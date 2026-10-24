"""Administrator-only, checkpointed trading-status batch remediation."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import socket
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from _project_bootstrap import ensure_project_root_on_sys_path
except ModuleNotFoundError:  # Imported as scripts.* by the Web application.
    from scripts._project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.storage.a_share_governance_store import AShareGovernanceStore
from scripts.preview_trading_status_semantic_remediation import build_preview_report


CONFIRMATION_PHRASE = "APPLY_TRADING_STATUS_REPAIR"
CHECKPOINT_VERSION = "2"
LEGACY_CHECKPOINT_VERSION = "1"
MAX_AUTHORIZED_TOTAL_WRITES = 1_000_000
DATABASE_LEASE_VERSION = "1"
_WINDOWS_SHARING_RETRY_ATTEMPTS = 20
_WINDOWS_SHARING_RETRY_DELAY_SECONDS = 0.01
_DATABASE_LEASE_OWNER_LIMIT_BYTES = 16 * 1024
_TERMINAL_STATUSES = {"completed", "authorization_exhausted"}
_RESUMABLE_STATUSES = {
    "queued", "running", "pause_requested", "paused_by_user",
    "paused_max_writes", "failed",
}


class TradingStatusDatabaseLeaseBusyError(ValueError):
    """Raised when another process owns the remediation writer lease."""

    def __init__(
        self, database: Path, lock_path: Path,
        owner: dict[str, Any] | None = None,
    ) -> None:
        self.database = database
        self.lock_path = lock_path
        self.owner = dict(owner or {})
        active_run_id = str(self.owner.get("run_id") or "unknown")
        holder_kind = str(self.owner.get("holder_kind") or "unknown")
        super().__init__(
            "trading status remediation database lease is busy: "
            f"active_run_id={active_run_id}, holder_kind={holder_kind}"
        )


class TradingStatusDatabaseLease:
    """Process-lifetime exclusive writer lease backed by an OS file lock."""

    def __init__(
        self, *, database: Path, lock_path: Path, file_descriptor: int,
        owner: dict[str, Any],
    ) -> None:
        self.database = database
        self.lock_path = lock_path
        self.owner = dict(owner)
        self._file_descriptor: int | None = file_descriptor

    @property
    def active(self) -> bool:
        return self._file_descriptor is not None

    def assert_matches(self, database: str | Path, *, run_id: str) -> None:
        self.assert_database(database)
        if str(self.owner.get("run_id") or "") != str(run_id):
            raise ValueError("trading status remediation database lease run_id changed")

    def assert_database(self, database: str | Path) -> None:
        if not self.active:
            raise ValueError("trading status remediation database lease is released")
        if Path(database).resolve() != self.database:
            raise ValueError("trading status remediation database lease database changed")

    def release(self) -> None:
        file_descriptor = self._file_descriptor
        if file_descriptor is None:
            return
        self._file_descriptor = None
        try:
            _unlock_database_lease_file(file_descriptor)
        finally:
            os.close(file_descriptor)

    def __enter__(self) -> "TradingStatusDatabaseLease":
        if not self.active:
            raise ValueError("trading status remediation database lease is released")
        return self

    def __exit__(self, _error_type, _error, _traceback) -> None:
        self.release()


def trading_status_database_lease_path(database: str | Path) -> Path:
    """Return the fixed database-scoped sidecar; callers must never replace it."""

    database_path = Path(database).resolve()
    return database_path.with_name(
        f"{database_path.name}.trading-status-remediation.lock"
    )


def acquire_trading_status_database_lease(
    database: str | Path, *, run_id: str, holder_kind: str,
) -> TradingStatusDatabaseLease:
    """Acquire the non-blocking cross-process writer lease for one database."""

    database_path = Path(database).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"market database not found: {database_path}")
    normalized_run_id = str(run_id or "").strip()
    normalized_holder_kind = str(holder_kind or "").strip()
    if not normalized_run_id:
        raise ValueError("database lease run_id is required")
    if not normalized_holder_kind:
        raise ValueError("database lease holder_kind is required")
    lock_path = trading_status_database_lease_path(database_path)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    file_descriptor = os.open(lock_path, flags, 0o600)
    os.set_inheritable(file_descriptor, False)
    try:
        _lock_database_lease_file(file_descriptor)
    except OSError as error:
        owner = _read_database_lease_owner(file_descriptor)
        os.close(file_descriptor)
        if _is_database_lease_busy_error(error):
            raise TradingStatusDatabaseLeaseBusyError(
                database_path, lock_path, owner,
            ) from error
        raise
    owner = {
        "lease_version": DATABASE_LEASE_VERSION,
        "lease_id": uuid.uuid4().hex,
        "database": str(database_path),
        "run_id": normalized_run_id,
        "holder_kind": normalized_holder_kind,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "acquired_at": _utc_now(),
    }
    try:
        _write_database_lease_owner(file_descriptor, owner)
    except Exception:
        try:
            _unlock_database_lease_file(file_descriptor)
        finally:
            os.close(file_descriptor)
        raise
    return TradingStatusDatabaseLease(
        database=database_path,
        lock_path=lock_path,
        file_descriptor=file_descriptor,
        owner=owner,
    )


def inspect_trading_status_database_lease(database: str | Path) -> dict[str, Any]:
    """Probe the OS lock; persisted owner metadata is never liveness authority."""

    database_path = Path(database).resolve()
    lock_path = trading_status_database_lease_path(database_path)
    if not lock_path.is_file():
        return {
            "status": "available", "database": str(database_path),
            "lock_path": str(lock_path), "owner": None,
        }
    flags = os.O_RDWR
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    file_descriptor = os.open(lock_path, flags)
    os.set_inheritable(file_descriptor, False)
    try:
        try:
            _lock_database_lease_file(file_descriptor)
        except OSError as error:
            if not _is_database_lease_busy_error(error):
                raise
            return {
                "status": "busy", "database": str(database_path),
                "lock_path": str(lock_path),
                "owner": _read_database_lease_owner(file_descriptor),
            }
        _unlock_database_lease_file(file_descriptor)
        return {
            "status": "available", "database": str(database_path),
            "lock_path": str(lock_path), "owner": None,
        }
    finally:
        os.close(file_descriptor)


def is_batch_pause_requested(checkpoint_path: str | Path) -> bool:
    """Read the controller-owned pause sidecar without changing the checkpoint."""

    return _pause_marker(Path(checkpoint_path).resolve()).is_file()


def _lock_database_lease_file(file_descriptor: int) -> None:
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_database_lease_file(file_descriptor: int) -> None:
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_UN)


def _is_database_lease_busy_error(error: OSError) -> bool:
    portable_busy = {errno.EACCES, errno.EAGAIN}
    if hasattr(errno, "EDEADLK"):
        portable_busy.add(errno.EDEADLK)
    return bool(
        getattr(error, "errno", None) in portable_busy
        or (
            os.name == "nt"
            and getattr(error, "winerror", None) in {32, 33, 36}
        )
    )


def _write_database_lease_owner(
    file_descriptor: int, owner: dict[str, Any],
) -> None:
    encoded = (
        json.dumps(owner, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if len(encoded) > _DATABASE_LEASE_OWNER_LIMIT_BYTES:
        raise ValueError("database lease owner metadata is too large")
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    os.write(file_descriptor, b"\x00" + encoded)
    os.ftruncate(file_descriptor, len(encoded) + 1)
    os.fsync(file_descriptor)


def _read_database_lease_owner(file_descriptor: int) -> dict[str, Any] | None:
    try:
        os.lseek(file_descriptor, 1, os.SEEK_SET)
        encoded = os.read(file_descriptor, _DATABASE_LEASE_OWNER_LIMIT_BYTES)
        parsed = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _write_candidate_manifest(
    store: AShareGovernanceStore, path: Path, *, current_symbols_only: bool,
    page_size: int, expected_candidate_set_hash: str,
    expected_candidate_count: int,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    if temporary.exists():
        raise ValueError(f"temporary candidate manifest already exists: {temporary}")
    candidate_digest = hashlib.sha256()
    file_digest = hashlib.sha256()
    count = 0
    after_symbol = ""
    after_trade_date = ""
    try:
        with temporary.open("xb") as stream:
            while True:
                page = store.scan_trading_status_repair_candidates(
                    after_symbol=after_symbol,
                    after_trade_date=after_trade_date,
                    limit=page_size,
                    current_symbols_only=current_symbols_only,
                )
                if not page:
                    break
                for candidate in page:
                    record = {
                        "symbol": candidate["symbol"],
                        "trade_date": candidate["trade_date"],
                        "repairability": candidate["repairability"],
                        "reason": candidate["reason"],
                        "evidence_fingerprint": candidate["evidence_fingerprint"],
                    }
                    encoded = (
                        json.dumps(
                            record, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"),
                        ) + "\n"
                    ).encode("utf-8")
                    stream.write(encoded)
                    file_digest.update(encoded)
                    candidate_digest.update(
                        str(candidate["evidence_fingerprint"]).encode("ascii")
                    )
                    count += 1
                last = page[-1]
                after_symbol = str(last["symbol"])
                after_trade_date = str(last["trade_date"])
                if len(page) < page_size:
                    break
        if (
            candidate_digest.hexdigest() != str(expected_candidate_set_hash)
            or count != int(expected_candidate_count)
        ):
            raise ValueError(
                "candidate set changed while creating immutable manifest; rerun preview"
            )
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"candidate_count": count, "file_hash": file_digest.hexdigest()}


def _read_manifest_page(
    path: Path, *, byte_offset: int, limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    records: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        stream.seek(max(0, int(byte_offset)))
        for _ in range(max(1, int(limit))):
            line = stream.readline()
            if not line:
                break
            record = json.loads(line.decode("utf-8"))
            record["_end_offset"] = stream.tell()
            records.append(record)
        eof = stream.read(1) == b""
    return records, eof


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _replace_with_windows_sharing_retry(source: Path, destination: Path) -> None:
    """Replace atomically, retrying only transient Windows sharing conflicts."""

    for attempt in range(_WINDOWS_SHARING_RETRY_ATTEMPTS):
        try:
            source.replace(destination)
            return
        except PermissionError as error:
            sharing_conflict = (
                os.name == "nt"
                and getattr(error, "winerror", None) in {5, 32, 33}
            )
            if not sharing_conflict or attempt + 1 >= _WINDOWS_SHARING_RETRY_ATTEMPTS:
                raise
            time.sleep(_WINDOWS_SHARING_RETRY_DELAY_SECONDS)


def _write_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _replace_with_windows_sharing_retry(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _database_lease_for_call(
    database: str | Path, *, run_id: str,
    database_lease: TradingStatusDatabaseLease | None,
    holder_kind: str,
) -> tuple[TradingStatusDatabaseLease, bool]:
    if database_lease is not None:
        database_lease.assert_matches(database, run_id=run_id)
        return database_lease, False
    return (
        acquire_trading_status_database_lease(
            database, run_id=run_id, holder_kind=holder_kind,
        ),
        True,
    )


def prepare_batch_remediation(
    database: str | Path, *, expected_candidate_set_hash: str,
    run_id: str, operator: str, checkpoint_path: str | Path,
    confirmation: str, current_symbols_only: bool = True,
    page_size: int = 1_000, max_writes: int = 0,
    authorized_total_writes: int | None = None,
    commit_batch_size: int | None = None,
    authorization_reference: str = "",
    database_lease: TradingStatusDatabaseLease | None = None,
) -> dict[str, Any]:
    """Freeze authorization under the database-scoped exclusive writer lease."""

    lease, owns_lease = _database_lease_for_call(
        database,
        run_id=run_id,
        database_lease=database_lease,
        holder_kind="python_api_prepare",
    )
    try:
        return _prepare_batch_remediation_under_lease(
            database,
            expected_candidate_set_hash=expected_candidate_set_hash,
            run_id=run_id,
            operator=operator,
            checkpoint_path=checkpoint_path,
            confirmation=confirmation,
            current_symbols_only=current_symbols_only,
            page_size=page_size,
            max_writes=max_writes,
            authorized_total_writes=authorized_total_writes,
            commit_batch_size=commit_batch_size,
            authorization_reference=authorization_reference,
        )
    finally:
        if owns_lease:
            lease.release()


def _prepare_batch_remediation_under_lease(
    database: str | Path, *, expected_candidate_set_hash: str,
    run_id: str, operator: str, checkpoint_path: str | Path,
    confirmation: str, current_symbols_only: bool = True,
    page_size: int = 1_000, max_writes: int = 0,
    authorized_total_writes: int | None = None,
    commit_batch_size: int | None = None,
    authorization_reference: str = "",
) -> dict[str, Any]:
    """Freeze v2 authorization and prepare one immutable candidate manifest."""

    context = _v2_request_context(
        database, expected_candidate_set_hash=expected_candidate_set_hash,
        run_id=run_id, operator=operator, checkpoint_path=checkpoint_path,
        confirmation=confirmation, current_symbols_only=current_symbols_only,
    )
    checkpoint = context["checkpoint"]
    manifest = context["manifest"]
    state = _load_checkpoint(checkpoint)
    if state is not None:
        _validate_checkpoint_version(state)
        _validate_v2_checkpoint(
            state, database_path=context["database_path"],
            expected_candidate_set_hash=context["expected_candidate_set_hash"],
            run_id=context["run_id"], operator=context["operator"],
            current_symbols_only=current_symbols_only,
            authorized_total_writes=authorized_total_writes,
            commit_batch_size=commit_batch_size,
            authorization_reference=authorization_reference,
        )
        if Path(str(state.get("candidate_manifest") or "")).resolve() != manifest:
            raise ValueError("checkpoint candidate manifest path changed")
        if state.get("candidate_manifest_file_hash"):
            _validate_prepared_manifest(state, manifest)
            return state
    else:
        total_writes, batch_size = _new_authorization_limits(
            max_writes=max_writes,
            authorized_total_writes=authorized_total_writes,
            commit_batch_size=commit_batch_size,
            page_size=page_size,
        )
        now = _utc_now()
        state = {
            "checkpoint_version": CHECKPOINT_VERSION,
            "status": "initializing",
            "run_id": context["run_id"],
            "operator": context["operator"],
            "authorized_by": context["operator"],
            "authorization_reference": str(
                authorization_reference or "explicit_confirmation_phrase"
            ),
            "authorization_created_at": now,
            "authorized_total_writes": total_writes,
            "commit_batch_size": batch_size,
            "database": str(context["database_path"]),
            "scope": "current_symbols" if current_symbols_only else "all_symbols",
            "expected_candidate_set_hash": context["expected_candidate_set_hash"],
            "expected_candidate_count": 0,
            "preflight_repairability_counts": {},
            "preflight_reason_counts": {},
            "candidate_manifest": str(manifest),
            "candidate_manifest_file_hash": "",
            "candidate_manifest_byte_offset": 0,
            "cursor": {"symbol": "", "trade_date": ""},
            "scanned_candidates": 0,
            "auto_candidates_seen": 0,
            "authorization_consumed": 0,
            "manual_candidates_seen": 0,
            "written": 0,
            "newly_written": 0,
            "recovered_written": 0,
            "skipped": 0,
            "evidence_mismatch_skipped": 0,
            "reason_counts": {},
            "batch_count": 0,
            "batches": [],
            "pause_requested": False,
            "last_error": None,
            "failure_count": 0,
            "failed_at": None,
            "failed_batch_number": None,
            "failed_cursor": None,
            "interruption_count": 0,
            "last_interruption": None,
            "started_at": None,
            "updated_at": now,
            "finished_at": None,
        }
        _create_checkpoint(checkpoint, state)

    state["status"] = "initializing"
    state["last_error"] = None
    state["failed_at"] = None
    state["failed_batch_number"] = None
    state["failed_cursor"] = None
    state["updated_at"] = _utc_now()
    _write_checkpoint(checkpoint, state)
    try:
        preview = build_preview_report(
            context["database_path"],
            current_symbols_only=current_symbols_only,
            page_size=max(1, min(int(page_size), 10_000)),
            sample_limit=0,
        )
        if preview["candidate_set_hash"] != context["expected_candidate_set_hash"]:
            raise ValueError(
                "candidate set hash mismatch; rerun read-only preview before applying"
            )
        auto_candidate_count = int(
            preview["repairability_counts"].get("auto_repairable", 0)
        )
        if int(state["authorized_total_writes"]) > auto_candidate_count:
            raise ValueError(
                "authorized_total_writes exceeds the read-only auto-repairable count"
            )
        if manifest.exists():
            manifest_summary = _inspect_candidate_manifest(manifest)
            if (
                manifest_summary["candidate_set_hash"]
                != context["expected_candidate_set_hash"]
                or int(manifest_summary["candidate_count"])
                != int(preview["candidate_count"])
            ):
                raise ValueError(
                    "existing candidate manifest does not match the frozen candidate set"
                )
        else:
            manifest_summary = _write_candidate_manifest(
                AShareGovernanceStore(context["database_path"]),
                manifest,
                current_symbols_only=current_symbols_only,
                page_size=max(1, min(int(page_size), 10_000)),
                expected_candidate_set_hash=context["expected_candidate_set_hash"],
                expected_candidate_count=int(preview["candidate_count"]),
            )
        state["expected_candidate_count"] = int(preview["candidate_count"])
        state["preflight_repairability_counts"] = preview["repairability_counts"]
        state["preflight_reason_counts"] = preview["reason_counts"]
        state["candidate_manifest_file_hash"] = manifest_summary["file_hash"]
        state["status"] = "queued"
        state["pause_requested"] = _pause_requested(checkpoint, state)
        if state["pause_requested"]:
            state["status"] = "paused_by_user"
        state["updated_at"] = _utc_now()
        _write_checkpoint(checkpoint, state)
        return state
    except Exception as error:
        _record_failure(checkpoint, state, error)
        raise


def run_batch_remediation(
    database: str | Path, *, expected_candidate_set_hash: str,
    run_id: str, operator: str, checkpoint_path: str | Path,
    confirmation: str, current_symbols_only: bool = True,
    page_size: int = 1_000, max_writes: int = 0,
    authorized_total_writes: int | None = None,
    commit_batch_size: int | None = None,
    authorization_reference: str = "",
    database_lease: TradingStatusDatabaseLease | None = None,
) -> dict[str, Any]:
    """Apply or resume while holding one database-scoped writer lease."""

    lease, owns_lease = _database_lease_for_call(
        database,
        run_id=run_id,
        database_lease=database_lease,
        holder_kind="python_api_run",
    )
    try:
        return _run_batch_remediation_under_lease(
            database,
            expected_candidate_set_hash=expected_candidate_set_hash,
            run_id=run_id,
            operator=operator,
            checkpoint_path=checkpoint_path,
            confirmation=confirmation,
            current_symbols_only=current_symbols_only,
            page_size=page_size,
            max_writes=max_writes,
            authorized_total_writes=authorized_total_writes,
            commit_batch_size=commit_batch_size,
            authorization_reference=authorization_reference,
        )
    finally:
        if owns_lease:
            lease.release()


def _run_batch_remediation_under_lease(
    database: str | Path, *, expected_candidate_set_hash: str,
    run_id: str, operator: str, checkpoint_path: str | Path,
    confirmation: str, current_symbols_only: bool = True,
    page_size: int = 1_000, max_writes: int = 0,
    authorized_total_writes: int | None = None,
    commit_batch_size: int | None = None,
    authorization_reference: str = "",
) -> dict[str, Any]:
    """Apply or resume a v2 run without exceeding its frozen authorization."""

    state = _prepare_batch_remediation_under_lease(
        database,
        expected_candidate_set_hash=expected_candidate_set_hash,
        run_id=run_id,
        operator=operator,
        checkpoint_path=checkpoint_path,
        confirmation=confirmation,
        current_symbols_only=current_symbols_only,
        page_size=page_size,
        max_writes=max_writes,
        authorized_total_writes=authorized_total_writes,
        commit_batch_size=commit_batch_size,
        authorization_reference=authorization_reference,
    )
    checkpoint = Path(checkpoint_path).resolve()
    manifest = Path(str(state["candidate_manifest"])).resolve()
    if state["status"] in _TERMINAL_STATUSES:
        return state
    if state["status"] not in _RESUMABLE_STATUSES:
        raise ValueError(f"checkpoint is not runnable from status={state['status']}")
    if _pause_requested(checkpoint, state):
        state["status"] = "paused_by_user"
        state["pause_requested"] = True
        state["updated_at"] = _utc_now()
        _write_checkpoint(checkpoint, state)
        return state

    invocation_limit = max(0, int(max_writes))
    invocation_requested = 0
    reason_counts = Counter(state.get("reason_counts") or {})
    state["status"] = "running"
    state["pause_requested"] = False
    state["last_error"] = None
    state["failed_at"] = None
    state["failed_batch_number"] = None
    state["failed_cursor"] = None
    state["finished_at"] = None
    if not state.get("started_at"):
        state["started_at"] = _utc_now()
    state["updated_at"] = _utc_now()
    _write_checkpoint(checkpoint, state)
    store = AShareGovernanceStore(Path(database).resolve())
    try:
        while True:
            if _pause_requested(checkpoint, state):
                state["status"] = "paused_by_user"
                state["pause_requested"] = True
                state["updated_at"] = _utc_now()
                _write_checkpoint(checkpoint, state)
                return state
            page, manifest_eof = _read_manifest_page(
                manifest,
                byte_offset=int(state.get("candidate_manifest_byte_offset") or 0),
                limit=int(state["commit_batch_size"]),
            )
            if not page:
                return _finish_completed(checkpoint, state)

            considered: list[dict[str, Any]] = []
            authorization_blocked = False
            invocation_paused = False
            remaining_authorization = max(
                0,
                int(state["authorized_total_writes"])
                - int(state.get("auto_candidates_seen") or 0),
            )
            page_auto_count = 0
            for manifest_candidate in page:
                is_auto = manifest_candidate["repairability"] == "auto_repairable"
                if is_auto and page_auto_count >= remaining_authorization:
                    authorization_blocked = True
                    break
                if (
                    is_auto and invocation_limit
                    and invocation_requested >= invocation_limit
                ):
                    invocation_paused = True
                    break
                considered.append(manifest_candidate)
                reason_counts[str(manifest_candidate["reason"])] += 1
                if is_auto:
                    page_auto_count += 1
                    invocation_requested += 1

            if considered:
                batch_started_at = _utc_now()
                batch_started_monotonic = time.monotonic()
                current_candidates = store.load_trading_status_repair_candidates([
                    (str(item["symbol"]), str(item["trade_date"]))
                    for item in considered
                ])
                current_by_key = {
                    (str(item["symbol"]), str(item["trade_date"])): item
                    for item in current_candidates
                }
                auto_candidates: list[dict[str, Any]] = []
                recovered_keys: list[str] = []
                evidence_mismatches = 0
                for item in considered:
                    if item["repairability"] != "auto_repairable":
                        continue
                    current = current_by_key.get(
                        (str(item["symbol"]), str(item["trade_date"]))
                    )
                    if _is_recovered_write(
                        current, item, run_id=str(state["run_id"]),
                    ):
                        recovered_keys.append(_candidate_key(item))
                        continue
                    if (
                        current is None
                        or current["evidence_fingerprint"] != item["evidence_fingerprint"]
                    ):
                        evidence_mismatches += 1
                        continue
                    auto_candidates.append(current)
                applied = store.apply_trading_status_repair_batch(
                    auto_candidates,
                    run_id=str(state["run_id"]),
                    operator=str(state["operator"]),
                )
                newly_written_keys = list(applied.get("written_keys") or [])
                successful_keys = set(newly_written_keys) | set(recovered_keys)
                ordered_written_keys = [
                    _candidate_key(item)
                    for item in considered
                    if _candidate_key(item) in successful_keys
                ]
                written_key_digest = hashlib.sha256()
                for key in ordered_written_keys:
                    written_key_digest.update(key.encode("ascii"))
                manifest_auto_count = sum(
                    1 for item in considered
                    if item["repairability"] == "auto_repairable"
                )
                newly_written = int(applied["written"])
                recovered_written = len(recovered_keys)
                skipped = int(applied["skipped"]) + evidence_mismatches
                state["scanned_candidates"] += len(considered)
                state["auto_candidates_seen"] += manifest_auto_count
                state["authorization_consumed"] = int(state["auto_candidates_seen"])
                state["manual_candidates_seen"] += len(considered) - manifest_auto_count
                state["written"] += newly_written + recovered_written
                state["newly_written"] += newly_written
                state["recovered_written"] += recovered_written
                state["skipped"] += skipped
                state["evidence_mismatch_skipped"] += evidence_mismatches
                state["batch_count"] += 1
                last = considered[-1]
                state["cursor"] = {
                    "symbol": str(last["symbol"]),
                    "trade_date": str(last["trade_date"]),
                }
                state["candidate_manifest_byte_offset"] = int(last["_end_offset"])
                duration_seconds = max(0.0, time.monotonic() - batch_started_monotonic)
                throughput = (
                    round(len(considered) / duration_seconds, 3)
                    if duration_seconds > 0 else None
                )
                pause_after_commit = _pause_requested(checkpoint, state)
                state["pause_requested"] = pause_after_commit
                state["batches"].append({
                    "batch_number": int(state["batch_count"]),
                    "candidate_count": len(considered),
                    "auto_candidate_count": manifest_auto_count,
                    "newly_written": newly_written,
                    "recovered_written": recovered_written,
                    "written": newly_written + recovered_written,
                    "skipped": skipped,
                    "evidence_mismatch_skipped": evidence_mismatches,
                    "written_key_hash": written_key_digest.hexdigest(),
                    "skipped_key_samples": list(applied["skipped_key_samples"]),
                    "cursor": dict(state["cursor"]),
                    "started_at": batch_started_at,
                    "committed_at": _utc_now(),
                    "duration_seconds": round(duration_seconds, 6),
                    "throughput_candidates_per_second": throughput,
                })
                state["reason_counts"] = dict(sorted(reason_counts.items()))
                state["status"] = "paused_by_user" if pause_after_commit else "running"
                state["updated_at"] = _utc_now()
                _write_checkpoint(checkpoint, state)
                if pause_after_commit:
                    return state

            if authorization_blocked:
                state["status"] = "authorization_exhausted"
                state["finished_at"] = _utc_now()
                state["updated_at"] = _utc_now()
                _write_checkpoint(checkpoint, state)
                return state
            if invocation_paused:
                state["status"] = "paused_max_writes"
                state["updated_at"] = _utc_now()
                _write_checkpoint(checkpoint, state)
                return state
            if manifest_eof and len(considered) == len(page):
                return _finish_completed(checkpoint, state)
    except Exception as error:
        latest = _load_checkpoint(checkpoint) or state
        _record_failure(checkpoint, latest, error)
        raise


def request_batch_pause(checkpoint_path: str | Path) -> dict[str, Any]:
    """Write only the controller sidecar; the lease holder owns the checkpoint."""

    checkpoint = Path(checkpoint_path).resolve()
    state = _required_v2_checkpoint(checkpoint)
    if state["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"terminal remediation run cannot be paused: {state['status']}")
    _write_pause_marker(checkpoint)
    latest = _required_v2_checkpoint(checkpoint)
    latest["pause_requested"] = True
    if latest["status"] == "queued":
        latest["status"] = "paused_by_user"
    elif latest["status"] == "running":
        latest["status"] = "pause_requested"
    latest["updated_at"] = _utc_now()
    return latest


def clear_batch_pause(
    checkpoint_path: str | Path, *,
    database_lease: TradingStatusDatabaseLease | None = None,
) -> dict[str, Any]:
    """Clear only the pause request; the frozen authorization is unchanged."""

    checkpoint = Path(checkpoint_path).resolve()
    state = _required_v2_checkpoint(checkpoint)
    lease, owns_lease = _database_lease_for_call(
        str(state.get("database") or ""),
        run_id=str(state.get("run_id") or ""),
        database_lease=database_lease,
        holder_kind="pause_clear",
    )
    try:
        _pause_marker(checkpoint).unlink(missing_ok=True)
        latest = _required_v2_checkpoint(checkpoint)
        latest["pause_requested"] = False
        if latest["status"] in {"paused_by_user", "pause_requested"}:
            latest["status"] = "queued"
        latest["updated_at"] = _utc_now()
        _write_checkpoint(checkpoint, latest)
        return latest
    finally:
        if owns_lease:
            lease.release()


def mark_batch_interrupted(
    checkpoint_path: str | Path,
    reason: str = "background remediation worker interrupted",
    *, database_lease: TradingStatusDatabaseLease | None = None,
) -> dict[str, Any]:
    """Atomically mark a non-terminal v2 run failed without changing authorization.

    A terminal run is returned unchanged.  An already failed run is also returned
    unchanged so an earlier diagnostic is never overwritten by shutdown cleanup.
    The resulting ``failed`` checkpoint remains resumable only through an explicit
    call to :func:`run_batch_remediation` with the original frozen parameters.
    """

    checkpoint = Path(checkpoint_path).resolve()
    state = _required_v2_checkpoint(checkpoint)
    if database_lease is not None:
        database_lease.assert_database(str(state.get("database") or ""))
        lease, owns_lease = database_lease, False
    else:
        lease, owns_lease = _database_lease_for_call(
            str(state.get("database") or ""),
            run_id=str(state.get("run_id") or ""),
            database_lease=None,
            holder_kind="interruption_marker",
        )
    try:
        return _mark_batch_interrupted_under_lease(
            checkpoint, reason=reason,
        )
    finally:
        if owns_lease:
            lease.release()


def _mark_batch_interrupted_under_lease(
    checkpoint: Path,
    reason: str = "background remediation worker interrupted",
) -> dict[str, Any]:
    state = _required_v2_checkpoint(checkpoint)
    if state["status"] in _TERMINAL_STATUSES or state["status"] == "failed":
        return state
    normalized_reason = str(reason).strip() or "background remediation worker interrupted"
    interrupted_at = _utc_now()
    prior_status = str(state.get("status") or "unknown")
    cursor = dict(state.get("cursor") or {"symbol": "", "trade_date": ""})
    failed_batch_number = int(state.get("batch_count") or 0) + 1
    state["status"] = "failed"
    state["last_error"] = f"InterruptedError: {normalized_reason}"
    state["failure_count"] = int(state.get("failure_count") or 0) + 1
    state["failed_at"] = interrupted_at
    state["failed_batch_number"] = failed_batch_number
    state["failed_cursor"] = cursor
    state["finished_at"] = interrupted_at
    state["updated_at"] = interrupted_at
    state["interruption_count"] = int(state.get("interruption_count") or 0) + 1
    state["last_interruption"] = {
        "reason": normalized_reason,
        "interrupted_at": interrupted_at,
        "prior_status": prior_status,
        "cursor": cursor,
        "batch_number": failed_batch_number,
    }
    _write_checkpoint(checkpoint, state)
    return state


def _v2_request_context(
    database: str | Path, *, expected_candidate_set_hash: str,
    run_id: str, operator: str, checkpoint_path: str | Path,
    confirmation: str, current_symbols_only: bool,
) -> dict[str, Any]:
    if str(confirmation) != CONFIRMATION_PHRASE:
        raise ValueError("exact trading status repair confirmation phrase is required")
    normalized_run_id = str(run_id).strip()
    normalized_operator = str(operator).strip()
    normalized_hash = str(expected_candidate_set_hash).strip()
    if not normalized_run_id:
        raise ValueError("run_id is required")
    if not normalized_operator:
        raise ValueError("operator is required")
    if not normalized_hash:
        raise ValueError("expected candidate set hash is required")
    database_path = Path(database).resolve()
    checkpoint = Path(checkpoint_path).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"market database not found: {database_path}")
    if checkpoint == database_path:
        raise ValueError("checkpoint path must not be the market database")
    return {
        "database_path": database_path,
        "checkpoint": checkpoint,
        "manifest": checkpoint.with_name(f"{checkpoint.name}.candidates.jsonl"),
        "expected_candidate_set_hash": normalized_hash,
        "run_id": normalized_run_id,
        "operator": normalized_operator,
        "scope": "current_symbols" if current_symbols_only else "all_symbols",
    }


def _new_authorization_limits(
    *, max_writes: int, authorized_total_writes: int | None,
    commit_batch_size: int | None, page_size: int,
) -> tuple[int, int]:
    total_writes = int(
        authorized_total_writes
        if authorized_total_writes is not None else max_writes
    )
    if total_writes < 1:
        raise ValueError("authorized_total_writes must be a positive integer")
    if total_writes > MAX_AUTHORIZED_TOTAL_WRITES:
        raise ValueError(
            "authorized_total_writes must not exceed "
            f"{MAX_AUTHORIZED_TOTAL_WRITES}"
        )
    batch_size = int(
        commit_batch_size
        if commit_batch_size is not None else min(max(1, int(page_size)), 1_000)
    )
    if batch_size < 1 or batch_size > 1_000:
        raise ValueError("commit_batch_size must be between 1 and 1000")
    return total_writes, batch_size


def _inspect_candidate_manifest(path: Path) -> dict[str, Any]:
    candidate_digest = hashlib.sha256()
    file_digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for line in stream:
            file_digest.update(line)
            record = json.loads(line.decode("utf-8"))
            candidate_digest.update(
                str(record["evidence_fingerprint"]).encode("ascii")
            )
            count += 1
    return {
        "candidate_count": count,
        "candidate_set_hash": candidate_digest.hexdigest(),
        "file_hash": file_digest.hexdigest(),
    }


def _validate_prepared_manifest(state: dict[str, Any], manifest: Path) -> None:
    if not manifest.is_file():
        raise FileNotFoundError(f"candidate manifest not found: {manifest}")
    if _file_hash(manifest) != str(state.get("candidate_manifest_file_hash") or ""):
        raise ValueError("candidate manifest content changed after checkpoint creation")


def _required_v2_checkpoint(path: Path) -> dict[str, Any]:
    state = _load_checkpoint(path)
    if state is None:
        raise FileNotFoundError(f"trading status remediation checkpoint not found: {path}")
    _validate_checkpoint_version(state)
    return state


def _validate_checkpoint_version(state: dict[str, Any]) -> None:
    version = str(state.get("checkpoint_version") or LEGACY_CHECKPOINT_VERSION)
    if version == LEGACY_CHECKPOINT_VERSION:
        raise ValueError(
            "legacy checkpoint v1 is read-only and cannot be resumed by the v2 writer"
        )
    if version != CHECKPOINT_VERSION:
        raise ValueError(f"unsupported trading status remediation checkpoint version: {version}")


def _validate_v2_checkpoint(
    state: dict[str, Any], *, database_path: Path,
    expected_candidate_set_hash: str, run_id: str, operator: str,
    current_symbols_only: bool,
    authorized_total_writes: int | None,
    commit_batch_size: int | None,
    authorization_reference: str,
) -> None:
    expected_scope = "current_symbols" if current_symbols_only else "all_symbols"
    checks = {
        "database": str(database_path),
        "run_id": run_id,
        "operator": operator,
        "scope": expected_scope,
        "expected_candidate_set_hash": expected_candidate_set_hash,
    }
    if authorized_total_writes is not None:
        checks["authorized_total_writes"] = int(authorized_total_writes)
    if commit_batch_size is not None:
        checks["commit_batch_size"] = int(commit_batch_size)
    if str(authorization_reference).strip():
        checks["authorization_reference"] = str(authorization_reference).strip()
    mismatches = [
        key for key, expected in checks.items()
        if str(state.get(key)) != str(expected)
    ]
    if mismatches:
        raise ValueError(
            "checkpoint does not match requested run or frozen authorization: "
            + ",".join(mismatches)
        )
    total = int(state.get("authorized_total_writes") or 0)
    batch_size = int(state.get("commit_batch_size") or 0)
    if (
        total < 1
        or total > MAX_AUTHORIZED_TOTAL_WRITES
        or batch_size < 1
        or batch_size > 1_000
    ):
        raise ValueError("checkpoint contains invalid frozen authorization limits")
    if int(state.get("auto_candidates_seen") or 0) > total:
        raise ValueError("checkpoint authorization consumption exceeds its frozen total")


def _create_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.initializing.tmp"
    )
    content = (
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ValueError(f"checkpoint already exists: {path}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _pause_marker(checkpoint: Path) -> Path:
    return checkpoint.with_name(f"{checkpoint.name}.pause.json")


def _write_pause_marker(checkpoint: Path) -> None:
    marker = _pause_marker(checkpoint)
    temporary = marker.with_name(
        f"{marker.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps({"requested_at": _utc_now()}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _replace_with_windows_sharing_retry(temporary, marker)
    finally:
        temporary.unlink(missing_ok=True)


def _pause_requested(checkpoint: Path, state: dict[str, Any]) -> bool:
    return _pause_marker(checkpoint).is_file() or bool(state.get("pause_requested"))


def _record_failure(
    checkpoint: Path, state: dict[str, Any], error: Exception,
) -> None:
    state["status"] = "failed"
    state["last_error"] = f"{type(error).__name__}: {error}"
    state["failure_count"] = int(state.get("failure_count") or 0) + 1
    state["failed_at"] = _utc_now()
    state["failed_batch_number"] = int(state.get("batch_count") or 0) + 1
    state["failed_cursor"] = dict(
        state.get("cursor") or {"symbol": "", "trade_date": ""}
    )
    state["finished_at"] = state["failed_at"]
    state["updated_at"] = state["failed_at"]
    try:
        _write_checkpoint(checkpoint, state)
    except Exception:
        pass


def _finish_completed(checkpoint: Path, state: dict[str, Any]) -> dict[str, Any]:
    processed = int(state["scanned_candidates"])
    expected = int(state["expected_candidate_count"])
    if processed != expected:
        state["completion_consistency"] = "candidate_drift_detected"
        _record_failure(
            checkpoint,
            state,
            RuntimeError(
                "completion candidate count mismatch: "
                f"processed={processed}, expected={expected}"
            ),
        )
        return state
    state["status"] = "completed"
    state["finished_at"] = _utc_now()
    state["completion_consistency"] = "matched"
    state["updated_at"] = _utc_now()
    _write_checkpoint(checkpoint, state)
    return state


def _candidate_key(candidate: dict[str, Any]) -> str:
    return f"{candidate['symbol']}|{candidate['trade_date']}"


def _is_recovered_write(
    current: dict[str, Any] | None,
    manifest_candidate: dict[str, Any], *, run_id: str,
) -> bool:
    if current is None:
        return False
    before = dict(current.get("before") or {})
    evidence = dict(before.get("evidence") or {})
    return bool(
        str(before.get("source") or "")
        == "admin_batch_remediation:canonical_positive_bar"
        and str(evidence.get("run_id") or "") == str(run_id)
        and str(evidence.get("candidate_fingerprint") or "")
        == str(manifest_candidate.get("evidence_fingerprint") or "")
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply checkpointed trading-status remediation after approval.",
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expected-candidate-set-hash", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--all-symbols", action="store_true")
    parser.add_argument("--page-size", type=int, default=1_000)
    parser.add_argument(
        "--authorized-total-writes", type=int,
        help="Immutable total write authorization for a new v2 run.",
    )
    parser.add_argument(
        "--commit-batch-size", type=int,
        help="Atomic commit size for a new v2 run; must be between 1 and 1000.",
    )
    parser.add_argument("--authorization-reference", default="")
    parser.add_argument(
        "--max-writes", type=int, default=0,
        help=(
            "Optional invocation pause limit. For a legacy caller creating a new run, "
            "it is also the frozen total when --authorized-total-writes is omitted."
        ),
    )
    arguments = parser.parse_args()
    if (
        not arguments.checkpoint.resolve().is_file()
        and not str(arguments.authorization_reference or "").strip()
    ):
        parser.error(
            "--authorization-reference is required when creating a new checkpoint"
        )
    try:
        lease = acquire_trading_status_database_lease(
            arguments.database,
            run_id=arguments.run_id,
            holder_kind="cli",
        )
    except TradingStatusDatabaseLeaseBusyError as error:
        parser.exit(3, f"database writer busy: {error}\n")
    try:
        result = run_batch_remediation(
            arguments.database,
            expected_candidate_set_hash=arguments.expected_candidate_set_hash,
            run_id=arguments.run_id, operator=arguments.operator,
            checkpoint_path=arguments.checkpoint,
            confirmation=arguments.confirm,
            current_symbols_only=not arguments.all_symbols,
            page_size=arguments.page_size, max_writes=arguments.max_writes,
            authorized_total_writes=arguments.authorized_total_writes,
            commit_batch_size=arguments.commit_batch_size,
            authorization_reference=arguments.authorization_reference,
            database_lease=lease,
        )
    finally:
        lease.release()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
