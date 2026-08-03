"""Persistent stage-78.3 full-market context backfill and release workflow."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from data_platform.a_share_sync_scheduler import GlobalRateLimiter
from data_platform.storage.a_share_governance_store import AShareGovernanceStore


CONTEXT_SCHEMA_VERSION = "78.3.0"
REMOTE_DATASETS = (
    "security_lifecycle_events",
    "corporate_action_events",
    "security_suspensions",
)
LOCAL_DATASETS = (
    "security_trading_status_daily",
    "price_adjustment_factors",
)
ALL_DATASETS = REMOTE_DATASETS + LOCAL_DATASETS
TERMINAL_ITEM_STATUSES = ("completed", "quarantined")


class AShareContextBackfill:
    """Queue, resume, validate and publish full-market context facts."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        provider: Any,
        requests_per_minute: int = 60,
        max_workers: int = 4,
        retry_count: int = 3,
        base_backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.database_path = Path(database_path)
        self.provider = provider
        self.governance_store = AShareGovernanceStore(self.database_path)
        self.max_workers = max(1, min(int(max_workers), 16))
        self.retry_count = max(1, int(retry_count))
        self.base_backoff_seconds = max(0.0, float(base_backoff_seconds))
        self._sleep = sleep
        self._rate_limiter = GlobalRateLimiter(
            requests_per_minute,
            monotonic=monotonic,
            sleep=sleep,
        )
        if hasattr(provider, "request_gate"):
            provider.request_gate = self._rate_limiter.acquire
        self._run_lock = threading.Lock()

    def ensure_schema(self) -> None:
        self.governance_store.ensure_schema()
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_context_backfill_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    symbol_scope TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    datasets_json TEXT NOT NULL,
                    total_items INTEGER NOT NULL DEFAULT 0,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    quarantined_items INTEGER NOT NULL DEFAULT 0,
                    rows_written INTEGER NOT NULL DEFAULT 0,
                    unknown_items INTEGER NOT NULL DEFAULT 0,
                    quality_report_id TEXT,
                    data_version_id TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_context_backfill_jobs_status
                    ON market_context_backfill_jobs (status, created_at);

                CREATE TABLE IF NOT EXISTS market_context_backfill_items (
                    job_id TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    symbol TEXT,
                    trade_date TEXT,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    rows_received INTEGER NOT NULL DEFAULT 0,
                    rows_written INTEGER NOT NULL DEFAULT 0,
                    evidence_state TEXT,
                    next_attempt_at TEXT,
                    last_error TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, dataset, item_key),
                    FOREIGN KEY (job_id)
                        REFERENCES market_context_backfill_jobs (job_id)
                );

                CREATE INDEX IF NOT EXISTS idx_context_backfill_items_status
                    ON market_context_backfill_items
                       (job_id, dataset, status, next_attempt_at);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO market_schema_migrations
                    (schema_version, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    CONTEXT_SCHEMA_VERSION,
                    "Add persistent full-market context backfill queue",
                    _utc_now(),
                ),
            )

    def create_job(
        self,
        *,
        start_date: str,
        end_date: str,
        symbols: Sequence[str] | None = None,
        all_current: bool = False,
        datasets: Sequence[str] = ALL_DATASETS,
    ) -> dict[str, Any]:
        self.ensure_schema()
        if bool(symbols) == bool(all_current):
            raise ValueError("provide symbols or set all_current=true, but not both")
        selected = _datasets(datasets)
        symbol_rows = self._symbols(symbols if not all_current else None)
        if not symbol_rows:
            raise RuntimeError("no symbols found for context backfill")
        open_dates = self._open_dates(start_date, end_date)
        if not open_dates:
            raise RuntimeError("no open trade dates found in requested range")

        job_id = f"ctx-{uuid.uuid4().hex[:16]}"
        now = _utc_now()
        items: list[tuple[Any, ...]] = []
        for dataset in selected:
            if dataset in {
                "security_lifecycle_events",
                "corporate_action_events",
                "security_trading_status_daily",
                "price_adjustment_factors",
            }:
                for row in symbol_rows:
                    symbol = str(row["symbol"])
                    items.append(
                        (
                            job_id,
                            dataset,
                            symbol,
                            symbol,
                            None,
                            "pending",
                            now,
                        )
                    )
            elif dataset == "security_suspensions":
                for trade_date in open_dates:
                    items.append(
                        (
                            job_id,
                            dataset,
                            trade_date,
                            None,
                            trade_date,
                            "pending",
                            now,
                        )
                    )

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO market_context_backfill_jobs (
                    job_id, status, symbol_scope, start_date, end_date,
                    datasets_json, total_items, created_at, updated_at
                ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    "all_current" if all_current else ",".join(row["symbol"] for row in symbol_rows),
                    start_date,
                    end_date,
                    _dump(selected),
                    len(items),
                    now,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO market_context_backfill_items (
                    job_id, dataset, item_key, symbol, trade_date, status,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                items,
            )
        return self.get_job(job_id)

    def run_job(
        self,
        job_id: str,
        *,
        publish: bool = True,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("another context backfill is already running")
        try:
            self.ensure_schema()
            job = self.get_job(job_id)
            if job["status"] in {"published", "completed", "rejected"}:
                return job
            self._mark_interrupted_items_pending(job_id)
            self._set_job_running(job_id)
            remaining = None if max_items is None else max(0, int(max_items))
            for dataset in REMOTE_DATASETS:
                if dataset not in job["datasets"]:
                    continue
                used = self._run_remote_dataset(job_id, dataset, remaining)
                if remaining is not None:
                    remaining -= used
                    if remaining <= 0:
                        self._finish_partial(job_id)
                        return self.get_job(job_id)
            for dataset in LOCAL_DATASETS:
                if dataset not in job["datasets"]:
                    continue
                used = self._run_local_dataset(job_id, dataset, remaining)
                if remaining is not None:
                    remaining -= used
                    if remaining <= 0:
                        self._finish_partial(job_id)
                        return self.get_job(job_id)

            summary = self._refresh_job_summary(job_id)
            if summary["quarantined_items"]:
                self._finish_job(
                    job_id,
                    "rejected",
                    error="one or more source requests remain quarantined",
                )
                return self.get_job(job_id)
            if summary["completed_items"] != summary["total_items"]:
                self._finish_partial(job_id)
                return self.get_job(job_id)

            self._set_job_status(job_id, "validating")
            release = self._validate_and_publish(job_id, publish=publish)
            if release.get("quality_passed") is False:
                return self.get_job(job_id)
            self._finish_job(
                job_id,
                "published" if release.get("data_version_id") else "completed",
                quality_report_id=release["quality_report_id"],
                data_version_id=release.get("data_version_id"),
            )
            return self.get_job(job_id)
        except Exception as error:
            self._finish_job(
                job_id,
                "failed",
                error=f"{type(error).__name__}: {error}",
            )
            raise
        finally:
            self._run_lock.release()

    def retry_quarantined(self, job_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_items
                SET status='pending', attempt_count=0, next_attempt_at=NULL,
                    last_error=NULL, updated_at=?
                WHERE job_id=? AND status<>'completed'
                """,
                (_utc_now(), job_id),
            )
            connection.execute(
                """
                UPDATE market_context_backfill_jobs
                SET status='queued', last_error=NULL, finished_at=NULL,
                    updated_at=?
                WHERE job_id=?
                """,
                (_utc_now(), job_id),
            )
        self._refresh_job_summary(job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                "SELECT * FROM market_context_backfill_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"context backfill job not found: {job_id}")
            grouped = connection.execute(
                """
                SELECT dataset, status, COUNT(*) AS item_count,
                       SUM(rows_written) AS rows_written,
                       SUM(CASE WHEN evidence_state='unknown' THEN 1 ELSE 0 END)
                           AS unknown_items
                FROM market_context_backfill_items
                WHERE job_id=?
                GROUP BY dataset, status
                ORDER BY dataset, status
                """,
                (job_id,),
            ).fetchall()
            quarantined = connection.execute(
                """
                SELECT dataset, item_key, attempt_count, last_error
                FROM market_context_backfill_items
                WHERE job_id=? AND status='quarantined'
                ORDER BY dataset, item_key LIMIT 100
                """,
                (job_id,),
            ).fetchall()
        payload = dict(row)
        payload["datasets"] = _load_json(payload.pop("datasets_json"), [])
        payload["item_summary"] = [dict(item) for item in grouped]
        payload["quarantined_sample"] = [dict(item) for item in quarantined]
        return payload

    def latest_job(self) -> dict[str, Any] | None:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                """
                SELECT job_id FROM market_context_backfill_jobs
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        return self.get_job(str(row["job_id"])) if row else None

    def _run_remote_dataset(
        self,
        job_id: str,
        dataset: str,
        limit: int | None,
    ) -> int:
        items = self._pending_items(job_id, dataset, limit)
        if not items:
            return 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._run_remote_item, dict(item)): item
                for item in items
            }
            for future in as_completed(futures):
                future.result()
                self._refresh_job_summary(job_id)
        return len(items)

    def _run_remote_item(self, item: Mapping[str, Any]) -> None:
        job_id = str(item["job_id"])
        dataset = str(item["dataset"])
        item_key = str(item["item_key"])
        last_error: Exception | None = None
        start_attempt = int(item["attempt_count"] or 0) + 1
        for attempt in range(start_attempt, self.retry_count + 1):
            self._set_item_running(job_id, dataset, item_key, attempt)
            try:
                rows = self._fetch_remote_rows(dataset, item)
                written = self._write_remote_rows(dataset, rows)
                evidence_state = (
                    "unknown"
                    if dataset == "security_lifecycle_events" and not rows
                    else "observed"
                )
                self._complete_item(
                    job_id,
                    dataset,
                    item_key,
                    rows_received=len(rows),
                    rows_written=written,
                    evidence_state=evidence_state,
                    result={
                        "empty_result": not bool(rows),
                        "evidence_state": evidence_state,
                    },
                )
                return
            except Exception as error:
                last_error = error
                if attempt < self.retry_count:
                    delay = self.base_backoff_seconds * (2 ** (attempt - 1))
                    self._set_item_retry(
                        job_id,
                        dataset,
                        item_key,
                        attempt=attempt,
                        error=f"{type(error).__name__}: {error}",
                        delay_seconds=delay,
                    )
                    self._sleep(delay)
        assert last_error is not None
        self._quarantine_item(
            job_id,
            dataset,
            item_key,
            attempt=self.retry_count,
            error=f"{type(last_error).__name__}: {last_error}",
        )

    def _fetch_remote_rows(
        self,
        dataset: str,
        item: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        if dataset == "security_lifecycle_events":
            return list(
                self.provider.fetch_security_lifecycle_events(
                    symbol=str(item["symbol"])
                )
            )
        if dataset == "corporate_action_events":
            return list(
                self.provider.fetch_corporate_actions(symbol=str(item["symbol"]))
            )
        if dataset == "security_suspensions":
            return list(
                self.provider.fetch_suspensions(trade_date=str(item["trade_date"]))
            )
        raise ValueError(f"unsupported remote dataset: {dataset}")

    def _write_remote_rows(
        self,
        dataset: str,
        rows: Iterable[Mapping[str, Any]],
    ) -> int:
        materialized = list(rows)
        if dataset == "security_lifecycle_events":
            return self.governance_store.upsert_lifecycle_events(materialized)
        if dataset == "corporate_action_events":
            return self.governance_store.upsert_corporate_actions(materialized)
        if dataset == "security_suspensions":
            return self.governance_store.upsert_trading_statuses(materialized)
        raise ValueError(f"unsupported remote dataset: {dataset}")

    def _run_local_dataset(
        self,
        job_id: str,
        dataset: str,
        limit: int | None,
    ) -> int:
        items = self._pending_items(job_id, dataset, limit)
        for item in items:
            self._set_item_running(
                job_id,
                dataset,
                str(item["item_key"]),
                int(item["attempt_count"] or 0) + 1,
            )
            try:
                if dataset == "security_trading_status_daily":
                    written, unknown = self._derive_status_rows(
                        symbol=str(item["symbol"]),
                        start_date=str(item["start_date"]),
                        end_date=str(item["end_date"]),
                    )
                    evidence_state = "unknown" if unknown else "observed"
                    result = {"unknown_rows": unknown}
                elif dataset == "price_adjustment_factors":
                    written = self._derive_factor_rows(
                        symbol=str(item["symbol"]),
                        end_date=str(item["end_date"]),
                    )
                    evidence_state = "observed" if written else "unknown"
                    result = {"missing_join_rows": written == 0}
                else:
                    raise ValueError(f"unsupported local dataset: {dataset}")
                self._complete_item(
                    job_id,
                    dataset,
                    str(item["item_key"]),
                    rows_received=written,
                    rows_written=written,
                    evidence_state=evidence_state,
                    result=result,
                )
            except Exception as error:
                self._quarantine_item(
                    job_id,
                    dataset,
                    str(item["item_key"]),
                    attempt=int(item["attempt_count"] or 0) + 1,
                    error=f"{type(error).__name__}: {error}",
                )
            self._refresh_job_summary(job_id)
        return len(items)

    def _derive_status_rows(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[int, int]:
        observed_at = _utc_now()
        normal_evidence = _dump({"derivation": "positive_raw_daily_bar"})
        unknown_evidence = _dump(
            {"reason": "no_authoritative_status_or_positive_bar_evidence"}
        )
        normal_hash = sha256(normal_evidence.encode("utf-8")).hexdigest()
        unknown_hash = sha256(unknown_evidence.encode("utf-8")).hexdigest()
        with closing(self._connect()) as connection, connection:
            first_evidence = connection.execute(
                """
                SELECT COALESCE(
                    (SELECT MIN(effective_from)
                     FROM security_lifecycle_events
                     WHERE symbol=? AND event_type='listed'
                       AND effective_from IS NOT NULL),
                    (SELECT MIN(trade_date) FROM market_daily_prices
                     WHERE symbol=? AND adjustment='raw')
                ) AS first_date
                """,
                (symbol, symbol),
            ).fetchone()["first_date"]
            if not first_evidence:
                return 0, 0
            effective_start = max(str(first_evidence), start_date)
            before = connection.total_changes
            connection.execute(
                """
                INSERT INTO security_trading_status_daily (
                    symbol, trade_date, status, is_tradable,
                    suspension_reason, expected_resume_date, source,
                    source_observed_at, source_payload_hash, evidence_json
                )
                SELECT ?, c.trade_date,
                       CASE
                           WHEN existing.status='suspended' THEN 'suspended'
                           WHEN p.symbol IS NOT NULL THEN 'normal'
                           ELSE 'unknown'
                       END,
                       CASE
                           WHEN existing.status='suspended' THEN 0
                           WHEN p.symbol IS NOT NULL THEN 1
                           ELSE NULL
                       END,
                       CASE WHEN existing.status='suspended'
                            THEN existing.suspension_reason END,
                       CASE WHEN existing.status='suspended'
                            THEN existing.expected_resume_date END,
                       CASE
                           WHEN existing.status='suspended' THEN existing.source
                           WHEN p.symbol IS NOT NULL
                               THEN 'canonical_market_daily_prices:positive_bar'
                           ELSE 'stage78.3:evidence_gap'
                       END,
                       CASE WHEN existing.status='suspended'
                            THEN existing.source_observed_at ELSE ? END,
                       CASE
                           WHEN existing.status='suspended'
                               THEN existing.source_payload_hash
                           WHEN p.symbol IS NOT NULL THEN ?
                           ELSE ?
                       END,
                       CASE
                           WHEN existing.status='suspended'
                               THEN existing.evidence_json
                           WHEN p.symbol IS NOT NULL THEN ?
                           ELSE ?
                       END
                FROM market_trade_calendar c
                LEFT JOIN market_daily_prices p
                  ON p.symbol=? AND p.trade_date=c.trade_date
                 AND p.adjustment='raw'
                LEFT JOIN security_trading_status_daily existing
                  ON existing.symbol=? AND existing.trade_date=c.trade_date
                WHERE c.market='CN' AND c.is_open=1
                  AND c.trade_date>=? AND c.trade_date<=?
                ON CONFLICT(symbol, trade_date) DO UPDATE SET
                    status=excluded.status,
                    is_tradable=excluded.is_tradable,
                    suspension_reason=excluded.suspension_reason,
                    expected_resume_date=excluded.expected_resume_date,
                    source=excluded.source,
                    source_observed_at=excluded.source_observed_at,
                    source_payload_hash=excluded.source_payload_hash,
                    evidence_json=excluded.evidence_json
                """,
                (
                    symbol,
                    observed_at,
                    normal_hash,
                    unknown_hash,
                    normal_evidence,
                    unknown_evidence,
                    symbol,
                    symbol,
                    effective_start,
                    end_date,
                ),
            )
            written = connection.total_changes - before
            unknown = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM security_trading_status_daily
                    WHERE symbol=? AND trade_date>=? AND trade_date<=?
                      AND status='unknown'
                    """,
                    (symbol, effective_start, end_date),
                ).fetchone()[0]
            )
        return written, unknown

    def _derive_factor_rows(self, *, symbol: str, end_date: str) -> int:
        observed_at = _utc_now()
        with closing(self._connect()) as connection, connection:
            before = connection.total_changes
            for method, mode in (
                ("observed_qfq_close_ratio", "qfq"),
                ("observed_hfq_close_ratio", "hfq"),
            ):
                connection.execute(
                    """
                    INSERT INTO price_adjustment_factors (
                        symbol, trade_date, factor_method, factor, base_date,
                        source, source_observed_at, derived_from_action_version,
                        quality_status, evidence_json
                    )
                    SELECT raw.symbol, raw.trade_date, ?,
                           adjusted.close / raw.close, ?,
                           'derived:canonical_raw_adjusted_close_ratio', ?,
                           NULL, 'passed',
                           json_object(
                               'raw_close', raw.close,
                               'adjusted_close', adjusted.close,
                               'adjustment', ?,
                               'derivation', 'adjusted_close/raw_close'
                           )
                    FROM market_daily_prices raw
                    JOIN market_daily_prices adjusted
                      ON adjusted.symbol=raw.symbol
                     AND adjusted.trade_date=raw.trade_date
                     AND adjusted.adjustment=?
                    WHERE raw.symbol=? AND raw.adjustment='raw'
                      AND raw.trade_date<=?
                      AND raw.close>0 AND adjusted.close>0
                    ON CONFLICT(symbol, trade_date, factor_method) DO UPDATE SET
                        factor=excluded.factor,
                        base_date=excluded.base_date,
                        source=excluded.source,
                        source_observed_at=excluded.source_observed_at,
                        quality_status=excluded.quality_status,
                        evidence_json=excluded.evidence_json
                    """,
                    (
                        method,
                        end_date,
                        observed_at,
                        mode,
                        mode,
                        symbol,
                        end_date,
                    ),
                )
            return connection.total_changes - before

    def _validate_and_publish(
        self,
        job_id: str,
        *,
        publish: bool,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        checks, metrics = self._quality_checks(job_id)
        passed = all(bool(check["passed"]) for check in checks)
        payload = {
            "stage": "78.3",
            "scope": "full_market_context_backfill",
            "job_id": job_id,
            "start_date": job["start_date"],
            "end_date": job["end_date"],
            "datasets": job["datasets"],
            "checks": checks,
            "metrics": metrics,
            "source_boundary": (
                "AKShare public aggregation is a local-research candidate source; "
                "commercial authorization and SLA are not asserted."
            ),
            "generated_at": _utc_now(),
        }
        report_hash = _hash_mapping(payload)
        report_id = f"stage783-{job['end_date'].replace('-', '')}-{report_hash[:12]}"
        report = self.governance_store.save_quality_report(
            quality_report_id=report_id,
            rule_version="stage78.3-quality-v1",
            status="passed" if passed else "failed",
            payload=payload,
        )
        if not passed:
            self._finish_job(
                job_id,
                "rejected",
                error="stage 78.3 quality gate failed",
                quality_report_id=report_id,
            )
            return {
                "quality_report_id": report_id,
                "quality_passed": False,
            }
        if not publish:
            return {"quality_report_id": report_id}
        version = self.governance_store.publish_data_version(
            as_of_trade_date=str(job["end_date"]),
            quality_report_id=report_id,
            members=self._version_members(job_id),
            notes=(
                f"stage78.3 full-market context backfill job={job_id}; "
                "unknown status is preserved where evidence is unavailable"
            ),
        )
        return {
            "quality_report_id": report["quality_report_id"],
            "data_version_id": version["data_version_id"],
        }

    def _quality_checks(
        self,
        job_id: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        cutoff = str(self.get_job(job_id)["end_date"])
        with closing(self._connect(read_only=True)) as connection:
            item = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                       SUM(CASE WHEN status='quarantined' THEN 1 ELSE 0 END) AS quarantined,
                       SUM(CASE WHEN evidence_state='unknown' THEN 1 ELSE 0 END) AS unknown_items
                FROM market_context_backfill_items WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            lifecycle_unknown_items = int(connection.execute(
                """
                SELECT COUNT(*) FROM market_context_backfill_items
                WHERE job_id=? AND dataset='security_lifecycle_events'
                  AND evidence_state='unknown'
                """,
                (job_id,),
            ).fetchone()[0])
            current_symbols = int(connection.execute(
                "SELECT COUNT(*) FROM market_symbols WHERE listing_status='current'"
            ).fetchone()[0])
            metrics = {
                "current_symbols": current_symbols,
                "lifecycle_symbols": int(connection.execute(
                    """
                    SELECT COUNT(DISTINCT e.symbol)
                    FROM security_lifecycle_events e
                    JOIN market_symbols m ON m.symbol=e.symbol
                    WHERE m.listing_status='current' AND e.effective_from<=?
                    """,
                    (cutoff,),
                ).fetchone()[0]),
                "corporate_action_symbols": int(connection.execute(
                    """
                    SELECT COUNT(DISTINCT e.symbol)
                    FROM corporate_action_events e
                    JOIN market_symbols m ON m.symbol=e.symbol
                    WHERE m.listing_status='current'
                      AND COALESCE(e.announcement_date, e.ex_date)<=?
                    """,
                    (cutoff,),
                ).fetchone()[0]),
                "trading_status_rows": int(connection.execute(
                    """
                    SELECT COUNT(*) FROM security_trading_status_daily s
                    JOIN market_symbols m ON m.symbol=s.symbol
                    WHERE m.listing_status='current' AND s.trade_date<=?
                    """,
                    (cutoff,),
                ).fetchone()[0]),
                "trading_status_unknown_rows": int(connection.execute(
                    """
                    SELECT COUNT(*) FROM security_trading_status_daily s
                    JOIN market_symbols m ON m.symbol=s.symbol
                    WHERE m.listing_status='current' AND s.trade_date<=?
                      AND s.status='unknown'
                    """,
                    (cutoff,),
                ).fetchone()[0]),
                "adjustment_factor_rows": int(connection.execute(
                    """
                    SELECT COUNT(*) FROM price_adjustment_factors f
                    JOIN market_symbols m ON m.symbol=f.symbol
                    WHERE m.listing_status='current' AND f.trade_date<=?
                    """,
                    (cutoff,),
                ).fetchone()[0]),
                "invalid_factor_rows": int(connection.execute(
                    """
                    SELECT COUNT(*) FROM price_adjustment_factors f
                    JOIN market_symbols m ON m.symbol=f.symbol
                    WHERE m.listing_status='current' AND f.trade_date<=?
                      AND (f.factor<=0 OR f.factor IS NULL)
                    """,
                    (cutoff,),
                ).fetchone()[0]),
                "context_duplicate_groups": {
                    "lifecycle": int(connection.execute(
                        """
                        SELECT COUNT(*) FROM (
                            SELECT 1 FROM security_lifecycle_events
                            GROUP BY symbol, event_type, COALESCE(effective_from, ''),
                                     COALESCE(announced_at, '')
                            HAVING COUNT(*)>1
                        )
                        """
                    ).fetchone()[0]),
                    "corporate_actions": int(connection.execute(
                        """
                        SELECT COUNT(*) FROM (
                            SELECT 1 FROM corporate_action_events
                            GROUP BY symbol, action_type, COALESCE(report_period, ''),
                                     COALESCE(announcement_date, ''), COALESCE(ex_date, '')
                            HAVING COUNT(*)>1
                        )
                        """
                    ).fetchone()[0]),
                },
            }
        item_evidence = dict(item)
        checks = [
            _check(
                "all_queue_items_completed",
                int(item["total"] or 0) == int(item["completed"] or 0)
                and int(item["quarantined"] or 0) == 0,
                item_evidence,
            ),
            _check(
                "lifecycle_coverage_is_explicit",
                metrics["lifecycle_symbols"] + lifecycle_unknown_items >= current_symbols,
                {
                    "observed_symbols": metrics["lifecycle_symbols"],
                    "unknown_items": lifecycle_unknown_items,
                    "current_symbols": current_symbols,
                },
            ),
            _check(
                "trading_status_materialized",
                metrics["trading_status_rows"] > 0,
                {
                    "row_count": metrics["trading_status_rows"],
                    "unknown_count": metrics["trading_status_unknown_rows"],
                },
            ),
            _check(
                "adjustment_factors_positive",
                metrics["adjustment_factor_rows"] > 0
                and metrics["invalid_factor_rows"] == 0,
                {
                    "row_count": metrics["adjustment_factor_rows"],
                    "invalid_count": metrics["invalid_factor_rows"],
                },
            ),
            _check(
                "context_natural_keys_unique",
                all(value == 0 for value in metrics["context_duplicate_groups"].values()),
                metrics["context_duplicate_groups"],
            ),
        ]
        return checks, metrics

    def _version_members(self, job_id: str) -> list[dict[str, Any]]:
        job = self.get_job(job_id)
        datasets = (
            "market_daily_prices",
            "market_trade_calendar",
            "market_index_daily_prices",
            "security_lifecycle_events",
            "security_trading_status_daily",
            "corporate_action_events",
            "price_adjustment_factors",
        )
        date_columns = {
            "market_daily_prices": "trade_date",
            "market_trade_calendar": "trade_date",
            "market_index_daily_prices": "trade_date",
            "security_lifecycle_events": "effective_from",
            "security_trading_status_daily": "trade_date",
            "corporate_action_events": "COALESCE(announcement_date, ex_date)",
            "price_adjustment_factors": "trade_date",
        }
        symbol_columns = {
            "market_trade_calendar": "market",
            "market_index_daily_prices": "index_symbol",
        }
        context_datasets = {
            "security_lifecycle_events",
            "security_trading_status_daily",
            "corporate_action_events",
            "price_adjustment_factors",
        }
        members: list[dict[str, Any]] = []
        with closing(self._connect(read_only=True)) as connection:
            for dataset in datasets:
                adjustments = (
                    ("raw", "qfq", "hfq")
                    if dataset == "market_daily_prices"
                    else ("",)
                )
                for adjustment in adjustments:
                    conditions = []
                    values: list[Any] = []
                    if adjustment:
                        conditions.append("adjustment=?")
                        values.append(adjustment)
                    conditions.append(f"{date_columns[dataset]}<=?")
                    values.append(str(job["end_date"]))
                    if dataset in context_datasets:
                        conditions.append(
                            "symbol IN (SELECT symbol FROM market_symbols "
                            "WHERE listing_status='current')"
                        )
                    where = "WHERE " + " AND ".join(conditions)
                    symbol_column = symbol_columns.get(dataset, "symbol")
                    row = connection.execute(
                        f"""
                        SELECT COUNT(*) AS row_count,
                               COUNT(DISTINCT {symbol_column}) AS symbol_count,
                               MIN({date_columns[dataset]}) AS min_date,
                               MAX({date_columns[dataset]}) AS max_date
                        FROM {dataset} {where}
                        """,
                        tuple(values),
                    ).fetchone()
                    symbol_scope = (
                        "CN"
                        if dataset == "market_trade_calendar"
                        else "000300"
                        if dataset == "market_index_daily_prices"
                        else "canonical_all_catalogued_a_shares"
                        if dataset == "market_daily_prices"
                        else "all_current_a_shares"
                    )
                    summary = {
                        "dataset": dataset,
                        "adjustment": adjustment,
                        "symbol_scope": symbol_scope,
                        "row_count": int(row["row_count"] or 0),
                        "symbol_count": int(row["symbol_count"] or 0),
                        "min_date": row["min_date"],
                        "max_date": row["max_date"],
                        "source": (
                            "canonical_a_share_sqlite"
                            if dataset == "market_daily_prices"
                            else "stage78.3_context_backfill"
                        ),
                        "sync_run_ref": job_id,
                        "quality_status": "passed",
                        "details": {
                            "full_market_context": dataset in context_datasets,
                            "unknown_preserved": dataset
                            == "security_trading_status_daily",
                            "as_of_trade_date": job["end_date"],
                            "availability_date": (
                                "announcement_date"
                                if dataset == "corporate_action_events"
                                else date_columns[dataset]
                            ),
                        },
                    }
                    members.append({**summary, "content_hash": _hash_mapping(summary)})
        return members
    def _symbols(
        self,
        requested: Sequence[str] | None,
    ) -> list[dict[str, str]]:
        with closing(self._connect(read_only=True)) as connection:
            if requested is None:
                rows = connection.execute(
                    """
                    SELECT symbol FROM market_symbols
                    WHERE listing_status='current' ORDER BY symbol
                    """
                ).fetchall()
            else:
                normalized = sorted({_symbol(value) for value in requested})
                placeholders = ",".join("?" for _ in normalized)
                rows = connection.execute(
                    f"""
                    SELECT symbol FROM market_symbols
                    WHERE symbol IN ({placeholders}) ORDER BY symbol
                    """,
                    tuple(normalized),
                ).fetchall()
        return [dict(row) for row in rows]

    def _open_dates(self, start_date: str, end_date: str) -> list[str]:
        with closing(self._connect(read_only=True)) as connection:
            return [
                str(row["trade_date"])
                for row in connection.execute(
                    """
                    SELECT trade_date FROM market_trade_calendar
                    WHERE market='CN' AND is_open=1
                      AND trade_date>=? AND trade_date<=?
                    ORDER BY trade_date
                    """,
                    (start_date, end_date),
                ).fetchall()
            ]

    def _pending_items(
        self,
        job_id: str,
        dataset: str,
        limit: int | None,
    ) -> list[sqlite3.Row]:
        sql = """
            SELECT i.*, j.start_date, j.end_date
            FROM market_context_backfill_items i
            JOIN market_context_backfill_jobs j ON j.job_id=i.job_id
            WHERE i.job_id=? AND i.dataset=?
              AND i.status IN ('pending','retry_wait')
            ORDER BY i.item_key
        """
        values: list[Any] = [job_id, dataset]
        if limit is not None:
            sql += " LIMIT ?"
            values.append(max(0, int(limit)))
        with closing(self._connect(read_only=True)) as connection:
            return connection.execute(sql, tuple(values)).fetchall()

    def _mark_interrupted_items_pending(self, job_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_items
                SET status='pending', updated_at=?
                WHERE job_id=? AND status='running'
                """,
                (_utc_now(), job_id),
            )

    def _set_job_running(self, job_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_jobs
                SET status='running', started_at=COALESCE(started_at, ?),
                    finished_at=NULL, last_error=NULL, updated_at=?
                WHERE job_id=?
                """,
                (_utc_now(), _utc_now(), job_id),
            )

    def _set_job_status(self, job_id: str, status: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_jobs
                SET status=?, updated_at=? WHERE job_id=?
                """,
                (status, _utc_now(), job_id),
            )

    def _set_item_running(
        self,
        job_id: str,
        dataset: str,
        item_key: str,
        attempt: int,
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_items
                SET status='running', attempt_count=?, next_attempt_at=NULL,
                    updated_at=?
                WHERE job_id=? AND dataset=? AND item_key=?
                """,
                (attempt, _utc_now(), job_id, dataset, item_key),
            )

    def _set_item_retry(
        self,
        job_id: str,
        dataset: str,
        item_key: str,
        *,
        attempt: int,
        error: str,
        delay_seconds: float,
    ) -> None:
        next_at = datetime.fromtimestamp(
            time.time() + delay_seconds,
            tz=timezone.utc,
        ).isoformat(timespec="seconds")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_items
                SET status='retry_wait', attempt_count=?, next_attempt_at=?,
                    last_error=?, updated_at=?
                WHERE job_id=? AND dataset=? AND item_key=?
                """,
                (
                    attempt,
                    next_at,
                    error,
                    _utc_now(),
                    job_id,
                    dataset,
                    item_key,
                ),
            )

    def _complete_item(
        self,
        job_id: str,
        dataset: str,
        item_key: str,
        *,
        rows_received: int,
        rows_written: int,
        evidence_state: str,
        result: Mapping[str, Any],
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_items
                SET status='completed', rows_received=?, rows_written=?,
                    evidence_state=?, next_attempt_at=NULL, last_error=NULL,
                    result_json=?, updated_at=?
                WHERE job_id=? AND dataset=? AND item_key=?
                """,
                (
                    rows_received,
                    rows_written,
                    evidence_state,
                    _dump(dict(result)),
                    _utc_now(),
                    job_id,
                    dataset,
                    item_key,
                ),
            )

    def _quarantine_item(
        self,
        job_id: str,
        dataset: str,
        item_key: str,
        *,
        attempt: int,
        error: str,
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_items
                SET status='quarantined', attempt_count=?,
                    next_attempt_at=NULL, last_error=?, updated_at=?
                WHERE job_id=? AND dataset=? AND item_key=?
                """,
                (
                    attempt,
                    error,
                    _utc_now(),
                    job_id,
                    dataset,
                    item_key,
                ),
            )

    def _refresh_job_summary(self, job_id: str) -> dict[str, int]:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total_items,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)
                           AS completed_items,
                       SUM(CASE WHEN status='quarantined' THEN 1 ELSE 0 END)
                           AS quarantined_items,
                       SUM(rows_written) AS rows_written,
                       SUM(CASE WHEN evidence_state='unknown' THEN 1 ELSE 0 END)
                           AS unknown_items
                FROM market_context_backfill_items WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            values = {key: int(row[key] or 0) for key in row.keys()}
            connection.execute(
                """
                UPDATE market_context_backfill_jobs
                SET total_items=?, completed_items=?, quarantined_items=?,
                    rows_written=?, unknown_items=?, updated_at=?
                WHERE job_id=?
                """,
                (
                    values["total_items"],
                    values["completed_items"],
                    values["quarantined_items"],
                    values["rows_written"],
                    values["unknown_items"],
                    _utc_now(),
                    job_id,
                ),
            )
        return values

    def _finish_partial(self, job_id: str) -> None:
        self._refresh_job_summary(job_id)
        self._set_job_status(job_id, "queued")

    def _finish_job(
        self,
        job_id: str,
        status: str,
        *,
        error: str | None = None,
        quality_report_id: str | None = None,
        data_version_id: str | None = None,
    ) -> None:
        self._refresh_job_summary(job_id)
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE market_context_backfill_jobs
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
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection


def _datasets(values: Sequence[str]) -> list[str]:
    selected = []
    for value in values:
        dataset = str(value).strip()
        if dataset not in ALL_DATASETS:
            raise ValueError(f"unsupported context dataset: {dataset}")
        if dataset not in selected:
            selected.append(dataset)
    if not selected:
        raise ValueError("at least one context dataset is required")
    return selected


def _symbol(value: Any) -> str:
    text = str(value or "").strip().split(".", 1)[0]
    if not text.isdigit():
        raise ValueError(f"invalid symbol: {value}")
    return text.zfill(6)


def _check(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


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
