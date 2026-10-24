"""Fail-closed SQLite guard for isolated formal-verification child processes.

This module is loaded by Python's normal ``sitecustomize`` hook. It is placed
first on ``PYTHONPATH`` only by ``run_formal_verifications.py``; normal product
processes never import it.
"""

from __future__ import annotations

import builtins
import _sqlite3
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote


_REAL_CONNECT = sqlite3.connect
_PROTECTED_ROOTS = tuple(
    Path(item).resolve()
    for item in os.environ.get("SCQ_FORMAL_PROTECTED_ROOTS", "").split(os.pathsep)
    if item.strip()
)
_REQUIRED = os.environ.get("SCQ_FORMAL_STORAGE_GUARD_REQUIRED") == "1"
_VIOLATION_LOG = os.environ.get("SCQ_FORMAL_STORAGE_GUARD_LOG", "")
_READY_LOG = os.environ.get("SCQ_FORMAL_STORAGE_GUARD_READY_LOG", "")
_CURRENT_SCRIPT = os.environ.get("SCQ_FORMAL_CURRENT_SCRIPT", "")
_REAL_BUILTIN_OPEN = builtins.open
_REAL_IO_OPEN = io.open
_REAL_OS_OPEN = os.open
_REAL_OS_REMOVE = os.remove
_REAL_OS_UNLINK = os.unlink
_REAL_OS_RENAME = os.rename
_REAL_OS_REPLACE = os.replace
_REAL_OS_CHMOD = os.chmod
_REAL_OS_UTIME = os.utime


def _record(path_text: str, event: str, **details: Any) -> None:
    if not path_text:
        return
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "pid": os.getpid(),
        "script": _CURRENT_SCRIPT,
        "event": event,
        **details,
    }
    path = Path(path_text)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        # Blocking remains active even if the secondary evidence sink is lost.
        return


def _normalized_path(value: Any) -> Path | None:
    try:
        text = os.fsdecode(os.fspath(value))
    except (TypeError, ValueError):
        return None
    if text in {"", ":memory:"} or text.startswith("file::memory:"):
        return None
    if text.startswith("file:"):
        raw_path = unquote(text[5:].split("?", 1)[0])
        if os.name == "nt" and raw_path.startswith("/") and len(raw_path) >= 3:
            if raw_path[2] == ":":
                raw_path = raw_path[1:]
        text = raw_path
    try:
        return Path(text).resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _is_protected(path: Path | None) -> bool:
    if path is None:
        return False
    candidate = os.path.normcase(str(path))
    for root in _PROTECTED_ROOTS:
        protected = os.path.normcase(str(root))
        try:
            if os.path.commonpath((candidate, protected)) == protected:
                return True
        except ValueError:
            continue
    return False


def _is_immutable_read_uri(database: Any, *, uri: bool) -> bool:
    try:
        text = os.fsdecode(os.fspath(database))
    except (TypeError, ValueError):
        return False
    if not uri or not text.startswith("file:") or "?" not in text:
        return False
    query = parse_qs(text.split("?", 1)[1], keep_blank_values=True)
    return query.get("mode", [""])[-1].lower() == "ro" and query.get(
        "immutable", [""]
    )[-1].lower() in {"1", "true", "yes", "on"}


_WRITE_ACTION_NAMES = (
    "SQLITE_CREATE_INDEX",
    "SQLITE_CREATE_TABLE",
    "SQLITE_CREATE_TEMP_INDEX",
    "SQLITE_CREATE_TEMP_TABLE",
    "SQLITE_CREATE_TEMP_TRIGGER",
    "SQLITE_CREATE_TEMP_VIEW",
    "SQLITE_CREATE_TRIGGER",
    "SQLITE_CREATE_VIEW",
    "SQLITE_DELETE",
    "SQLITE_DROP_INDEX",
    "SQLITE_DROP_TABLE",
    "SQLITE_DROP_TEMP_INDEX",
    "SQLITE_DROP_TEMP_TABLE",
    "SQLITE_DROP_TEMP_TRIGGER",
    "SQLITE_DROP_TEMP_VIEW",
    "SQLITE_DROP_TRIGGER",
    "SQLITE_DROP_VIEW",
    "SQLITE_INSERT",
    "SQLITE_REINDEX",
    "SQLITE_UPDATE",
)
_WRITE_ACTIONS = {
    int(getattr(sqlite3, name))
    for name in _WRITE_ACTION_NAMES
    if hasattr(sqlite3, name)
}
_ACTION_LABELS = {
    int(getattr(sqlite3, name)): name
    for name in _WRITE_ACTION_NAMES
    if hasattr(sqlite3, name)
}
_SAFE_MUTATING_PRAGMAS = {"busy_timeout", "foreign_keys", "query_only", "temp_store"}


