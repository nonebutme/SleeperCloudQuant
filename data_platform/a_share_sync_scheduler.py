"""Persistent stage-78.2 scheduler for canonical A-share incremental releases."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from data_platform.providers.a_share_sqlite_repository import (
    _normalize_adjustment,
    _normalize_symbol,
)
from data_platform.storage.a_share_governance_store import AShareGovernanceStore
from data_platform.storage.a_share_market_store import AShareMarketStore
from data_platform.task_ids import new_task_id


SCHEDULER_SCHEMA_VERSION = "78.2.0"
ACTIVE_JOB_STATUSES = ("queued", "running", "validating")
TERMINAL_ITEM_STATUSES = ("completed", "quarantined")


class GlobalRateLimiter:
    """Thread-safe minimum-interval limiter shared by every sync worker."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.requests_per_minute = max(1, int(requests_per_minute))
        self._interval = 60.0 / self.requests_per_minute
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = self._monotonic()
            delay = max(0.0, self._next_allowed_at - now)
            if delay:
                self._sleep(delay)
                now = self._monotonic()
            self._next_allowed_at = max(now, self._next_allowed_at) + self._interval


class AShareSyncScheduler:
    """Queue, resume, validate and atomically publish canonical A-share updates."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        market_store: AShareMarketStore | None = None,
        governance_store: AShareGovernanceStore | None = None,
        provider: Any,
        requests_per_minute: int = 60,
        max_workers: int = 4,
        retry_count: int = 3,
        base_backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.database_path = Path(database_path)
        self.market_store = market_store or AShareMarketStore(self.database_path)
        self.governance_store = governance_store or AShareGovernanceStore(self.database_path)
        self.provider = provider
        self.governance_provider = (
            provider
            if all(
                hasattr(provider, name)
                for name in (
                    "list_symbols",
                    "fetch_trade_calendar",
                    "fetch_index_daily_prices",
                )
            )
            else None
        )
        self.max_workers = max(1, min(int(max_workers), 16))
        self.retry_count = max(1, int(retry_count))
        self.base_backoff_seconds = max(0.0, float(base_backoff_seconds))
        self._sleep = sleep
        self._rate_limiter = GlobalRateLimiter(
            requests_per_minute,
            monotonic=monotonic,
            sleep=sleep,
        )
        self._provider_controls_rate = hasattr(provider, "request_gate")
        if self._provider_controls_rate:
            provider.request_gate = self._rate_limiter.acquire
        self._run_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def ensure_schema(self) -> None:
        self.market_store.ensure_schema()
        self.governance_store.ensure_schema()
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_incremental_sync_jobs (
                    job_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    schedule_key TEXT,
                    status TEXT NOT NULL,
                    target_trade_date TEXT NOT NULL,
                    symbol_scope TEXT NOT NULL,
                    adjustments_json TEXT NOT NULL,
                    total_items INTEGER NOT NULL DEFAULT 0,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    failed_items INTEGER NOT NULL DEFAULT 0,
                    quarantined_items INTEGER NOT NULL DEFAULT 0,
                    rows_written INTEGER NOT NULL DEFAULT 0,
                    quality_report_id TEXT,
                    data_version_id TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE (schedule_key)
                );

                CREATE INDEX IF NOT EXISTS idx_incremental_sync_jobs_status
                    ON market_incremental_sync_jobs (status, created_at);

                CREATE TABLE IF NOT EXISTS market_incremental_sync_items (
                    job_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    adjustment TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    rows_received INTEGER NOT NULL DEFAULT 0,
                    rows_written INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, symbol, adjustment),
                    FOREIGN KEY (job_id)
                        REFERENCES market_incremental_sync_jobs (job_id)
                );

                CREATE INDEX IF NOT EXISTS idx_incremental_sync_items_status
                    ON market_incremental_sync_items (job_id, status, next_attempt_at);

                CREATE TABLE IF NOT EXISTS market_scheduler_settings (
                    scheduler_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    timezone_name TEXT NOT NULL,
                    run_hour INTEGER NOT NULL,
                    run_minute INTEGER NOT NULL,
                    adjustments_json TEXT NOT NULL,
                    requests_per_minute INTEGER NOT NULL,
                    max_workers INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    last_scheduled_for TEXT,
                    last_job_id TEXT,
                    last_tick_at TEXT,
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO market_schema_migrations
                    (schema_version, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    SCHEDULER_SCHEMA_VERSION,
                    "Add persistent incremental sync queue and application scheduler state",
                    _utc_now(),
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO market_scheduler_settings (
                    scheduler_id, enabled, timezone_name, run_hour, run_minute,
                    adjustments_json, requests_per_minute, max_workers,
                    retry_count, updated_at
                ) VALUES ('canonical-a-share', 0, 'Asia/Shanghai', 18, 15,
                          '["raw","qfq","hfq"]', ?, ?, ?, ?)
                """,
                (
                    self._rate_limiter.requests_per_minute,
                    self.max_workers,
                    self.retry_count,
                    _utc_now(),
                ),
            )

    def configure(
        self,
        *,
        enabled: bool,
        run_time: str = "18:15",
        timezone_name: str = "Asia/Shanghai",
        adjustments: Sequence[str] = ("raw", "qfq", "hfq"),
    ) -> dict[str, Any]:
        self.ensure_schema()
        hour, minute = _parse_run_time(run_time)
        modes = _adjustments(adjustments)
        ZoneInfo(timezone_name)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_scheduler_settings
                SET enabled=?, timezone_name=?, run_hour=?, run_minute=?,
                    adjustments_json=?, requests_per_minute=?, max_workers=?,
                    retry_count=?, updated_at=?
                WHERE scheduler_id='canonical-a-share'
                """,
                (
                    1 if enabled else 0,
                    timezone_name,
                    hour,
                    minute,
                    _dump(modes),
                    self._rate_limiter.requests_per_minute,
                    self.max_workers,
                    self.retry_count,
                    _utc_now(),
                ),
            )
        return self.get_status()

    def latest_sync_target(self, date_limit: str | None = None) -> dict[str, Any]:
        self.ensure_schema()
        limit = date.fromisoformat(str(date_limit or date.today().isoformat())).isoformat()
        target = self._latest_open_trade_date(limit)
        return {
            "date_limit": limit,
            "target_trade_date": target,
            "source": "local_trade_calendar",
        }
    def create_job(
        self,
        *,
        target_trade_date: str,
        symbols: Sequence[str] | None = None,
        all_current: bool = False,
        adjustments: Sequence[str] = ("raw", "qfq", "hfq"),
        mode: str = "manual",
        schedule_key: str | None = None,
        start_floor: str = "2015-01-05",
        selected_shards: Sequence[str] = (),
        gap_scan: bool = False,
    ) -> dict[str, Any]:
        self.ensure_schema()
        target = date.fromisoformat(str(target_trade_date)).isoformat()
        modes = _adjustments(adjustments)
        if bool(symbols) == bool(all_current):
            raise ValueError("provide symbols or set all_current=true, but not both")
        tasks = self._build_tasks(
            target_trade_date=target,
            symbols=symbols,
            all_current=all_current,
            adjustments=modes,
            start_floor=start_floor,
            gap_scan=gap_scan,
        )
        if selected_shards:
            selected = {str(item) for item in selected_shards}
            tasks = [task for task in tasks if f"{task['symbol']}|{task['adjustment']}" in selected]
        now = _utc_now()
        job_id = new_task_id("a-share-sync")
        scope = "all_current" if all_current else ",".join(
            sorted({_normalize_symbol(symbol) for symbol in symbols or ()})
        )
        with closing(self._connect()) as connection, connection:
            if schedule_key:
                existing = connection.execute(
                    "SELECT job_id FROM market_incremental_sync_jobs WHERE schedule_key=?",
                    (schedule_key,),
                ).fetchone()
                if existing:
                    return self.get_job(str(existing["job_id"]))
            connection.execute(
                """
                INSERT INTO market_incremental_sync_jobs (
                    job_id, mode, schedule_key, status, target_trade_date,
                    symbol_scope, adjustments_json, total_items,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    str(mode),
                    schedule_key,
                    "queued" if tasks else "completed_noop",
                    target,
                    scope,
                    _dump(modes),
                    len(tasks),
                    now,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO market_incremental_sync_items (
                    job_id, symbol, adjustment, start_date, end_date,
                    status, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                [
                    (
                        job_id,
                        task["symbol"],
                        task["adjustment"],
                        task["start_date"],
                        target,
                        now,
                    )
                    for task in tasks
                ],
            )
            if not tasks:
                connection.execute(
                    """
                    UPDATE market_incremental_sync_jobs
                    SET finished_at=?, updated_at=? WHERE job_id=?
                    """,
                    (now, now, job_id),
                )
        return self.get_job(job_id)

    def preview_job(
        self,
        *,
        target_trade_date: str,
        symbols: Sequence[str] | None = None,
        all_current: bool = False,
        adjustments: Sequence[str] = ("raw", "qfq", "hfq"),
        start_floor: str = "2015-01-05",
        gap_scan: bool = False,
    ) -> dict[str, Any]:
        """Preview one incremental job without persisting work."""

        self.ensure_schema()
        target = date.fromisoformat(str(target_trade_date)).isoformat()
        modes = _adjustments(adjustments)
        if bool(symbols) == bool(all_current):
            raise ValueError("provide symbols or set all_current=true, but not both")
        tasks = self._build_tasks(
            target_trade_date=target,
            symbols=symbols,
            all_current=all_current,
            adjustments=modes,
            start_floor=start_floor,
            gap_scan=gap_scan,
        )
        preview_tasks = [dict(task) for task in tasks[:200]]
        if gap_scan:
            self._attach_gap_date_samples(preview_tasks, target, start_floor)
        return {
            "target_trade_date": target,
            "symbol_scope": "all_current" if all_current else sorted(
                {_normalize_symbol(symbol) for symbol in symbols or ()}
            ),
            "adjustments": modes,
            "request_count": len(tasks),
            "missing_date_count": sum(int(task.get("missing_date_count") or 0) for task in tasks),
            "tasks": [
                {**task, "shard_id": f"{task['symbol']}|{task['adjustment']}"}
                for task in preview_tasks
            ],
            "tasks_truncated": len(tasks) > 200,
            "estimated_seconds": round(
                len(tasks) * 60.0 / self._rate_limiter.requests_per_minute, 1
            ),
        }

    def scan_gap_tasks(
        self, *, target_trade_date: str, start_floor: str,
        symbols: Sequence[str] | None = None, all_current: bool = False,
        adjustments: Sequence[str] = ("raw", "qfq", "hfq"),
    ) -> list[dict[str, Any]]:
        """Return the complete grouped gap set for the active quality engine."""

        self.ensure_schema()
        target = date.fromisoformat(str(target_trade_date)).isoformat()
        if bool(symbols) == bool(all_current):
            raise ValueError("provide symbols or set all_current=true, but not both")
        return self._build_gap_tasks(
            target, symbols, all_current, _adjustments(adjustments), start_floor,
        )
    def run_job(self, job_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with self._run_lock:
            job = self.get_job(job_id, include_items=True)
            if job.get("status") == "not_found":
                return job
            if job.get("status") in {"published", "completed_noop"}:
                return job
            if job.get("status") not in {
                "queued", "partial_failure", "failed", "interrupted"
            }:
                raise RuntimeError(f"job is not runnable from status={job.get('status')}")
            self._mark_job_running(job_id)
            self._refresh_target_suspensions(job)
            items = self._load_runnable_items(job_id)
            with ThreadPoolExecutor(
                max_workers=max(1, min(self.max_workers, len(items) or 1)),
                thread_name_prefix="a-share-sync",
            ) as executor:
                futures = [executor.submit(self._run_item, item) for item in items]
                for future in as_completed(futures):
                    future.result()
            summary = self._refresh_job_summary(job_id)
            if self.get_job(job_id).get("status") in {"stopping", "stopped"}:
                self._finish_job(job_id, status="stopped", error="stop_requested")
                return self.get_job(job_id, include_items=True)
            if summary["quarantined_items"] or summary["failed_items"]:
                self._finish_job(
                    job_id,
                    status="partial_failure",
                    error="one or more items are quarantined",
                )
                return self.get_job(job_id, include_items=True)
            if summary["completed_items"] != summary["total_items"]:
                self._finish_job(
                    job_id,
                    status="interrupted",
                    error="job stopped with unfinished items",
                )
                return self.get_job(job_id, include_items=True)
            self._set_job_status(job_id, "validating")
            try:
                release = self._validate_and_publish(job_id)
            except Exception as error:
                self._finish_job(
                    job_id,
                    status="failed",
                    error=f"{type(error).__name__}: {error}",
                )
                return self.get_job(job_id, include_items=True)
            self._finish_job(
                job_id,
                status="published",
                quality_report_id=release["quality_report_id"],
                data_version_id=release["data_version_id"],
            )
            return self.get_job(job_id, include_items=True)

    def retry_quarantined(self, job_id: str) -> dict[str, Any]:
        self.ensure_schema()
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='pending', attempt_count=0, next_attempt_at=NULL,
                    last_error=NULL, updated_at=?
                WHERE job_id=? AND status IN ('quarantined','stopped')
                """,
                (now, job_id),
            )
            connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET status='queued', last_error=NULL, finished_at=NULL, updated_at=?
                WHERE job_id=? AND status IN ('partial_failure','failed','interrupted','stopped')
                """,
                (now, job_id),
            )
        return self.get_job(job_id, include_items=True)

    def stop_job(self, job_id: str) -> dict[str, Any]:
        """Stop accepting new work while allowing in-flight writes to finish."""

        self.ensure_schema()
        job = self.get_job(job_id)
        if job.get("status") == "not_found":
            return job
        if job.get("status") in {"published", "completed_noop", "failed", "stopped"}:
            return job
        now = _utc_now()
        target_status = "stopping" if job.get("status") in {"running", "validating"} else "stopped"
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET status=?, last_error='stop_requested', updated_at=?,
                    finished_at=CASE WHEN ?='stopped' THEN ? ELSE finished_at END
                WHERE job_id=?
                """,
                (target_status, now, target_status, now, job_id),
            )
            connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='stopped', last_error='stop_requested', updated_at=?
                WHERE job_id=? AND status IN ('pending','retry_wait')
                """,
                (now, job_id),
            )
        return self.get_job(job_id, include_items=True)

    def recover_interrupted_jobs(self) -> dict[str, Any]:
        """Recover abandoned work and finalize jobs that were already stopping."""

        self.ensure_schema()
        now = _utc_now()
        with closing(self._connect(read_only=True)) as connection:
            stopping_job_ids = [
                str(row["job_id"]) for row in connection.execute(
                    """
                    SELECT job_id FROM market_incremental_sync_jobs
                    WHERE status IN ('stopping','stopped')
                      AND EXISTS (
                          SELECT 1 FROM market_incremental_sync_items items
                          WHERE items.job_id=market_incremental_sync_jobs.job_id
                            AND items.status IN ('pending','running','retry_wait')
                      )
                    """
                ).fetchall()
            ]
        finalized_items = 0
        for job_id in stopping_job_ids:
            result = self._finalize_stopped_job(job_id, error="startup_stop_recovery")
            finalized_items += int(result.get("finalized_items") or 0)
        with closing(self._connect()) as connection, connection:
            recovered_items = connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='pending', next_attempt_at=NULL,
                    last_error=COALESCE(last_error, 'startup_recovery'),
                    updated_at=?
                WHERE status IN ('running','retry_wait')
                  AND job_id IN (
                      SELECT job_id FROM market_incremental_sync_jobs
                      WHERE status IN ('running','validating','interrupted')
                  )
                """,
                (now,),
            ).rowcount
            recovered_jobs = connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET status='queued', last_error='startup_recovery',
                    started_at=NULL, finished_at=NULL, updated_at=?
                WHERE status IN ('running','validating','interrupted')
                """,
                (now,),
            ).rowcount
        return {
            "status": "completed",
            "recovered_jobs": recovered_jobs,
            "recovered_items": recovered_items,
            "finalized_stopping_jobs": len(stopping_job_ids),
            "finalized_stopping_items": finalized_items,
            "recovered_at": now,
        }

    def _finalize_stopped_job(self, job_id: str, *, error: str) -> dict[str, Any]:
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            finalized_items = connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='stopped', next_attempt_at=NULL,
                    last_error=COALESCE(last_error, ?), updated_at=?
                WHERE job_id=?
                  AND status NOT IN ('completed','quarantined','stopped')
                """,
                (str(error), now, job_id),
            ).rowcount
            connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET status='stopped', last_error=?, finished_at=COALESCE(finished_at, ?),
                    updated_at=?
                WHERE job_id=? AND status IN ('stopping','stopped')
                """,
                (str(error), now, now, job_id),
            )
        self._refresh_job_summary(job_id)
        return {
            **self.get_job(job_id, include_items=True),
            "finalized_items": finalized_items,
        }

    def mark_job_interrupted(self, job_id: str, *, error: str) -> dict[str, Any]:
        """Recover one abnormally terminated worker without touching other jobs."""

        self.ensure_schema()
        job = self.get_job(job_id)
        if str(job.get("status") or "") in {"stopping", "stopped"}:
            return self._finalize_stopped_job(job_id, error="stop_requested")
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='pending', next_attempt_at=NULL,
                    last_error=COALESCE(last_error, ?), updated_at=?
                WHERE job_id=? AND status IN ('running','retry_wait')
                """,
                (str(error), now, job_id),
            )
            connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET status='interrupted', last_error=?, finished_at=?,
                    updated_at=?
                WHERE job_id=? AND status IN ('queued','running','validating')
                """,
                (str(error), now, now, job_id),
            )
        return self.get_job(job_id, include_items=True)

    def run_due(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Run at most one missed daily schedule, including application-start catch-up."""

        self.ensure_schema()
        settings = self._settings()
        tick_at = now or datetime.now(timezone.utc)
        zone = ZoneInfo(str(settings["timezone_name"]))
        local_now = tick_at.astimezone(zone)
        due_at = local_now.replace(
            hour=int(settings["run_hour"]),
            minute=int(settings["run_minute"]),
            second=0,
            microsecond=0,
        )
        response: dict[str, Any]
        if not bool(settings["enabled"]):
            response = {"status": "disabled"}
        elif local_now < due_at:
            response = {"status": "not_due", "due_at": due_at.isoformat()}
        elif str(settings.get("last_scheduled_for") or "") == local_now.date().isoformat():
            existing = self.get_job(str(settings.get("last_job_id") or ""))
            if existing.get("status") in {"queued", "interrupted"}:
                response = self.run_job(str(existing["job_id"]))
            elif existing.get("status") in {"running", "validating"}:
                response = existing
            elif existing.get("status") in {"partial_failure", "failed"}:
                response = {
                    **existing,
                    "status": "needs_attention",
                    "reason": "scheduled_job_requires_manual_retry",
                }
            else:
                response = {
                    "status": "already_scheduled",
                    "job_id": settings.get("last_job_id"),
                }
        else:
            try:
                reference = self.refresh_reference_data(
                    end_date=local_now.date().isoformat()
                )
            except Exception as error:
                response = {
                    "status": "data_not_ready",
                    "reason": f"reference_refresh_failed:{type(error).__name__}: {error}",
                }
                self._record_tick(error=response["reason"])
                return response
            target = self._latest_open_trade_date(local_now.date().isoformat())
            if not target:
                response = {"status": "data_not_ready", "reason": "trade_calendar_missing"}
            elif str(reference.get("latest_index_date") or "") < target:
                response = {
                    "status": "data_not_ready",
                    "reason": "formal_benchmark_not_current",
                    "target_trade_date": target,
                    "latest_index_date": reference.get("latest_index_date"),
                }
            else:
                job = self.create_job(
                    target_trade_date=target,
                    all_current=True,
                    adjustments=_load_json(settings["adjustments_json"], []),
                    mode="scheduled",
                    schedule_key=f"canonical-a-share:{local_now.date().isoformat()}",
                )
                self._record_schedule_tick(
                    scheduled_for=local_now.date().isoformat(),
                    job_id=str(job["job_id"]),
                    error=None,
                )
                response = self.run_job(str(job["job_id"]))
        self._record_tick(error=response.get("reason"))
        return response

    def refresh_reference_data(self, *, end_date: str) -> dict[str, Any]:
        """Refresh catalog, calendar and formal benchmark before a scheduled price job."""

        self.ensure_schema()
        if self.governance_provider is None:
            with closing(self._connect(read_only=True)) as connection:
                latest_index = connection.execute(
                    """
                    SELECT MAX(trade_date) AS latest
                    FROM market_index_daily_prices WHERE index_symbol='000300'
                    """
                ).fetchone()
            return {
                "status": "local_only",
                "latest_index_date": latest_index["latest"] if latest_index else None,
            }
        target_end = date.fromisoformat(str(end_date)).isoformat()
        with closing(self._connect(read_only=True)) as connection:
            catalog_latest = connection.execute(
                "SELECT MAX(updated_at) AS latest FROM market_symbols"
            ).fetchone()["latest"]
        replaced = 0
        catalog_refreshed = False
        if str(catalog_latest or "")[:10] < target_end:
            symbols = list(self.governance_provider.list_symbols())
            if not symbols:
                raise RuntimeError("catalog provider returned no symbols")
            replaced = self.market_store.replace_current_symbols(symbols)
            catalog_refreshed = True
        with closing(self._connect(read_only=True)) as connection:
            calendar_latest = connection.execute(
                """
                SELECT MAX(trade_date) AS latest
                FROM market_trade_calendar WHERE market='CN'
                """
            ).fetchone()["latest"]
            index_latest = connection.execute(
                """
                SELECT MAX(trade_date) AS latest
                FROM market_index_daily_prices WHERE index_symbol='000300'
                """
            ).fetchone()["latest"]
        calendar_start = _resume_date(calendar_latest, target_end)
        calendar_rows: list[Mapping[str, Any]] = []
        if calendar_start <= target_end:
            calendar_rows = list(
                self.governance_provider.fetch_trade_calendar(
                    start_date=calendar_start,
                    end_date=target_end,
                    market="CN",
                )
            )
            self.governance_store.upsert_trade_calendar(calendar_rows)
        target_trade_date = self._latest_open_trade_date(target_end)
        index_rows: list[Mapping[str, Any]] = []
        if target_trade_date:
            index_start = _resume_date(index_latest, target_trade_date)
            if index_start <= target_trade_date:
                index_rows = list(
                    self.governance_provider.fetch_index_daily_prices(
                        index_symbol="000300",
                        start_date=index_start,
                        end_date=target_trade_date,
                    )
                )
                self.governance_store.upsert_index_prices(index_rows)
        with closing(self._connect(read_only=True)) as connection:
            latest_index = connection.execute(
                """
                SELECT MAX(trade_date) AS latest
                FROM market_index_daily_prices WHERE index_symbol='000300'
                """
            ).fetchone()["latest"]
        return {
            "status": "completed",
            "catalog_count": replaced,
            "catalog_refreshed": catalog_refreshed,
            "calendar_rows": len(calendar_rows),
            "index_rows": len(index_rows),
            "target_trade_date": target_trade_date,
            "latest_index_date": latest_index,
        }
    def start_background(self, *, poll_seconds: float = 60.0) -> dict[str, Any]:
        self.recover_interrupted_jobs()
        if self._thread and self._thread.is_alive():
            return {"status": "already_running"}
        self._stop_event.clear()

        def loop() -> None:
            while not self._stop_event.is_set():
                try:
                    self.run_due()
                except Exception as error:  # pragma: no cover - daemon safety boundary.
                    self._record_tick(error=f"{type(error).__name__}: {error}")
                self._stop_event.wait(max(1.0, float(poll_seconds)))

        self._thread = threading.Thread(
            target=loop,
            name="canonical-a-share-scheduler",
            daemon=True,
        )
        self._thread.start()
        return {"status": "started", "thread_name": self._thread.name}

    def stop_background(self) -> dict[str, Any]:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5.0)
        return {"status": "stopped"}

    def get_status(self) -> dict[str, Any]:
        self.ensure_schema()
        settings = self._settings()
        with closing(self._connect(read_only=True)) as connection:
            counts = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    """
                    SELECT status, COUNT(*) AS count
                    FROM market_incremental_sync_jobs GROUP BY status
                    """
                ).fetchall()
            }
            latest = connection.execute(
                """
                SELECT job_id, status, target_trade_date, data_version_id,
                       quality_report_id, updated_at
                FROM market_incremental_sync_jobs
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        return {
            "status": "ready",
            "enabled": bool(settings["enabled"]),
            "timezone": settings["timezone_name"],
            "run_time": f"{int(settings['run_hour']):02d}:{int(settings['run_minute']):02d}",
            "adjustments": _load_json(settings["adjustments_json"], []),
            "requests_per_minute": int(settings["requests_per_minute"]),
            "max_workers": int(settings["max_workers"]),
            "retry_count": int(settings["retry_count"]),
            "last_scheduled_for": settings.get("last_scheduled_for"),
            "last_job_id": settings.get("last_job_id"),
            "last_tick_at": settings.get("last_tick_at"),
            "last_error": settings.get("last_error"),
            "background_running": bool(self._thread and self._thread.is_alive()),
            "job_counts": counts,
            "latest_job": dict(latest) if latest else None,
        }

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """
                SELECT * FROM market_incremental_sync_jobs
                ORDER BY created_at DESC LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
            payloads = []
            for row in rows:
                payload = self._job_payload(row)
                payload.update(self._live_job_summary(connection, str(row["job_id"])))
                payloads.append(payload)
        return payloads

    def get_job(self, job_id: str, *, include_items: bool = False) -> dict[str, Any]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                "SELECT * FROM market_incremental_sync_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                return {"job_id": str(job_id), "status": "not_found"}
            payload = self._job_payload(row)
            payload.update(self._live_job_summary(connection, str(job_id)))
            if include_items:
                items = connection.execute(
                    """
                    SELECT * FROM market_incremental_sync_items
                    WHERE job_id=?
                    ORDER BY CASE status
                        WHEN 'quarantined' THEN 0
                        WHEN 'retry_wait' THEN 1
                        WHEN 'failed' THEN 2
                        ELSE 3
                    END, symbol, adjustment
                    """,
                    (job_id,),
                ).fetchall()
                payload["items"] = [
                    {
                        **dict(item),
                        "result": _load_json(item["result_json"], {}),
                    }
                    for item in items
                ]
        return payload

    def delete_job(self, job_id: str) -> dict[str, Any]:
        """Delete task metadata and work items without touching synchronized market data."""

        self.ensure_schema()
        job = self.get_job(job_id)
        if job.get("status") == "not_found":
            raise KeyError(f"sync task not found: {job_id}")
        if str(job.get("status") or "") in {"running", "validating", "stopping"}:
            raise ValueError("running, validating or stopping tasks cannot be deleted")
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM market_incremental_sync_items WHERE job_id=?", (job_id,))
            deleted = connection.execute(
                "DELETE FROM market_incremental_sync_jobs WHERE job_id=?", (job_id,)
            ).rowcount
        if deleted != 1:
            raise KeyError(f"sync task not found: {job_id}")
        return {
            "job_id": job_id,
            "status": "deleted",
            "deleted_items": int(job.get("total_items") or 0),
            "market_data_deleted": False,
        }
    @staticmethod
    def _live_job_summary(connection: sqlite3.Connection, job_id: str) -> dict[str, int]:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total_items,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed_items,
                   SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running_items,
                   SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending_items,
                   SUM(CASE WHEN status='retry_wait' THEN 1 ELSE 0 END) AS retry_wait_items,
                   SUM(CASE WHEN status='quarantined' THEN 1 ELSE 0 END) AS quarantined_items,
                   SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_items,
                   SUM(CASE WHEN status='stopped' THEN 1 ELSE 0 END) AS stopped_items,
                   SUM(rows_written) AS rows_written
            FROM market_incremental_sync_items WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return {}
        payload = {key: int(row[key] or 0) for key in row.keys()}
        payload["processed_items"] = (
            payload["completed_items"] + payload["quarantined_items"]
            + payload["failed_items"] + payload["stopped_items"]
        )
        return payload


    def _build_tasks(
        self,
        *,
        target_trade_date: str,
        symbols: Sequence[str] | None,
        all_current: bool,
        adjustments: Sequence[str],
        start_floor: str,
        gap_scan: bool = False,
    ) -> list[dict[str, Any]]:
        if gap_scan:
            return self._build_gap_tasks(target_trade_date, symbols, all_current, adjustments, start_floor)
        tasks: list[dict[str, str]] = []
        if all_current:
            for adjustment in adjustments:
                targets = self.market_store.list_sync_targets(
                    adjustment=adjustment,
                    end_date=target_trade_date,
                )
                for target in targets:
                    start = _resume_date(target.get("latest_date"), start_floor)
                    if start <= target_trade_date:
                        tasks.append(
                            {
                                "symbol": _normalize_symbol(target["symbol"]),
                                "adjustment": adjustment,
                                "start_date": start,
                            }
                        )
            return tasks
        with closing(self._connect(read_only=True)) as connection:
            for symbol in symbols or ():
                code = _normalize_symbol(symbol)
                for adjustment in adjustments:
                    latest = connection.execute(
                        """
                        SELECT MAX(trade_date) AS latest_date
                        FROM market_daily_prices
                        WHERE symbol=? AND adjustment=?
                        """,
                        (code, adjustment),
                    ).fetchone()
                    start = _resume_date(
                        latest["latest_date"] if latest else None,
                        start_floor,
                    )
                    if start <= target_trade_date:
                        tasks.append(
                            {
                                "symbol": code,
                                "adjustment": adjustment,
                                "start_date": start,
                            }
                        )
        return tasks

    def _build_gap_tasks(
        self, target_trade_date: str, symbols: Sequence[str] | None,
        all_current: bool, adjustments: Sequence[str], start_floor: str,
    ) -> list[dict[str, Any]]:
        start = date.fromisoformat(str(start_floor)).isoformat()
        end = date.fromisoformat(str(target_trade_date)).isoformat()
        if start > end:
            raise ValueError("start_trade_date must not be later than target_trade_date")
        if all_current:
            with closing(self._connect(read_only=True)) as connection:
                universe = [
                    _normalize_symbol(row["symbol"])
                    for row in connection.execute(
                        "SELECT symbol FROM market_symbols WHERE listing_status='current' ORDER BY symbol"
                    ).fetchall()
                ]
        else:
            universe = sorted({_normalize_symbol(item) for item in symbols or ()})
        tasks: list[dict[str, Any]] = []
        if not universe:
            return tasks
        with closing(self._connect(read_only=True)) as connection:
            if all_current:
                eligible = {
                    _normalize_symbol(row["symbol"])
                    for row in connection.execute(
                        """
                        SELECT s.symbol FROM market_symbols s
                        WHERE EXISTS (
                            SELECT 1 FROM market_daily_prices p
                            WHERE p.symbol=s.symbol AND p.trade_date<=?
                        ) OR EXISTS (
                            SELECT 1 FROM security_lifecycle_events e
                            WHERE e.symbol=s.symbol AND e.event_type='listed'
                              AND e.effective_from<=?
                        )
                        """,
                        (end, end),
                    ).fetchall()
                }
                universe = [symbol for symbol in universe if symbol in eligible]
            for adjustment in adjustments:
                for offset in range(0, len(universe), 400):
                    batch = universe[offset:offset + 400]
                    placeholders = ",".join("?" for _ in batch)
                    rows = connection.execute(
                        f"""
                        SELECT s.symbol,
                               MIN(cal.trade_date) AS first_missing_date,
                               MAX(cal.trade_date) AS last_missing_date,
                               COUNT(*) AS missing_date_count
                        FROM market_symbols s
                        JOIN market_trade_calendar cal
                          ON cal.market='CN' AND cal.is_open=1
                        LEFT JOIN market_daily_prices p
                          ON p.symbol=s.symbol AND p.adjustment=?
                         AND p.trade_date=cal.trade_date
                         AND p.open IS NOT NULL AND p.high IS NOT NULL
                         AND p.low IS NOT NULL AND p.close IS NOT NULL
                         AND p.high >= MAX(p.open, p.close, p.low)
                         AND p.low <= MIN(p.open, p.close, p.high)
                         AND p.volume >= 0
                        LEFT JOIN security_trading_status_daily ts
                          ON ts.symbol=s.symbol AND ts.trade_date=cal.trade_date
                         AND ts.is_tradable=0
                        WHERE s.symbol IN ({placeholders})
                          AND cal.trade_date BETWEEN ? AND ?
                          AND cal.trade_date >= MAX(
                              COALESCE((
                                  SELECT MIN(effective_from) FROM security_lifecycle_events lifecycle
                                  WHERE lifecycle.symbol=s.symbol AND lifecycle.event_type='listed'
                              ), ?),
                              COALESCE((
                                  SELECT MIN(first_price.trade_date) FROM market_daily_prices first_price
                                  WHERE first_price.symbol=s.symbol AND first_price.adjustment=?
                              ), ?)
                          )
                          AND cal.trade_date < COALESCE((
                              SELECT MIN(effective_from)
                              FROM security_lifecycle_events lifecycle
                              WHERE lifecycle.symbol=s.symbol
                                AND lifecycle.event_type IN ('delisted','terminated')
                          ), '9999-12-31')
                          AND p.symbol IS NULL
                          AND ts.symbol IS NULL
                        GROUP BY s.symbol
                        ORDER BY s.symbol
                        """,
                        [str(adjustment), *batch, start, end, start, str(adjustment), start],
                    ).fetchall()
                    tasks.extend({
                        "symbol": _normalize_symbol(row["symbol"]),
                        "adjustment": str(adjustment),
                        "start_date": str(row["first_missing_date"]),
                        "first_missing_date": str(row["first_missing_date"]),
                        "last_missing_date": str(row["last_missing_date"]),
                        "missing_date_count": int(row["missing_date_count"] or 0),
                    } for row in rows)
        return tasks

    def _attach_gap_date_samples(
        self, tasks: list[dict[str, Any]], target_trade_date: str,
        start_floor: str, sample_limit: int = 50,
    ) -> None:
        """Attach bounded exact missing-date samples to preview-only task copies."""

        if not tasks:
            return
        start = date.fromisoformat(str(start_floor)).isoformat()
        end = date.fromisoformat(str(target_trade_date)).isoformat()
        with closing(self._connect(read_only=True)) as connection:
            for task in tasks:
                rows = connection.execute(
                    """
                    SELECT cal.trade_date
                    FROM market_symbols s
                    JOIN market_trade_calendar cal
                      ON cal.market='CN' AND cal.is_open=1
                    LEFT JOIN market_daily_prices p
                      ON p.symbol=s.symbol AND p.adjustment=?
                     AND p.trade_date=cal.trade_date
                     AND p.open IS NOT NULL AND p.high IS NOT NULL
                     AND p.low IS NOT NULL AND p.close IS NOT NULL
                     AND p.high >= MAX(p.open, p.close, p.low)
                     AND p.low <= MIN(p.open, p.close, p.high)
                     AND p.volume >= 0
                    LEFT JOIN security_trading_status_daily ts
                      ON ts.symbol=s.symbol AND ts.trade_date=cal.trade_date
                     AND ts.is_tradable=0
                    WHERE s.symbol=?
                      AND cal.trade_date BETWEEN ? AND ?
                      AND cal.trade_date >= MAX(
                          COALESCE((
                              SELECT MIN(effective_from) FROM security_lifecycle_events lifecycle
                              WHERE lifecycle.symbol=s.symbol AND lifecycle.event_type='listed'
                          ), ?),
                          COALESCE((
                              SELECT MIN(first_price.trade_date) FROM market_daily_prices first_price
                              WHERE first_price.symbol=s.symbol AND first_price.adjustment=?
                          ), ?)
                      )
                      AND cal.trade_date < COALESCE((
                          SELECT MIN(effective_from)
                          FROM security_lifecycle_events lifecycle
                          WHERE lifecycle.symbol=s.symbol
                            AND lifecycle.event_type IN ('delisted','terminated')
                      ), '9999-12-31')
                      AND p.symbol IS NULL
                      AND ts.symbol IS NULL
                    ORDER BY cal.trade_date
                    LIMIT ?
                    """,
                    (
                        str(task["adjustment"]), str(task["symbol"]), start, end,
                        start, str(task["adjustment"]), start, sample_limit + 1,
                    ),
                ).fetchall()
                dates = [str(row["trade_date"]) for row in rows]
                task["missing_dates"] = dates[:sample_limit]
                task["missing_dates_truncated"] = (
                    int(task.get("missing_date_count") or 0) > sample_limit
                    or len(dates) > sample_limit
                )
    def _mark_job_running(self, job_id: str) -> None:
        now = _utc_now()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            other = connection.execute(
                """
                SELECT job_id FROM market_incremental_sync_jobs
                WHERE status IN ('running','validating') AND job_id<>?
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if other:
                connection.rollback()
                raise RuntimeError(f"another sync job is active: {other['job_id']}")
            connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET status='running', started_at=COALESCE(started_at, ?),
                    finished_at=NULL, last_error=NULL, updated_at=?
                WHERE job_id=?
                """,
                (now, now, job_id),
            )
            connection.commit()

    def _load_runnable_items(self, job_id: str) -> list[dict[str, Any]]:
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """
                SELECT * FROM market_incremental_sync_items
                WHERE job_id=? AND status NOT IN ('completed','quarantined')
                ORDER BY symbol, adjustment
                """,
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _refresh_target_suspensions(self, job: Mapping[str, Any]) -> None:
        """Refresh target-day calendar and suspension evidence before price sync."""

        provider = self.governance_provider
        if provider is None or not hasattr(provider, "fetch_suspensions"):
            return
        target = str(job.get("target_trade_date") or "")
        if not target:
            return
        try:
            calendar_rows = list(
                provider.fetch_trade_calendar(
                    start_date=target,
                    end_date=target,
                    market="CN",
                )
            )
            if calendar_rows:
                self.governance_store.upsert_trade_calendar(calendar_rows)
        except (Exception, SystemExit):
            pass
        try:
            rows = list(provider.fetch_suspensions(trade_date=target))
        except (Exception, SystemExit):
            return
        normalized = []
        for source_row in rows:
            row = dict(source_row)
            evidence = dict(row.get("evidence") or {})
            evidence.setdefault("source_suspension_start_date", row.get("trade_date"))
            evidence["normalized_status_trade_date"] = target
            row["trade_date"] = target
            row["evidence"] = evidence
            normalized.append(row)
        if normalized:
            self.governance_store.upsert_trading_statuses(normalized)

    def _is_target_suspended(self, symbol: str, trade_date: str) -> bool:
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM security_trading_status_daily
                WHERE symbol=? AND trade_date=? AND status='suspended'
                  AND is_tradable=0
                LIMIT 1
                """,
                (_normalize_symbol(symbol), str(trade_date)),
            ).fetchone()
        return row is not None

    def _has_listing_evidence_by(self, symbol: str, trade_date: str) -> bool:
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                """
                SELECT 1
                WHERE EXISTS (
                    SELECT 1 FROM market_daily_prices
                    WHERE symbol=? AND trade_date<=?
                ) OR EXISTS (
                    SELECT 1 FROM security_lifecycle_events
                    WHERE symbol=? AND event_type='listed' AND effective_from<=?
                )
                """,
                (_normalize_symbol(symbol), str(trade_date),
                 _normalize_symbol(symbol), str(trade_date)),
            ).fetchone()
        return row is not None

    def _record_inferred_historical_suspensions(
        self, *, job_id: str, symbol: str, adjustment: str,
        start_date: str, end_date: str,
    ) -> int:
        """Record listed no-trade dates only when every price mode is absent."""
        with closing(self._connect(read_only=True)) as connection:
            bounds = connection.execute(
                """SELECT MIN(trade_date) AS first_date, MAX(trade_date) AS last_date,
                          (SELECT MIN(effective_from) FROM security_lifecycle_events
                           WHERE symbol=? AND event_type='listed') AS listing_date
                   FROM market_daily_prices
                   WHERE symbol=? AND adjustment=?""",
                (_normalize_symbol(symbol), _normalize_symbol(symbol), str(adjustment)),
            ).fetchone()
            if not bounds or not bounds["first_date"] or not bounds["last_date"]:
                return 0
            target_suspended = connection.execute(
                """SELECT 1 FROM security_trading_status_daily
                   WHERE symbol=? AND trade_date=? AND status='suspended'
                     AND is_tradable=0 LIMIT 1""",
                (_normalize_symbol(symbol), str(end_date)),
            ).fetchone()
            upper_bound = str(end_date) if target_suspended else str(bounds["last_date"])
            lower_bound = (
                max(str(start_date), str(bounds["listing_date"]))
                if bounds["listing_date"] else str(bounds["first_date"])
            )
            dates = connection.execute(
                """SELECT cal.trade_date FROM market_trade_calendar cal
                   WHERE cal.market='CN' AND cal.is_open=1
                     AND cal.trade_date BETWEEN ? AND ?
                      AND cal.trade_date >= ? AND cal.trade_date <= ?
                     AND NOT EXISTS (SELECT 1 FROM market_daily_prices p
                         WHERE p.symbol=? AND p.trade_date=cal.trade_date)
                     AND NOT EXISTS (SELECT 1 FROM security_trading_status_daily status
                         WHERE status.symbol=? AND status.trade_date=cal.trade_date
                           AND status.status='suspended' AND status.is_tradable=0)
                   ORDER BY cal.trade_date""",
                (str(start_date), str(end_date),
                  lower_bound, upper_bound,
                 _normalize_symbol(symbol), _normalize_symbol(symbol)),
            ).fetchall()
        observed_at = _utc_now()
        rows = [{
            "symbol": _normalize_symbol(symbol), "trade_date": str(row["trade_date"]),
            "status": "suspended", "is_tradable": False,
            "suspension_reason": "inferred_from_successful_history_gap",
            "source": "canonical_history_gap_inference", "source_observed_at": observed_at,
            "evidence": {"job_id": job_id, "adjustment": adjustment,
                "inference_rule": "listed_open_date_absent_from_all_adjustments_in_observed_range"},
        } for row in dates]
        return self.governance_store.upsert_trading_statuses(rows)

    def _run_item(self, item: Mapping[str, Any]) -> None:
        job_id = str(item["job_id"])
        symbol = str(item["symbol"])
        adjustment = str(item["adjustment"])
        attempt = int(item.get("attempt_count") or 0)
        if (
            str(item["start_date"]) == str(item["end_date"])
            and self._is_target_suspended(symbol, str(item["end_date"]))
        ):
            self._complete_item(
                job_id,
                symbol,
                adjustment,
                result={
                    "status": "completed",
                    "symbol": symbol,
                    "adjustment": adjustment,
                    "start_date": str(item["start_date"]),
                    "end_date": str(item["end_date"]),
                    "rows_received": 0,
                    "rows_written": 0,
                    "completion_reason": "target_trade_date_suspended",
                },
            )
            return
        while attempt < self.retry_count:
            if self._job_stop_requested(job_id):
                self._stop_item(job_id, symbol, adjustment)
                return
            attempt += 1
            self._set_item_running(job_id, symbol, adjustment, attempt)
            if not self._provider_controls_rate:
                self._rate_limiter.acquire()
            try:
                result = dict(
                    self.provider.sync_symbol(
                        self.market_store,
                        symbol=symbol,
                        adjustment=adjustment,
                        start_date=str(item["start_date"]),
                        end_date=str(item["end_date"]),
                    )
                )
                rows_received = int(result.get("rows_received") or 0)
                if (
                    result.get("status") == "completed"
                    and rows_received <= 0
                    and self._is_target_suspended(symbol, str(item["end_date"]))
                    and str(item["start_date"]) == str(item["end_date"])
                ):
                    result.update(
                        {
                            "status": "completed",
                            "rows_received": 0,
                            "rows_written": 0,
                            "completion_reason": "target_trade_date_suspended",
                        }
                    )
                    self._complete_item(
                        job_id,
                        symbol,
                        adjustment,
                        result=result,
                    )
                    return
                if (
                    result.get("status") == "completed"
                    and rows_received <= 0
                    and str(item["start_date"]) < str(item["end_date"])
                ):
                    inferred = self._record_inferred_historical_suspensions(
                        job_id=job_id, symbol=symbol, adjustment=adjustment,
                        start_date=str(item["start_date"]), end_date=str(item["end_date"]),
                    )
                    if inferred > 0:
                        result.update({
                            "status": "completed",
                            "rows_received": 0,
                            "rows_written": 0,
                            "inferred_suspension_count": inferred,
                            "completion_reason": "bounded_historical_suspensions_inferred",
                        })
                        self._complete_item(
                            job_id, symbol, adjustment, result=result,
                        )
                        return
                if (
                    result.get("status") == "completed"
                    and rows_received <= 0
                    and not self._has_listing_evidence_by(symbol, str(item["end_date"]))
                ):
                    result.update({
                        "status": "completed",
                        "rows_received": 0,
                        "rows_written": 0,
                        "completion_reason": "not_listed_by_target_trade_date",
                    })
                    self._complete_item(
                        job_id, symbol, adjustment, result=result,
                    )
                    return
                if result.get("status") != "completed" or rows_received <= 0:
                    raise RuntimeError("provider returned no rows for required increment")
                result["inferred_suspension_count"] = self._record_inferred_historical_suspensions(
                    job_id=job_id, symbol=symbol, adjustment=adjustment,
                    start_date=str(item["start_date"]), end_date=str(item["end_date"]),
                )
                self._complete_item(
                    job_id,
                    symbol,
                    adjustment,
                    result=result,
                )
                return
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                if attempt >= self.retry_count:
                    self._quarantine_item(
                        job_id,
                        symbol,
                        adjustment,
                        attempt=attempt,
                        error=message,
                    )
                    return
                backoff = self.base_backoff_seconds * (2 ** (attempt - 1))
                self._set_item_retry(
                    job_id,
                    symbol,
                    adjustment,
                    attempt=attempt,
                    error=message,
                    delay_seconds=backoff,
                )
                if backoff:
                    self._sleep(backoff)

    def _validate_and_publish(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        target = str(job["target_trade_date"])
        checks = self._quality_checks(job_id, target)
        passed = all(bool(check["passed"]) for check in checks)
        quality_report_id = (
            f"stage782-{target.replace('-', '')}-"
            f"{sha256((job_id + _dump(checks)).encode('utf-8')).hexdigest()[:12]}"
        )
        report = self.governance_store.save_quality_report(
            quality_report_id=quality_report_id,
            rule_version="stage78.2-incremental-release-v1",
            status="passed" if passed else "failed",
            payload={
                "job_id": job_id,
                "target_trade_date": target,
                "checks": checks,
            },
        )
        if not passed:
            failed = [
                f"{check['name']}={_dump(check.get('evidence') or {})}"
                for check in checks if not check["passed"]
            ]
            raise RuntimeError(f"quality gate failed: {';'.join(failed)}")
        members = self._release_members(job_id, target)
        release = self.governance_store.publish_data_version(
            as_of_trade_date=target,
            quality_report_id=quality_report_id,
            members=members,
            notes=f"stage78.2 incremental release job={job_id}",
        )
        return {
            "quality_report_id": report["quality_report_id"],
            "data_version_id": release["data_version_id"],
        }

    def _quality_checks(self, job_id: str, target: str) -> list[dict[str, Any]]:
        with closing(self._connect(read_only=True)) as connection:
            item_summary = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                       SUM(CASE WHEN status='quarantined' THEN 1 ELSE 0 END) AS quarantined
                FROM market_incremental_sync_items WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            missing_target = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM market_incremental_sync_items i
WHERE i.job_id=? AND NOT EXISTS (
                    SELECT 1 FROM market_daily_prices p
                    WHERE p.symbol=i.symbol AND p.adjustment=i.adjustment
                      AND p.trade_date=?
                ) AND NOT EXISTS (
                    SELECT 1 FROM security_trading_status_daily s
                    WHERE s.symbol=i.symbol AND s.trade_date=?
                      AND s.is_tradable=0
                )
                AND COALESCE(json_extract(i.result_json, '$.completion_reason'), '')
                    <> 'not_listed_by_target_trade_date'
                """,
                (job_id, target, target),
            ).fetchone()["count"]
            duplicate_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM (
                    SELECT symbol, trade_date, adjustment, COUNT(*) AS n
                    FROM market_daily_prices
                    GROUP BY symbol, trade_date, adjustment HAVING n>1
                )
                """
            ).fetchone()["count"]
            invalid_ohlc = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM market_daily_prices
                WHERE (
                    open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
                    OR high < MAX(open, close, low)
                    OR low > MIN(open, close, high)
                    OR volume < 0
                )
                  AND NOT EXISTS (
                      SELECT 1 FROM security_trading_status_daily s
                      WHERE s.symbol=market_daily_prices.symbol
                        AND s.trade_date=market_daily_prices.trade_date
                        AND s.is_tradable=0
                  )
                """
            ).fetchone()["count"]
            invalid_samples = connection.execute(
                """
                SELECT symbol, trade_date, adjustment, open, high, low, close, volume
                FROM market_daily_prices
                WHERE (
                    open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
                    OR high < MAX(open, close, low)
                    OR low > MIN(open, close, high)
                    OR volume < 0
                )
                  AND NOT EXISTS (
                      SELECT 1 FROM security_trading_status_daily s
                      WHERE s.symbol=market_daily_prices.symbol
                        AND s.trade_date=market_daily_prices.trade_date
                        AND s.is_tradable=0
                  )
                ORDER BY symbol, trade_date, adjustment LIMIT 10
                """
            ).fetchall()
            calendar = connection.execute(
                """
                SELECT is_open FROM market_trade_calendar
                WHERE market='CN' AND trade_date=?
                """,
                (target,),
            ).fetchone()
            benchmark = connection.execute(
                """
                SELECT MAX(trade_date) AS latest
                FROM market_index_daily_prices WHERE index_symbol='000300'
                """
            ).fetchone()
        return [
            {
                "name": "all_items_completed",
                "passed": (
                    int(item_summary["total"] or 0)
                    == int(item_summary["completed"] or 0)
                    and int(item_summary["quarantined"] or 0) == 0
                ),
                "evidence": dict(item_summary),
            },
            {
                "name": "requested_target_coverage",
                "passed": int(missing_target or 0) == 0,
                "evidence": {"missing_item_targets": int(missing_target or 0)},
            },
            {
                "name": "daily_primary_key_duplicates",
                "passed": int(duplicate_count or 0) == 0,
                "evidence": {"duplicate_groups": int(duplicate_count or 0)},
            },
            {
                "name": "daily_ohlcv_valid_all_adjustments",
                "passed": int(invalid_ohlc or 0) == 0,
                "evidence": {"invalid_rows": int(invalid_ohlc or 0), "samples": [dict(row) for row in invalid_samples]},
            },
            {
                "name": "target_is_open_trade_day",
                "passed": bool(calendar and int(calendar["is_open"]) == 1),
                "evidence": {"calendar_row": dict(calendar) if calendar else None},
            },
            {
                "name": "formal_benchmark_current",
                "passed": bool(benchmark and str(benchmark["latest"] or "") >= target),
                "evidence": {"latest_index_date": benchmark["latest"] if benchmark else None},
            },
        ]

    def _release_members(self, job_id: str, target: str) -> list[dict[str, Any]]:
        with closing(self._connect(read_only=True)) as connection:
            daily = connection.execute(
                """
                SELECT adjustment, COUNT(*) AS row_count,
                       COUNT(DISTINCT symbol) AS symbol_count,
                       MIN(trade_date) AS min_date, MAX(trade_date) AS max_date
                FROM market_daily_prices
                GROUP BY adjustment ORDER BY adjustment
                """
            ).fetchall()
            calendar = connection.execute(
                """
                SELECT COUNT(*) AS row_count, MIN(trade_date) AS min_date,
                       MAX(trade_date) AS max_date
                FROM market_trade_calendar WHERE market='CN'
                """
            ).fetchone()
            benchmark = connection.execute(
                """
                SELECT COUNT(*) AS row_count, MIN(trade_date) AS min_date,
                       MAX(trade_date) AS max_date
                FROM market_index_daily_prices WHERE index_symbol='000300'
                """
            ).fetchone()
            current = connection.execute(
                """
                SELECT data_version_id FROM data_versions
                WHERE status='published'
                ORDER BY as_of_trade_date DESC, published_at DESC LIMIT 1
                """
            ).fetchone()
            carried: list[sqlite3.Row] = []
            if current:
                carried = connection.execute(
                    """
                    SELECT dataset, adjustment, symbol_scope, row_count,
                           symbol_count, min_date, max_date, source,
                           sync_run_ref, content_hash, quality_status,
                           details_json
                    FROM data_version_members
                    WHERE data_version_id=?
                      AND dataset NOT IN (
                          'market_daily_prices',
                          'market_trade_calendar',
                          'market_index_daily_prices'
                      )
                    ORDER BY dataset, adjustment
                    """,
                    (current["data_version_id"],),
                ).fetchall()
        members = [
            {
                "dataset": "market_daily_prices",
                "adjustment": row["adjustment"],
                "symbol_scope": "canonical_all",
                "row_count": int(row["row_count"]),
                "symbol_count": int(row["symbol_count"]),
                "min_date": row["min_date"],
                "max_date": row["max_date"],
                "source": "canonical_a_share_sqlite",
                "sync_run_ref": job_id,
                "content_hash": _hash_mapping({
                    "dataset": "market_daily_prices",
                    "adjustment": row["adjustment"],
                    "row_count": row["row_count"],
                    "symbol_count": row["symbol_count"],
                    "min_date": row["min_date"],
                    "max_date": row["max_date"],
                    "target": target,
                }),
                "quality_status": "passed",
                "details": {"incremental_job_id": job_id},
            }
            for row in daily
        ]
        for dataset, scope, row in (
            ("market_trade_calendar", "CN", calendar),
            ("market_index_daily_prices", "000300", benchmark),
        ):
            members.append({
                "dataset": dataset,
                "adjustment": "",
                "symbol_scope": scope,
                "row_count": int(row["row_count"] or 0),
                "symbol_count": 1,
                "min_date": row["min_date"],
                "max_date": row["max_date"],
                "source": "stage78.2-reference-refresh",
                "sync_run_ref": job_id,
                "content_hash": _hash_mapping({
                    "dataset": dataset,
                    "symbol_scope": scope,
                    "row_count": row["row_count"],
                    "min_date": row["min_date"],
                    "max_date": row["max_date"],
                    "target": target,
                }),
                "quality_status": "passed",
                "details": {"incremental_job_id": job_id},
            })
        members.extend(
            {
                "dataset": row["dataset"],
                "adjustment": row["adjustment"],
                "symbol_scope": row["symbol_scope"],
                "row_count": int(row["row_count"]),
                "symbol_count": int(row["symbol_count"]),
                "min_date": row["min_date"],
                "max_date": row["max_date"],
                "source": row["source"],
                "sync_run_ref": row["sync_run_ref"],
                "content_hash": row["content_hash"],
                "quality_status": row["quality_status"],
                "details": _load_json(row["details_json"], {}),
            }
            for row in carried
        )
        return members
    def _job_stop_requested(self, job_id: str) -> bool:
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                "SELECT status FROM market_incremental_sync_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return bool(row and str(row["status"]) in {"stopping", "stopped"})

    def _stop_item(self, job_id: str, symbol: str, adjustment: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='stopped', last_error='stop_requested', updated_at=?
                WHERE job_id=? AND symbol=? AND adjustment=? AND status<>'completed'
                """,
                (_utc_now(), job_id, symbol, adjustment),
            )

    def _set_item_running(
        self, job_id: str, symbol: str, adjustment: str, attempt: int
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='running', attempt_count=?, next_attempt_at=NULL,
                    updated_at=?
                WHERE job_id=? AND symbol=? AND adjustment=?
                """,
                (attempt, _utc_now(), job_id, symbol, adjustment),
            )

    def _complete_item(
        self,
        job_id: str,
        symbol: str,
        adjustment: str,
        *,
        result: Mapping[str, Any],
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='completed', rows_received=?, rows_written=?,
                    result_json=?, next_attempt_at=NULL, last_error=NULL,
                    updated_at=?
                WHERE job_id=? AND symbol=? AND adjustment=?
                """,
                (
                    int(result.get("rows_received") or 0),
                    int(result.get("rows_written") or 0),
                    _dump(dict(result)),
                    _utc_now(),
                    job_id,
                    symbol,
                    adjustment,
                ),
            )

    def _set_item_retry(
        self,
        job_id: str,
        symbol: str,
        adjustment: str,
        *,
        attempt: int,
        error: str,
        delay_seconds: float,
    ) -> None:
        next_at = (
            datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        ).isoformat(timespec="seconds")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='retry_wait', attempt_count=?, next_attempt_at=?,
                    last_error=?, updated_at=?
                WHERE job_id=? AND symbol=? AND adjustment=?
                """,
                (
                    attempt,
                    next_at,
                    error,
                    _utc_now(),
                    job_id,
                    symbol,
                    adjustment,
                ),
            )

    def _quarantine_item(
        self,
        job_id: str,
        symbol: str,
        adjustment: str,
        *,
        attempt: int,
        error: str,
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_items
                SET status='quarantined', attempt_count=?, next_attempt_at=NULL,
                    last_error=?, updated_at=?
                WHERE job_id=? AND symbol=? AND adjustment=?
                """,
                (
                    attempt,
                    error,
                    _utc_now(),
                    job_id,
                    symbol,
                    adjustment,
                ),
            )

    def _refresh_job_summary(self, job_id: str) -> dict[str, int]:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total_items,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed_items,
                       SUM(CASE WHEN status IN ('pending','running','retry_wait') THEN 1 ELSE 0 END) AS failed_items,
                       SUM(CASE WHEN status='quarantined' THEN 1 ELSE 0 END) AS quarantined_items,
                       SUM(rows_written) AS rows_written
                FROM market_incremental_sync_items WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            values = {key: int(row[key] or 0) for key in row.keys()}
            connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET total_items=?, completed_items=?, failed_items=?,
                    quarantined_items=?, rows_written=?, updated_at=?
                WHERE job_id=?
                """,
                (
                    values["total_items"],
                    values["completed_items"],
                    values["failed_items"],
                    values["quarantined_items"],
                    values["rows_written"],
                    _utc_now(),
                    job_id,
                ),
            )
        return values

    def _set_job_status(self, job_id: str, status: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET status=?, updated_at=? WHERE job_id=?
                """,
                (status, _utc_now(), job_id),
            )

    def _finish_job(
        self,
        job_id: str,
        *,
        status: str,
        error: str | None = None,
        quality_report_id: str | None = None,
        data_version_id: str | None = None,
    ) -> None:
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_incremental_sync_jobs
                SET status=?, last_error=?, quality_report_id=?,
                    data_version_id=?, finished_at=?, updated_at=?
                WHERE job_id=?
                """,
                (
                    status,
                    error,
                    quality_report_id,
                    data_version_id,
                    now,
                    now,
                    job_id,
                ),
            )

    def _settings(self) -> dict[str, Any]:
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                """
                SELECT * FROM market_scheduler_settings
                WHERE scheduler_id='canonical-a-share'
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("scheduler settings are missing")
        return dict(row)

    def _latest_open_trade_date(self, date_limit: str) -> str | None:
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                """
                SELECT MAX(trade_date) AS trade_date
                FROM market_trade_calendar
                WHERE market='CN' AND is_open=1 AND trade_date<=?
                """,
                (date_limit,),
            ).fetchone()
        return str(row["trade_date"]) if row and row["trade_date"] else None

    def _record_schedule_tick(
        self, *, scheduled_for: str, job_id: str, error: str | None
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_scheduler_settings
                SET last_scheduled_for=?, last_job_id=?, last_error=?,
                    last_tick_at=?, updated_at=?
                WHERE scheduler_id='canonical-a-share'
                """,
                (scheduled_for, job_id, error, _utc_now(), _utc_now()),
            )

    def _record_tick(self, *, error: str | None) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_scheduler_settings
                SET last_tick_at=?, last_error=?, updated_at=?
                WHERE scheduler_id='canonical-a-share'
                """,
                (_utc_now(), error, _utc_now()),
            )

    def _job_payload(self, row: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        payload["adjustments"] = _load_json(payload.pop("adjustments_json"), [])
        return payload

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            connection = sqlite3.connect(
                f"file:{self.database_path.resolve().as_posix()}?mode=ro",
                uri=True,
            )
            connection.execute("PRAGMA query_only = ON")
        else:
            connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection


def _resume_date(latest: Any, start_floor: str) -> str:
    if not latest:
        return date.fromisoformat(str(start_floor)).isoformat()
    return (date.fromisoformat(str(latest)) + timedelta(days=1)).isoformat()


def _adjustments(values: Iterable[str]) -> list[str]:
    modes = []
    for value in values:
        mode = _normalize_adjustment(value)
        if mode not in modes:
            modes.append(mode)
    if not modes:
        raise ValueError("at least one adjustment is required")
    return modes


def _parse_run_time(value: str) -> tuple[int, int]:
    hour_text, minute_text = str(value).split(":", 1)
    hour, minute = int(hour_text), int(minute_text)
    if hour not in range(24) or minute not in range(60):
        raise ValueError("run_time must be HH:MM")
    return hour, minute


def _load_json(value: Any, default: Any) -> Any:
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _dump(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash_mapping(value: Mapping[str, Any]) -> str:
    return sha256(_dump(dict(value)).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
