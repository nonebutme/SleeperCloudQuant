"""Unified direct-execution entry for local formal verification scripts."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


_SOURCE_DIRECTORIES = (
    "app",
    "backtest_kernel",
    "config_center",
    "data_platform",
    "docs",
    "domain",
    "factor_lab",
    "reporting",
    "scripts",
    "web",
)
_SOURCE_FILES = (
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "manifest.md",
    "requirements-market-data.txt",
)
_EXTERNAL_ENVIRONMENT_KEYS = (
    "ALL_PROXY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "SCQ_AKSHARE_PROXY",
    "SCQ_LLM_API_KEY",
    "SCQ_LLM_BASE_URL",
    "SCQ_LLM_MODEL",
    "SCQ_LLM_PROVIDER_PROFILE",
    "SCQ_MARKET_PROVIDER_API_KEY",
    "SCQ_MARKET_PROVIDER_BASE_URL",
    "SCQ_MARKET_PROVIDER_NAME",
    "SCQ_MARKET_PROVIDER_TIMEOUT_SECONDS",
    "all_proxy",
    "https_proxy",
    "http_proxy",
)
_FINGERPRINT_SAMPLE_BYTES = 64 * 1024
_FORMAL_SNAPSHOT_MARKER = ".formal-verification-snapshot.json"
_PER_SCRIPT_WRITABLE_ROOTS = (
    Path("var/market"),
    Path("var/runtime"),
    Path("tmp/system-temp"),
    Path("output"),
)
_FORMAL_SOURCE_SCRIPTS = {
    "smoke_test_a_share_source_database.py",
    "smoke_test_a_share_full_market_quality.py",
}


class FormalVerificationIsolationError(RuntimeError):
    """Raised when formal verification cannot prove protected storage isolation."""


class FormalVerificationTestFailure(RuntimeError):
    """Represents an ordinary non-zero verification-script result."""

    def __init__(self, script_name: str, exit_code: int) -> None:
        self.script_name = script_name
        self.exit_code = int(exit_code)
        super().__init__(
            f"formal verification script failed: {script_name} (exit={exit_code})"
        )


@dataclass(frozen=True)
class FormalScriptResult:
    sequence: int
    script_name: str
    status: str
    exit_code: int | None
    log_path: str | None
    writable_state_reset: bool = False
    writable_state_evidence: str | None = None
    failure_type: str | None = None
    failure_message: str | None = None

    def as_report(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "script_name": self.script_name,
            "status": self.status,
            "exit_code": self.exit_code,
            "log_path": self.log_path,
            "writable_state_reset": self.writable_state_reset,
            "writable_state_evidence": self.writable_state_evidence,
            "failure": (
                None
                if self.failure_type is None
                else {
                    "type": self.failure_type,
                    "message": self.failure_message,
                }
            ),
        }


def _failure_payload(error: BaseException) -> dict[str, str]:
    return {"type": type(error).__name__, "message": str(error)}


def _existing_script_log_path(
    evidence_root: Path, sequence: int, script_name: str
) -> str | None:
    relative = f"logs/{sequence:03d}-{script_name}.log"
    return relative if (evidence_root / relative).is_file() else None


def _build_script_environment(
    *,
    script_name: str,
    base_environment: dict[str, str],
    formal_source_database: Path,
) -> dict[str, str]:
    environment = dict(base_environment)
    environment["SCQ_FORMAL_CURRENT_SCRIPT"] = script_name
    environment.pop("SCQ_FORMAL_SOURCE_A_SHARE_CANONICAL_DB_PATH", None)
    if script_name in _FORMAL_SOURCE_SCRIPTS:
        environment["SCQ_FORMAL_SOURCE_A_SHARE_CANONICAL_DB_PATH"] = str(
            formal_source_database.resolve()
        )
    if Path(script_name).suffix == ".mjs":
        for key in (
            "SCQ_FORMAL_PROTECTED_ROOTS",
            "SCQ_FORMAL_STORAGE_GUARD_LOG",
            "SCQ_FORMAL_STORAGE_GUARD_READY_LOG",
            "SCQ_FORMAL_STORAGE_GUARD_REQUIRED",
        ):
            environment.pop(key, None)
    return environment


def _run_script(
    script_name: str,
    *,
    snapshot_root: Path,
    base_environment: dict[str, str],
    evidence_root: Path,
    sequence: int,
    formal_source_database: Path,
) -> FormalScriptResult:
    script_path = snapshot_root / "scripts" / script_name
    environment = _build_script_environment(
        script_name=script_name,
        base_environment=base_environment,
        formal_source_database=formal_source_database,
    )
    log_path = evidence_root / "logs" / f"{sequence:03d}-{script_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ready_log = Path(base_environment["SCQ_FORMAL_STORAGE_GUARD_READY_LOG"])
    violation_log = Path(base_environment["SCQ_FORMAL_STORAGE_GUARD_LOG"])
    ready_size = ready_log.stat().st_size if ready_log.is_file() else 0
    violation_size = violation_log.stat().st_size if violation_log.is_file() else 0

    if script_path.suffix == ".mjs":
        command = ["node", str(script_path)]
    else:
        command = [
            sys.executable,
            str(snapshot_root / "scripts" / "_run_formal_isolated.py"),
            str(script_path),
        ]

    with log_path.open("w", encoding="utf-8", newline="\n") as log_stream:
        process = subprocess.Popen(
            command,
            cwd=snapshot_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                print(line, end="")
                log_stream.write(line)
                log_stream.flush()
        except BaseException:
            process.terminate()
            process.wait(timeout=10)
            raise
        return_code = process.wait()

    if script_path.suffix != ".mjs":
        observed_ready_size = ready_log.stat().st_size if ready_log.is_file() else 0
        if observed_ready_size <= ready_size:
            raise FormalVerificationIsolationError(
                f"storage guard ready marker missing for {script_name}"
            )
    observed_violation_size = violation_log.stat().st_size if violation_log.is_file() else 0
    if observed_violation_size > violation_size:
        raise FormalVerificationIsolationError(
            f"protected storage access was blocked while running {script_name}"
        )
    if return_code != 0:
        failure = FormalVerificationTestFailure(script_name, return_code)
        return FormalScriptResult(
            sequence=sequence,
            script_name=script_name,
            status="failed",
            exit_code=return_code,
            log_path=f"logs/{sequence:03d}-{script_name}.log",
            failure_type=type(failure).__name__,
            failure_message=str(failure),
        )
    return FormalScriptResult(
        sequence=sequence,
        script_name=script_name,
        status="passed",
        exit_code=0,
        log_path=f"logs/{sequence:03d}-{script_name}.log",
    )


def _is_link_or_reparse(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(
        getattr(path_stat, "st_file_attributes", 0) & reparse_flag
    )


def _write_formal_snapshot_marker(
    snapshot_root: Path, *, project_root: Path
) -> None:
    snapshot_root = snapshot_root.absolute()
    expected_formal_root = project_root.resolve(strict=True) / "tmp" / "formal-verification"
    if snapshot_root.name != "source":
        raise FormalVerificationIsolationError(
            f"formal snapshot root must be named source: {snapshot_root}"
        )
    if not snapshot_root.parent.name.startswith("formal-"):
        raise FormalVerificationIsolationError(
            f"formal snapshot run directory is invalid: {snapshot_root.parent}"
        )
    if os.path.normcase(str(snapshot_root.parent.parent.absolute())) != os.path.normcase(
        str(expected_formal_root.absolute())
    ):
        raise FormalVerificationIsolationError(
            "formal snapshot is not anchored under the expected project tmp root: "
            f"{snapshot_root}"
        )
    if any(
        _is_link_or_reparse(path)
        for path in (
            expected_formal_root.parent,
            expected_formal_root,
            snapshot_root.parent,
            snapshot_root,
        )
    ):
        raise FormalVerificationIsolationError(
            f"formal snapshot path contains a symlink or junction: {snapshot_root}"
        )
    if not snapshot_root.is_dir():
        raise FormalVerificationIsolationError(
            f"formal snapshot root must be a real directory: {snapshot_root}"
        )
    marker = snapshot_root / _FORMAL_SNAPSHOT_MARKER
    if marker.exists() or marker.is_symlink():
        raise FormalVerificationIsolationError(
            f"formal snapshot marker already exists: {marker}"
        )
    marker.write_text(
        json.dumps(
            {
                "format": 1,
                "snapshot_root": str(snapshot_root.resolve(strict=True)),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _validated_formal_snapshot_root(
    snapshot_root: Path, *, project_root: Path
) -> Path:
    supplied = Path(snapshot_root)
    if not supplied.is_absolute():
        raise FormalVerificationIsolationError(
            f"formal snapshot root must be absolute: {supplied}"
        )
    if supplied.name != "source" or not supplied.parent.name.startswith("formal-"):
        raise FormalVerificationIsolationError(
            f"refusing unexpected formal snapshot path: {supplied}"
        )
    expected_formal_root = project_root.resolve(strict=True) / "tmp" / "formal-verification"
    if os.path.normcase(str(supplied.parent.parent.absolute())) != os.path.normcase(
        str(expected_formal_root.absolute())
    ):
        raise FormalVerificationIsolationError(
            "refusing snapshot outside the expected project tmp/formal-verification: "
            f"{supplied}"
        )
    if any(
        _is_link_or_reparse(path)
        for path in (
            expected_formal_root.parent,
            expected_formal_root,
            supplied.parent,
            supplied,
        )
    ):
        raise FormalVerificationIsolationError(
            f"formal snapshot path contains a symlink or junction: {supplied}"
        )
    if not supplied.is_dir():
        raise FormalVerificationIsolationError(
            f"formal snapshot root is missing or redirected: {supplied}"
        )
    resolved = supplied.resolve(strict=True)
    marker = supplied / _FORMAL_SNAPSHOT_MARKER
    if not marker.is_file() or _is_link_or_reparse(marker):
        raise FormalVerificationIsolationError(
            f"formal snapshot marker is missing or redirected: {marker}"
        )
    try:
        marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FormalVerificationIsolationError(
            f"formal snapshot marker is invalid: {marker}"
        ) from error
    if marker_payload != {"format": 1, "snapshot_root": str(resolved)}:
        raise FormalVerificationIsolationError(
            f"formal snapshot marker does not bind this root: {marker}"
        )
    return resolved


def _assert_safe_writable_target(snapshot_root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise FormalVerificationIsolationError(
            f"formal writable root must be relative and contained: {relative}"
        )
    target = snapshot_root.joinpath(relative)
    current = snapshot_root
    for part in relative.parts:
        current = current / part
        if not current.exists() and not current.is_symlink():
            continue
        if _is_link_or_reparse(current):
            raise FormalVerificationIsolationError(
                f"formal writable root contains a symlink or junction: {current}"
            )
        if current != target and not current.is_dir():
            raise FormalVerificationIsolationError(
                f"formal writable root parent is not a directory: {current}"
            )
        if current == target and not current.is_dir():
            raise FormalVerificationIsolationError(
                f"formal writable root is not a directory: {current}"
            )
        try:
            current.resolve(strict=True).relative_to(snapshot_root)
        except (OSError, ValueError) as error:
            raise FormalVerificationIsolationError(
                f"formal writable root escapes snapshot: {current}"
            ) from error
    return target


def _reset_per_script_writable_state(
    snapshot_root: Path, *, project_root: Path
) -> tuple[Path, ...]:
    validated_root = _validated_formal_snapshot_root(
        snapshot_root, project_root=project_root
    )
    targets = tuple(
        _assert_safe_writable_target(validated_root, relative)
        for relative in _PER_SCRIPT_WRITABLE_ROOTS
    )
    for relative, expected_target in zip(_PER_SCRIPT_WRITABLE_ROOTS, targets):
        current_root = _validated_formal_snapshot_root(
            snapshot_root, project_root=project_root
        )
        target = _assert_safe_writable_target(current_root, relative)
        if target != expected_target:
            raise FormalVerificationIsolationError(
                f"formal writable root changed during reset: {relative}"
            )
        if target.is_dir():
            shutil.rmtree(target)
        current_root = _validated_formal_snapshot_root(
            snapshot_root, project_root=project_root
        )
        target = _assert_safe_writable_target(current_root, relative)
        if target != expected_target:
            raise FormalVerificationIsolationError(
                f"formal writable root changed after removal: {relative}"
            )
        target.mkdir(parents=True, exist_ok=False)
        _assert_safe_writable_target(
            validated_root, target.relative_to(validated_root)
        )
    return targets


def _writable_root_inventory(root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    file_count = 0
    directory_count = 0
    total_file_bytes = 0
    if not root.exists():
        return {
            "root": str(root),
            "exists": False,
            "file_count": 0,
            "directory_count": 0,
            "total_file_bytes": 0,
            "entries": [],
        }

    def visit(directory: Path) -> None:
        nonlocal file_count, directory_count, total_file_bytes
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda item: os.path.normcase(item.name))
        for child in children:
            child_path = Path(child.path)
            child_stat = child.stat(follow_symlinks=False)
            relative = child_path.relative_to(root).as_posix()
            is_redirect = child.is_symlink() or bool(
                getattr(child_stat, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )
            if is_redirect:
                kind = "redirect"
            elif child.is_dir(follow_symlinks=False):
                kind = "directory"
                directory_count += 1
            elif child.is_file(follow_symlinks=False):
                kind = "file"
                file_count += 1
                total_file_bytes += int(child_stat.st_size)
            else:
                kind = "other"
            entries.append(
                {
                    "path": relative,
                    "kind": kind,
                    "size": int(child_stat.st_size),
                    "mtime_ns": int(child_stat.st_mtime_ns),
                    "mode": int(child_stat.st_mode),
                }
            )
            if kind == "directory":
                visit(child_path)

    visit(root)
    return {
        "root": str(root),
        "exists": True,
        "file_count": file_count,
        "directory_count": directory_count,
        "total_file_bytes": total_file_bytes,
        "entries": entries,
    }


def _capture_per_script_writable_state(
    *,
    project_root: Path,
    snapshot_root: Path,
    evidence_root: Path,
    sequence: int,
    script_name: str,
) -> str:
    validated_root = _validated_formal_snapshot_root(
        snapshot_root, project_root=project_root
    )
    evidence_resolved = evidence_root.resolve(strict=True)
    try:
        evidence_resolved.relative_to(validated_root)
    except ValueError:
        pass
    else:
        raise FormalVerificationIsolationError(
            "formal evidence root must remain outside the resettable snapshot"
        )
    targets = tuple(
        _assert_safe_writable_target(validated_root, relative)
        for relative in _PER_SCRIPT_WRITABLE_ROOTS
    )
    safe_script_name = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in script_name
    )
    relative_evidence = (
        f"writable-state/{sequence:03d}-{safe_script_name}.json"
    )
    _write_report(
        evidence_root / relative_evidence,
        {
            "sequence": sequence,
            "script_name": script_name,
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "content_copied": False,
            "roots": [_writable_root_inventory(target) for target in targets],
        },
    )
    return relative_evidence


def _copy_source_snapshot(project_root: Path, snapshot_root: Path) -> None:
    snapshot_root.mkdir(parents=True, exist_ok=False)

    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name == "__pycache__"
            or name == ".pytest_cache"
            or name.endswith((".pyc", ".pyo"))
        }

    for name in _SOURCE_DIRECTORIES:
        source = project_root / name
        if not source.is_dir():
            raise FormalVerificationIsolationError(
                f"formal source snapshot is missing required directory: {name}"
            )
        shutil.copytree(source, snapshot_root / name, ignore=ignore)
    for name in _SOURCE_FILES:
        source = project_root / name
        if source.is_file():
            shutil.copy2(source, snapshot_root / name)
    for path in (
        snapshot_root / "var" / "market",
        snapshot_root / "var" / "runtime",
        snapshot_root / "tmp" / "system-temp",
    ):
        path.mkdir(parents=True, exist_ok=True)
    _write_formal_snapshot_marker(snapshot_root, project_root=project_root)


def _build_environment(
    *, project_root: Path, snapshot_root: Path, evidence_root: Path
) -> dict[str, str]:
    environment = dict(os.environ)
    for key in _EXTERNAL_ENVIRONMENT_KEYS:
        environment.pop(key, None)
    environment["NO_PROXY"] = "127.0.0.1,localhost"
    environment["no_proxy"] = "127.0.0.1,localhost"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    environment["SCQ_DISABLE_BACKGROUND_SCHEDULER"] = "1"
    environment["SCQ_ENABLE_DEMO_SEED"] = "1"
    environment["SCQ_FORMAL_ISOLATION"] = "1"
    environment["SCQ_FORMAL_STORAGE_GUARD_REQUIRED"] = "1"
    environment["SCQ_FORMAL_SNAPSHOT_ROOT"] = str(snapshot_root)
    environment["SCQ_FORMAL_EVIDENCE_ROOT"] = str(evidence_root)
    environment["SCQ_FORMAL_PROTECTED_ROOTS"] = os.pathsep.join(
        str(path.resolve())
        for path in (project_root / "var" / "market", project_root / "var" / "runtime")
    )
    environment["SCQ_FORMAL_STORAGE_GUARD_LOG"] = str(
        evidence_root / "storage-guard-violations.jsonl"
    )
    environment["SCQ_FORMAL_STORAGE_GUARD_READY_LOG"] = str(
        evidence_root / "storage-guard-ready.jsonl"
    )
    environment["SCQ_A_SHARE_CANONICAL_DB_PATH"] = str(
        snapshot_root / "var" / "market" / "a_share_market.sqlite3"
    )
    environment["SCQ_BACKTEST_RUNTIME_DB_PATH"] = str(
        snapshot_root / "var" / "runtime" / "backtest_results.sqlite3"
    )
    environment["SCQ_A_SHARE_DB_PATH"] = str(
        snapshot_root / "var" / "market" / "missing-legacy-a-share.sqlite3"
    )
    environment["SCQ_LEGACY_MARKET_DB_PATH"] = str(
        snapshot_root / "var" / "market" / "missing-legacy-market.sqlite3"
    )
    system_temp = str(snapshot_root / "tmp" / "system-temp")
    environment["TEMP"] = system_temp
    environment["TMP"] = system_temp
    environment["TMPDIR"] = system_temp
    environment["SQLITE_TMPDIR"] = system_temp
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(snapshot_root / "scripts" / "_formal_storage_guard"),
            str(snapshot_root),
        )
    )
    return environment


def _assert_no_sqlite_guard_bypasses(snapshot_root: Path) -> None:
    violations: list[str] = []
    for path in sorted(snapshot_root.rglob("*.py")):
        relative = path.relative_to(snapshot_root).as_posix()
        if relative == "scripts/_formal_storage_guard/sitecustomize.py":
            continue
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                item.name == "_sqlite3" for item in node.names
            ):
                violations.append(f"{relative}:{node.lineno}: private _sqlite3 import")
            if isinstance(node, ast.ImportFrom) and node.module == "_sqlite3":
                violations.append(f"{relative}:{node.lineno}: private _sqlite3 import")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Connection"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "sqlite3"
            ):
                violations.append(
                    f"{relative}:{node.lineno}: sqlite3.Connection constructor"
                )
    if violations:
        raise FormalVerificationIsolationError(
            "formal source contains SQLite guard bypasses: " + "; ".join(violations)
        )


def _assert_formal_source_consumers(snapshot_root: Path) -> None:
    forbidden_write_tokens = (
        ".write_bytes(",
        ".write_text(",
        ".unlink(",
        ".rename(",
        "os.open(",
        "sqlite3.dbapi2.connect(",
        "sqlite3.Connection(",
    )
    for script_name in sorted(_FORMAL_SOURCE_SCRIPTS):
        path = snapshot_root / "scripts" / script_name
        source = path.read_text(encoding="utf-8-sig")
        required = ("from _formal_read_only_a_share import",)
        missing = [token for token in required if token not in source]
        forbidden = [token for token in forbidden_write_tokens if token in source]
        if "build_demo_app" in source:
            forbidden.append("build_demo_app")
        if missing or forbidden:
            raise FormalVerificationIsolationError(
                f"formal source consumer contract failed for {script_name}: "
                f"missing={missing}, forbidden={forbidden}"
            )
    helper = (
        snapshot_root / "scripts" / "_formal_read_only_a_share.py"
    ).read_text(encoding="utf-8-sig")
    helper_required = (
        "SCQ_FORMAL_SOURCE_A_SHARE_CANONICAL_DB_PATH",
        "mode=ro&immutable=1",
        "uri=True",
        "PRAGMA query_only = ON",
        "formal source verification forbids schema initialization",
        "formal source verification forbids writable SQLite connections",
    )
    helper_missing = [token for token in helper_required if token not in helper]
    if helper_missing:
        raise FormalVerificationIsolationError(
            "formal immutable source helper contract failed: "
            f"missing={helper_missing}"
        )


def _sample_digest(path: Path, size: int) -> str:
    digest = hashlib.sha256()
    positions = sorted(
        {
            0,
            max(0, size // 2 - _FINGERPRINT_SAMPLE_BYTES // 2),
            max(0, size - _FINGERPRINT_SAMPLE_BYTES),
        }
    )
    with path.open("rb") as stream:
        for position in positions:
            stream.seek(position)
            block = stream.read(_FINGERPRINT_SAMPLE_BYTES)
            digest.update(position.to_bytes(8, "big", signed=False))
            digest.update(len(block).to_bytes(8, "big", signed=False))
            digest.update(block)
    return digest.hexdigest()


def _fingerprint_roots(project_root: Path, roots: tuple[Path, ...]) -> dict[str, Any]:
    fingerprint: dict[str, Any] = {}
    for root in roots:
        root_key = str(root.resolve().relative_to(project_root.resolve())).replace("\\", "/")
        if not root.exists():
            fingerprint[root_key] = {"exists": False, "files": {}}
            continue
        files: dict[str, Any] = {}
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: os.path.normcase(str(item)),
        ):
            stat = path.stat()
            relative = str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
            files[relative] = {
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
                "mode": int(stat.st_mode),
                "sample_sha256": _sample_digest(path, int(stat.st_size)),
            }
        fingerprint[root_key] = {"exists": True, "files": files}
    return fingerprint


def _fingerprint_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    changed: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = {"before": before.get(key), "after": after.get(key)}
    return changed


def _fingerprint_sha256(fingerprint: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _jsonl_record_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8") as stream:
        return sum(1 for line in stream if line.strip())


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _persist_evidence(evidence_root: Path, persistent_root: Path) -> None:
    persistent_root.mkdir(parents=True, exist_ok=True)
    for directory_name in ("logs", "writable-state"):
        source_directory = evidence_root / directory_name
        if source_directory.is_dir():
            shutil.copytree(
                source_directory,
                persistent_root / directory_name,
                dirs_exist_ok=True,
            )
    for name in ("storage-guard-ready.jsonl", "storage-guard-violations.jsonl"):
        source = evidence_root / name
        if source.is_file():
            shutil.copy2(source, persistent_root / name)


def _cleanup_success_run(project_root: Path, run_root: Path) -> None:
    allowed_parent = (project_root / "tmp" / "formal-verification").resolve()
    resolved = run_root.resolve()
    if resolved.parent != allowed_parent or not resolved.name.startswith("formal-"):
        raise FormalVerificationIsolationError(
            f"refusing to clean unexpected formal run path: {resolved}"
        )
    shutil.rmtree(resolved)


def _assert_formal_source_is_quiescent(source_database: Path) -> None:
    if not source_database.is_file():
        raise FormalVerificationIsolationError(
            f"formal source database is unavailable: {source_database}"
        )
    for suffix in ("-wal", "-journal"):
        sidecar = Path(str(source_database) + suffix)
        if sidecar.is_file() and sidecar.stat().st_size > 0:
            raise FormalVerificationIsolationError(
                f"formal source database has a non-empty {suffix} sidecar; immutable "
                "verification requires a quiescent, checkpointed source"
            )


def _formal_source_identity(source_database: Path) -> dict[str, Any]:
    stat = source_database.stat()
    sidecars: dict[str, Any] = {}
    for suffix in ("-wal", "-journal", "-shm"):
        path = Path(str(source_database) + suffix)
        if path.is_file():
            sidecar_stat = path.stat()
            sidecars[suffix] = {
                "size": int(sidecar_stat.st_size),
                "mtime_ns": int(sidecar_stat.st_mtime_ns),
                "sample_sha256": _sample_digest(path, int(sidecar_stat.st_size)),
            }
        else:
            sidecars[suffix] = {"exists": False}
    return {
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sample_sha256": _sample_digest(source_database, int(stat.st_size)),
        "sidecars": sidecars,
    }


def _assert_protected_roots_unchanged(
    *,
    project_root: Path,
    protected_roots: tuple[Path, ...],
    baseline: dict[str, Any],
    script_name: str,
) -> dict[str, Any]:
    try:
        observed = _fingerprint_roots(project_root, protected_roots)
    except Exception as error:
        raise FormalVerificationIsolationError(
            f"protected storage fingerprint capture failed after {script_name}: "
            f"{type(error).__name__}: {error}"
        ) from error
    changes = _fingerprint_changes(baseline, observed)
    if changes:
        raise FormalVerificationIsolationError(
            f"protected storage fingerprint changed after {script_name}: "
            + ", ".join(sorted(changes))
        )
    return observed


def _execute_script_sequence(
    scripts: list[str],
    *,
    project_root: Path,
    protected_roots: tuple[Path, ...],
    protected_baseline: dict[str, Any],
    snapshot_root: Path,
    base_environment: dict[str, str],
    evidence_root: Path,
    formal_source_database: Path,
) -> tuple[list[FormalScriptResult], BaseException | None]:
    results: list[FormalScriptResult] = []
    fatal_failure: BaseException | None = None
    for sequence, script_name in enumerate(scripts, start=1):
        print(f"[formal] running {script_name}")
        script_result: FormalScriptResult | None = None
        execution_failure: BaseException | None = None
        safety_failure: BaseException | None = None
        source_identity: dict[str, Any] | None = None
        writable_state_reset = False
        writable_state_evidence: str | None = None

        try:
            _reset_per_script_writable_state(
                snapshot_root, project_root=project_root
            )
            writable_state_reset = True
            if script_name in _FORMAL_SOURCE_SCRIPTS:
                _assert_formal_source_is_quiescent(formal_source_database)
                source_identity = _formal_source_identity(formal_source_database)
            script_result = _run_script(
                script_name,
                snapshot_root=snapshot_root,
                base_environment=base_environment,
                evidence_root=evidence_root,
                sequence=sequence,
                formal_source_database=formal_source_database,
            )
        except BaseException as error:
            execution_failure = error

        if writable_state_reset:
            try:
                writable_state_evidence = _capture_per_script_writable_state(
                    project_root=project_root,
                    snapshot_root=snapshot_root,
                    evidence_root=evidence_root,
                    sequence=sequence,
                    script_name=script_name,
                )
                if script_result is not None:
                    script_result = replace(
                        script_result,
                        writable_state_reset=True,
                        writable_state_evidence=writable_state_evidence,
                    )
            except BaseException as error:
                safety_failure = error

        if source_identity is not None:
            try:
                _assert_formal_source_is_quiescent(formal_source_database)
                if _formal_source_identity(formal_source_database) != source_identity:
                    raise FormalVerificationIsolationError(
                        f"formal source identity changed while running {script_name}"
                    )
            except BaseException as error:
                safety_failure = error

        try:
            _assert_protected_roots_unchanged(
                project_root=project_root,
                protected_roots=protected_roots,
                baseline=protected_baseline,
                script_name=script_name,
            )
        except BaseException as error:
            if safety_failure is None:
                safety_failure = error

        fatal_failure = safety_failure or execution_failure
        if fatal_failure is not None:
            log_path = (
                script_result.log_path
                if script_result is not None
                else _existing_script_log_path(evidence_root, sequence, script_name)
            )
            if log_path is not None and not (evidence_root / log_path).is_file():
                log_path = None
            results.append(
                FormalScriptResult(
                    sequence=sequence,
                    script_name=script_name,
                    status="fatal",
                    exit_code=(
                        script_result.exit_code if script_result is not None else None
                    ),
                    log_path=log_path,
                    writable_state_reset=writable_state_reset,
                    writable_state_evidence=writable_state_evidence,
                    failure_type=type(fatal_failure).__name__,
                    failure_message=str(fatal_failure),
                )
            )
            break

        if script_result is None:
            fatal_failure = FormalVerificationIsolationError(
                f"formal verification produced no result for {script_name}"
            )
            results.append(
                FormalScriptResult(
                    sequence=sequence,
                    script_name=script_name,
                    status="fatal",
                    exit_code=None,
                    log_path=_existing_script_log_path(
                        evidence_root, sequence, script_name
                    ),
                    writable_state_reset=writable_state_reset,
                    writable_state_evidence=writable_state_evidence,
                    failure_type=type(fatal_failure).__name__,
                    failure_message=str(fatal_failure),
                )
            )
            break
        results.append(script_result)
    return results, fatal_failure


def _summarize_script_results(
    scripts: list[str],
    results: list[FormalScriptResult],
    fatal_failure: BaseException | None,
) -> dict[str, Any]:
    attempted_scripts = [item.script_name for item in results]
    completed_scripts = [
        item.script_name for item in results if item.status in {"passed", "failed"}
    ]
    passed_scripts = [item.script_name for item in results if item.status == "passed"]
    test_failures = [item for item in results if item.status == "failed"]
    suite_completed = fatal_failure is None and len(results) == len(scripts)
    if fatal_failure is not None:
        run_outcome = "fatal_failure"
    elif test_failures:
        run_outcome = "completed_with_test_failures"
    elif suite_completed:
        run_outcome = "passed"
    else:
        run_outcome = "incomplete"
    return {
        "attempted_scripts": attempted_scripts,
        "completed_scripts": completed_scripts,
        "passed_scripts": passed_scripts,
        "test_failures": test_failures,
        "unattempted": scripts[len(results) :],
        "suite_completed": suite_completed,
        "run_outcome": run_outcome,
    }


def _summarize_per_script_writable_state_resets(
    scripts: list[str], results: list[FormalScriptResult]
) -> dict[str, Any]:
    successful_reset_count = sum(item.writable_state_reset for item in results)
    return {
        "policy_enabled": True,
        "successful_reset_count": successful_reset_count,
        "expected_reset_count": len(scripts),
        "completed_for_entire_suite": (
            len(results) == len(scripts) and successful_reset_count == len(scripts)
        ),
    }


def _promote_final_fingerprint_failure(
    fatal_failure: BaseException | None,
    *,
    fingerprints_paired: bool,
    changes: dict[str, dict[str, Any]],
) -> BaseException | None:
    if fatal_failure is not None:
        return fatal_failure
    if not fingerprints_paired:
        return FormalVerificationIsolationError(
            "protected storage before/after fingerprints were not both captured"
        )
    if "fingerprint_error" in changes:
        return FormalVerificationIsolationError(
            "final protected storage fingerprint capture failed"
        )
    if changes:
        return FormalVerificationIsolationError(
            "protected storage fingerprint changed during formal verification"
        )
    return None


def main() -> None:
    project_root = ensure_project_root_on_sys_path().resolve()
    run_id = (
        "formal-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    run_root = project_root / "tmp" / "formal-verification" / run_id
    snapshot_root = run_root / "source"
    evidence_root = run_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=False)
    protected_roots = (
        project_root / "var" / "market",
        project_root / "var" / "runtime",
    )
    source_database = project_root / "var" / "market" / "a_share_market.sqlite3"
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    script_results: list[FormalScriptResult] = []
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    before_fingerprint_captured = False
    after_fingerprint_captured = False
    changes: dict[str, dict[str, Any]] = {}
    fatal_failure: BaseException | None = None

    scripts = [
        "smoke_test_formal_verification_isolation.py",
        "verify_formal_fake_runtime.py",
        "verify_formal_reporting.py",
        "verify_formal_sqlite_cache.py",
        "smoke_test_legacy_sqlite_market_data.py",
        "smoke_test_demo_governed_seed.py",
        "smoke_test_a_share_source_database.py",
        "smoke_test_a_share_canonical_store.py",
        "smoke_test_stage78_data_governance.py",
        "smoke_test_stage78_2_incremental_scheduler.py",
        "smoke_test_data_maintenance.py",
        "smoke_test_selected_quality_repair.py",
        "smoke_test_stage78_2_scheduler_api.py",
        "smoke_test_stage86_data_center.py",
        "smoke_test_stage86_data_center_ui.py",
        "smoke_test_data_center_reference_refresh.py",
        "smoke_test_trading_status_semantic_repair.py",
        "smoke_test_trading_status_remediation_web_api.py",
        "smoke_test_stage2_status_remediation_ui.mjs",
        "smoke_test_stage2_status_remediation_closure_api.py",
        "smoke_test_trading_status_issue_reconciliation.py",
        "smoke_test_stage2_status_remediation_closure_ui.mjs",
        "smoke_test_stage87_factor_research_core.py",
        "smoke_test_stage87_factor_research_api.py",
        "smoke_test_factor_research_streaming.py",
        "smoke_test_stage87_factor_research_ui.py",
        "smoke_test_stage88_integrity_bridge.py",
        "smoke_test_factor_optimization.py",
        "smoke_test_stage4_factor_consumption.py",
        "smoke_test_stage91_source_quality_governance.py",
        "smoke_test_data_source_vtable_interaction.mjs",
        "smoke_test_m4_asset_browser_ui.py",
        "smoke_test_market_panorama.py",
        "smoke_test_m4_index_market.py",
        "smoke_test_vtable_global_adoption.py",
        "smoke_test_quant_ui_candidate.py",
        "smoke_test_stage78_3_context_backfill.py",
        "smoke_test_a_share_full_market_quality.py",
        "smoke_test_local_sqlite_backtest_runtime.py",
        "smoke_test_backtest_audit_regressions.py",
        "smoke_test_backtest_ui_audit.mjs",
        "smoke_test_versioned_custom_strategies.py",
        "smoke_test_strategy_library_crud.py",
        "smoke_test_strategy_dataset_validation.py",
        "smoke_test_strategy_dataset_resolver.py",
        "smoke_test_strict_strategy_warmup_runtime.py",
        "smoke_test_fujing_v7_research_gates.py",
        "smoke_test_fujing_v7_factor_features.py",
        "smoke_test_fujing_v7_candidate_strategy.py",
        "smoke_test_fujing_v7_universe_oos_gates.py",
        "smoke_test_security_master_history.py",
        "smoke_test_baostock_security_master_provider.py",
        "smoke_test_fujing_v7_preflight_service.py",
        "smoke_test_sealed_oos_evidence_service.py",
        "smoke_test_independent_screening_backtest.py",
        "smoke_test_independent_signal_analysis.py",
        "smoke_test_shared_portfolio_backtest.py",
        "smoke_test_shared_portfolio_execution_policies.py",
        "smoke_test_backtest_mode_reports.py",
        "smoke_test_stage74_professional_report_workspace.py",
        "smoke_test_stage75_quant_workbench_ux.py",
        "smoke_test_stage76_unified_backtest_workspace.py",
        "smoke_test_stage77_backtest_report_ui.py",
        "smoke_test_stage80_85_advanced_reports.py",
        "smoke_test_backtest_mode_task_directory.py",
        "smoke_test_full_market_backtest_scheduler.py",
        "smoke_test_classification_batch_sync.py",
        "smoke_test_factor_lab.py",
        "smoke_test_formal_services.py",
        "smoke_test_formal_api.py",
        "smoke_test_formal_http_adapter.py",
        "smoke_test_unified_web_entry.py",
        "smoke_test_r2_indicators.py",
        "smoke_test_ai_config_api.py",
        "smoke_test_report_package_manifest.py",
        "smoke_test_report_package_exports.py",
        "smoke_test_report_package_layout.py",
        "smoke_test_real_provider_entry.py",
        "smoke_test_rqalpha_local_settings.py",
        "smoke_test_market_endpoint_mapping.py",
        "smoke_test_market_data_quality.py",
        "smoke_test_market_data_browser.py",
        "smoke_test_strategy_research_tasks.py",
        "smoke_test_research_task_backtest_run.py",
        "smoke_test_backtest_result_panel.py",
        "smoke_test_backtest_portfolio_panel.py",
        "smoke_test_backtest_trade_risk_attribution.py",
        "smoke_test_backtest_result_pagination_exports.py",
        "smoke_test_backtest_experiment_index.py",
        "smoke_test_experiment_review_package.py",
        "smoke_test_experiment_filter_compare.py",
        "smoke_test_strategy_evaluation_diagnostics.py",
        "smoke_test_parameter_matrix_tasks.py",
        "smoke_test_market_data_assets.py",
        "smoke_test_backtest_data_asset_trace.py",
        "smoke_test_backtest_input_snapshot_directory.py",
        "smoke_test_asset_consistency_panels.py",
        "smoke_test_data_asset_directory_filters_migration.py",
        "smoke_test_report_analysis_summary.py",
        "smoke_test_report_visual_contract.py",
        "smoke_test_experiment_report_comparison.py",
        "smoke_test_experiment_report_comparison_charts.py",
        "smoke_test_experiment_report_comparison_package.py",
        "smoke_test_report_package_directory.py",
        "smoke_test_report_package_lifecycle.py",
        "smoke_test_report_package_export_manifest.py",
        "smoke_test_backtest_workspace_ui.py",
        "smoke_test_backtest_task_workflow_ui.py",
    "smoke_test_backtest_task_usability.py",
        "smoke_test_stage71a_backtest_pc_workspace.py",
        "smoke_test_stage71b_backtest_history_results.py",
        "smoke_test_stage73_backtest_history_selection_encoding.py",
    ]
    try:
        before = _fingerprint_roots(project_root, protected_roots)
        before_fingerprint_captured = True
        _assert_formal_source_is_quiescent(source_database)
        _copy_source_snapshot(project_root, snapshot_root)
        _assert_no_sqlite_guard_bypasses(snapshot_root)
        _assert_formal_source_consumers(snapshot_root)
        environment = _build_environment(
            project_root=project_root,
            snapshot_root=snapshot_root,
            evidence_root=evidence_root,
        )
        script_results, fatal_failure = _execute_script_sequence(
            scripts,
            project_root=project_root,
            protected_roots=protected_roots,
            protected_baseline=before,
            snapshot_root=snapshot_root,
            base_environment=environment,
            evidence_root=evidence_root,
            formal_source_database=source_database,
        )
    except BaseException as error:
        fatal_failure = error
    finally:
        try:
            after = _fingerprint_roots(project_root, protected_roots)
            after_fingerprint_captured = True
            changes = (
                _fingerprint_changes(before, after)
                if before_fingerprint_captured
                else {}
            )
        except BaseException as fingerprint_error:
            changes = {
                "fingerprint_error": {
                    "error": f"{type(fingerprint_error).__name__}: {fingerprint_error}"
                }
            }
            if fatal_failure is None:
                fatal_failure = FormalVerificationIsolationError(
                    "final protected storage fingerprint capture failed: "
                    f"{type(fingerprint_error).__name__}: {fingerprint_error}"
                )

    fingerprints_paired = before_fingerprint_captured and after_fingerprint_captured
    fatal_failure = _promote_final_fingerprint_failure(
        fatal_failure,
        fingerprints_paired=fingerprints_paired,
        changes=changes,
    )
    if fatal_failure is None and len(script_results) != len(scripts):
        fatal_failure = FormalVerificationIsolationError(
            "formal verification stopped without a fatal result"
        )
    summary = _summarize_script_results(scripts, script_results, fatal_failure)
    attempted_scripts = summary["attempted_scripts"]
    completed_scripts = summary["completed_scripts"]
    passed_scripts = summary["passed_scripts"]
    test_failures = summary["test_failures"]
    unattempted = summary["unattempted"]
    suite_completed = bool(summary["suite_completed"])
    run_outcome = str(summary["run_outcome"])
    reset_summary = _summarize_per_script_writable_state_resets(
        scripts, script_results
    )
    failed = run_outcome != "passed"
    failure_payload = (
        _failure_payload(fatal_failure)
        if fatal_failure is not None
        else (
            {
                "type": "FormalVerificationTestFailureSummary",
                "message": f"{len(test_failures)} verification script(s) failed",
            }
            if test_failures
            else None
        )
    )
    report = {
        "run_id": run_id,
        "status": "failed" if failed else "passed",
        "run_outcome": run_outcome,
        "suite_completed": suite_completed,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script_count": len(scripts),
        "attempted_script_count": len(attempted_scripts),
        "completed_script_count": len(completed_scripts),
        "passed_script_count": len(passed_scripts),
        "failed_script_count": len(test_failures),
        "unattempted_script_count": len(unattempted),
        "attempted_scripts": attempted_scripts,
        "completed_scripts": completed_scripts,
        "passed_scripts": passed_scripts,
        "script_results": [item.as_report() for item in script_results],
        "test_failures": [item.as_report() for item in test_failures],
        "unattempted": unattempted,
        "fatal_failure": (
            _failure_payload(fatal_failure) if fatal_failure is not None else None
        ),
        "snapshot_root": str(snapshot_root),
        "sandbox_retained": failed,
        "per_script_writable_state_reset_policy_enabled": reset_summary[
            "policy_enabled"
        ],
        "per_script_writable_state_reset": reset_summary[
            "completed_for_entire_suite"
        ],
        "per_script_writable_state_successful_reset_count": reset_summary[
            "successful_reset_count"
        ],
        "per_script_writable_state_expected_reset_count": reset_summary[
            "expected_reset_count"
        ],
        "per_script_writable_state_roots": [
            str(snapshot_root / relative)
            for relative in _PER_SCRIPT_WRITABLE_ROOTS
        ],
        "per_script_writable_state_evidence": [
            item.writable_state_evidence
            for item in script_results
            if item.writable_state_evidence is not None
        ],
        "protected_roots": [str(path.resolve()) for path in protected_roots],
        "protected_storage_fingerprints_paired": fingerprints_paired,
        "protected_storage_unchanged": fingerprints_paired and not changes,
        "protected_storage_before_sha256": (
            _fingerprint_sha256(before) if before_fingerprint_captured else None
        ),
        "protected_storage_after_sha256": (
            _fingerprint_sha256(after) if after_fingerprint_captured else None
        ),
        "protected_storage_changes": changes,
        "guard_ready_count": _jsonl_record_count(
            evidence_root / "storage-guard-ready.jsonl"
        ),
        "guard_violation_count": _jsonl_record_count(
            evidence_root / "storage-guard-violations.jsonl"
        ),
        "script_logs": [
            item.log_path for item in script_results if item.log_path is not None
        ],
        "isolation_scope": (
            "allowlisted source snapshot with per-script writable-root resets plus "
            "Python SQLite/filesystem fail-closed guard and before/after protected-root "
            "fingerprints; this is not an OS sandbox"
        ),
        "failure": failure_payload,
    }
    report_path = evidence_root / "formal-verification-report.json"
    persistent_evidence_root = (
        project_root / "tmp" / "formal-verification-reports" / run_id
    )
    persistent_report_path = persistent_evidence_root / "formal-verification-report.json"
    _write_report(report_path, report)
    _persist_evidence(evidence_root, persistent_evidence_root)
    _write_report(persistent_report_path, report)

    if failed:
        if fatal_failure is not None:
            print(
                f"[formal] stopped on fatal failure; evidence preserved at {run_root}",
                file=sys.stderr,
            )
            if isinstance(fatal_failure, KeyboardInterrupt):
                raise fatal_failure
        else:
            print(
                f"[formal] suite completed with {len(test_failures)} test failure(s); "
                f"evidence preserved at {run_root}",
                file=sys.stderr,
            )
        raise SystemExit(1) from fatal_failure

    try:
        _cleanup_success_run(project_root, run_root)
    except BaseException as cleanup_error:
        cleanup_payload = _failure_payload(cleanup_error)
        report["status"] = "failed"
        report["run_outcome"] = "failed_cleanup"
        report["sandbox_retained"] = True
        report["fatal_failure"] = cleanup_payload
        report["failure"] = cleanup_payload
        _write_report(report_path, report)
        _write_report(persistent_report_path, report)
        print(
            f"[formal] verification passed but isolated workspace cleanup failed; "
            f"evidence preserved at {run_root}",
            file=sys.stderr,
        )
        raise SystemExit(1) from cleanup_error
    print("[formal] all verifications passed")


if __name__ == "__main__":
    main()