def _guarded_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    uri = bool(kwargs.get("uri", False))
    resolved = _normalized_path(database)
    protected_main = _is_protected(resolved)
    if protected_main and not _is_immutable_read_uri(database, uri=uri):
        _record(
            _VIOLATION_LOG,
            "protected_connect_blocked",
            database=str(resolved or database),
            required_mode="mode=ro&immutable=1",
        )
        raise sqlite3.OperationalError(
            "formal storage guard blocked a non-immutable connection to a protected SQLite path"
        )

    connection = _REAL_CONNECT(database, *args, **kwargs)
    state = {"protected_main": protected_main, "protected_attachment": False}

    def authorize(
        action: int,
        arg1: str | None,
        arg2: str | None,
        database_name: str | None,
        _trigger: str | None,
    ) -> int:
        if action == getattr(sqlite3, "SQLITE_ATTACH", -1):
            if arg1 is None:
                _record(
                    _VIOLATION_LOG,
                    "protected_attach_blocked",
                    database="<parameterized-or-unresolved>",
                    reason="formal verification requires an auditable literal immutable URI",
                )
                return sqlite3.SQLITE_DENY
            attached_path = _normalized_path(arg1)
            if _is_protected(attached_path):
                if not _is_immutable_read_uri(arg1, uri=True):
                    _record(
                        _VIOLATION_LOG,
                        "protected_attach_blocked",
                        database=str(attached_path or arg1),
                        required_mode="mode=ro&immutable=1",
                    )
                    return sqlite3.SQLITE_DENY
                state["protected_attachment"] = True
            return sqlite3.SQLITE_OK

        protected_write_scope = (
            state["protected_attachment"] and database_name != "temp"
        ) or (state["protected_main"] and database_name in {None, "main"})
        if action in _WRITE_ACTIONS and protected_write_scope:
            _record(
                _VIOLATION_LOG,
                "protected_write_blocked",
                action=_ACTION_LABELS.get(action, str(action)),
                object_name=arg1,
                database_name=database_name,
            )
            return sqlite3.SQLITE_DENY

        if action == getattr(sqlite3, "SQLITE_PRAGMA", -1) and protected_write_scope:
            pragma = str(arg1 or "").lower()
            value = str(arg2 or "").upper()
            safe = arg2 is None or (
                pragma in _SAFE_MUTATING_PRAGMAS
                and (
                    pragma in {"busy_timeout", "foreign_keys", "temp_store"}
                    or value in {"1", "ON", "TRUE", "MEMORY"}
                )
            )
            if not safe:
                _record(
                    _VIOLATION_LOG,
                    "protected_pragma_blocked",
                    pragma=pragma,
                    value=arg2,
                    database_name=database_name,
                )
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(authorize)
    return connection


def _deny_filesystem_mutation(operation: str, *values: Any) -> None:
    protected = [
        str(path)
        for path in (_normalized_path(value) for value in values)
        if _is_protected(path)
    ]
    if not protected:
        return
    _record(
        _VIOLATION_LOG,
        "protected_filesystem_write_blocked",
        operation=operation,
        paths=protected,
    )
    raise PermissionError(
        f"formal storage guard blocked {operation} on protected storage"
    )


def _guarded_builtin_open(
    file: Any, mode: str = "r", *args: Any, **kwargs: Any
) -> Any:
    if any(marker in str(mode) for marker in ("w", "a", "x", "+")):
        _deny_filesystem_mutation("builtins.open", file)
    return _REAL_BUILTIN_OPEN(file, mode, *args, **kwargs)


def _guarded_io_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    if any(marker in str(mode) for marker in ("w", "a", "x", "+")):
        _deny_filesystem_mutation("io.open", file)
    return _REAL_IO_OPEN(file, mode, *args, **kwargs)


def _guarded_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
    write_flags = (
        getattr(os, "O_WRONLY", 0)
        | getattr(os, "O_RDWR", 0)
        | getattr(os, "O_CREAT", 0)
        | getattr(os, "O_TRUNC", 0)
        | getattr(os, "O_APPEND", 0)
        | getattr(os, "O_TMPFILE", 0)
    )
    if int(flags) & write_flags:
        _deny_filesystem_mutation("os.open", path)
    return _REAL_OS_OPEN(path, flags, *args, **kwargs)


def _guarded_remove(path: Any, *args: Any, **kwargs: Any) -> None:
    _deny_filesystem_mutation("os.remove", path)
    return _REAL_OS_REMOVE(path, *args, **kwargs)


def _guarded_unlink(path: Any, *args: Any, **kwargs: Any) -> None:
    _deny_filesystem_mutation("os.unlink", path)
    return _REAL_OS_UNLINK(path, *args, **kwargs)


def _guarded_rename(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
    _deny_filesystem_mutation("os.rename", src, dst)
    return _REAL_OS_RENAME(src, dst, *args, **kwargs)


def _guarded_replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
    _deny_filesystem_mutation("os.replace", src, dst)
    return _REAL_OS_REPLACE(src, dst, *args, **kwargs)


def _guarded_chmod(path: Any, mode: int, *args: Any, **kwargs: Any) -> None:
    _deny_filesystem_mutation("os.chmod", path)
    return _REAL_OS_CHMOD(path, mode, *args, **kwargs)


def _guarded_utime(path: Any, *args: Any, **kwargs: Any) -> None:
    _deny_filesystem_mutation("os.utime", path)
    return _REAL_OS_UTIME(path, *args, **kwargs)


if _REQUIRED and not _PROTECTED_ROOTS:
    raise RuntimeError("formal storage guard requires at least one protected root")

sqlite3.connect = _guarded_connect
sqlite3.dbapi2.connect = _guarded_connect
_sqlite3.connect = _guarded_connect
builtins.open = _guarded_builtin_open
io.open = _guarded_io_open
os.open = _guarded_os_open
os.remove = _guarded_remove
os.unlink = _guarded_unlink
os.rename = _guarded_rename
os.replace = _guarded_replace
os.chmod = _guarded_chmod
os.utime = _guarded_utime
setattr(builtins, "_SCQ_FORMAL_STORAGE_GUARD_READY", True)
os.environ["SCQ_FORMAL_STORAGE_GUARD_READY"] = "1"
_record(
    _READY_LOG,
    "guard_ready",
    protected_root_count=len(_PROTECTED_ROOTS),
    working_directory=str(Path.cwd()),
)
