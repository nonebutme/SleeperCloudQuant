"""SQLite persistence for governed factor-research tasks and reports."""

from __future__ import annotations

import json
import hashlib
import math
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class SqliteFactorResearchStore:
    """Own the stage-87 runtime database; market databases remain read-only."""

    def __init__(
        self,
        database_path: str | Path = "var/runtime/factor_research.sqlite3",
        *,
        index_store: Any | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self._index_store = index_store
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()
        self.recover_interrupted_tasks()

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS factor_definitions (
                    factor_id TEXT NOT NULL,
                    factor_version TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    metadata_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (factor_id, factor_version)
                );
                CREATE TABLE IF NOT EXISTS factor_research_tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    preflight_json TEXT NOT NULL,
                    progress_json TEXT NOT NULL,
                    error_json TEXT NOT NULL,
                    data_version_id TEXT NOT NULL,
                    quality_report_id TEXT NOT NULL,
                    report_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_factor_tasks_status_created
                    ON factor_research_tasks (status, created_at DESC);
                CREATE TABLE IF NOT EXISTS factor_research_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    snapshot_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES factor_research_tasks(task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_snapshots_task_type
                    ON factor_research_snapshots (task_id, snapshot_type);
                CREATE TABLE IF NOT EXISTS factor_research_observations (
                    task_id TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    raw_value REAL,
                    processed_value REAL,
                    aligned_value REAL,
                    forward_returns_json TEXT NOT NULL,
                    industry TEXT,
                    group_no INTEGER,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (task_id, trade_date, symbol),
                    FOREIGN KEY (task_id) REFERENCES factor_research_tasks(task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_observations_task_date
                    ON factor_research_observations (task_id, trade_date, group_no);
                CREATE TABLE IF NOT EXISTS factor_research_daily_universe (
                    task_id TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    universe_count INTEGER NOT NULL,
                    PRIMARY KEY (task_id, trade_date),
                    FOREIGN KEY (task_id) REFERENCES factor_research_tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS factor_research_daily_universe_batches (
                    task_id TEXT NOT NULL,
                    batch_offset INTEGER NOT NULL,
                    trade_date TEXT NOT NULL,
                    universe_count INTEGER NOT NULL,
                    PRIMARY KEY (task_id, batch_offset, trade_date),
                    FOREIGN KEY (task_id) REFERENCES factor_research_tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS factor_research_reports (
                    report_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE,
                    context_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES factor_research_tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS factor_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    factor_id TEXT NOT NULL,
                    factor_version TEXT NOT NULL,
                    source_task_id TEXT NOT NULL UNIQUE,
                    context_hash TEXT NOT NULL,
                    data_version_id TEXT NOT NULL,
                    quality_report_id TEXT NOT NULL,
                    adjustment TEXT NOT NULL,
                    pool_snapshot_hash TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_task_id) REFERENCES factor_research_tasks(task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_artifacts_factor_created
                    ON factor_artifacts (factor_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS factor_artifact_governance (
                    artifact_id TEXT PRIMARY KEY,
                    artifact_content_hash TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'pending',
                    registration_status TEXT NOT NULL DEFAULT 'unregistered',
                    policy_id TEXT NOT NULL DEFAULT '',
                    reviewer TEXT NOT NULL DEFAULT '',
                    decision_note TEXT NOT NULL DEFAULT '',
                    reviewed_at TEXT,
                    registered_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (artifact_id) REFERENCES factor_artifacts(artifact_id)
                );
                CREATE TABLE IF NOT EXISTS factor_artifact_governance_events (
                    event_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (artifact_id) REFERENCES factor_artifacts(artifact_id)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_governance_events_artifact
                    ON factor_artifact_governance_events (artifact_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS factor_artifact_monitoring_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (artifact_id) REFERENCES factor_artifacts(artifact_id)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_monitoring_artifact_created
                    ON factor_artifact_monitoring_snapshots (artifact_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS factor_oos_reveals (
                    report_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    revealed_at TEXT NOT NULL,
                    FOREIGN KEY (report_id) REFERENCES factor_research_reports(report_id),
                    FOREIGN KEY (task_id) REFERENCES factor_research_tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS factor_artifact_values (
                    artifact_id TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    value REAL NOT NULL,
                    aligned_value REAL,
                    PRIMARY KEY (artifact_id, trade_date, symbol),
                    FOREIGN KEY (artifact_id) REFERENCES factor_artifacts(artifact_id)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_artifact_values_lookup
                    ON factor_artifact_values (artifact_id, symbol, trade_date);
                CREATE TABLE IF NOT EXISTS factor_optimization_tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    artifact_content_hash TEXT NOT NULL,
                    source_task_id TEXT NOT NULL,
                    value_field TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    progress_json TEXT NOT NULL,
                    error_json TEXT NOT NULL,
                    report_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY (artifact_id) REFERENCES factor_artifacts(artifact_id),
                    FOREIGN KEY (source_task_id) REFERENCES factor_research_tasks(task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_optimization_tasks_status_created
                    ON factor_optimization_tasks (status, created_at DESC);
                CREATE TABLE IF NOT EXISTS factor_optimization_reports (
                    report_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE,
                    artifact_id TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES factor_optimization_tasks(task_id),
                    FOREIGN KEY (artifact_id) REFERENCES factor_artifacts(artifact_id)
                );
                CREATE TABLE IF NOT EXISTS factor_index_component_intervals (
                    index_code TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    source TEXT NOT NULL,
                    source_version TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY (index_code, symbol, valid_from, source)
                );
                CREATE INDEX IF NOT EXISTS idx_factor_index_components_asof
                    ON factor_index_component_intervals
                    (index_code, valid_from, valid_to, symbol);
                """
            )

    def save_definitions(self, definitions: Sequence[Mapping[str, Any]]) -> None:
        now = _utc_now()
        from factor_lab.research_core import canonical_hash

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO factor_definitions (
                    factor_id, factor_version, metadata_json, metadata_hash, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(factor_id, factor_version) DO UPDATE SET
                    metadata_json=excluded.metadata_json,
                    metadata_hash=excluded.metadata_hash
                """,
                [
                    (
                        str(item["factor_id"]),
                        str(item["factor_version"]),
                        _dump(item),
                        canonical_hash(item),
                        now,
                    )
                    for item in definitions
                ],
            )

    def list_definitions(self, *, latest_only: bool = True) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT metadata_json, metadata_hash, created_at
                   FROM factor_definitions ORDER BY factor_id, factor_version"""
            ).fetchall()
        result = []
        for row in rows:
            payload = _load(row["metadata_json"])
            payload["metadata_hash"] = row["metadata_hash"]
            payload["registered_at"] = row["created_at"]
            result.append(payload)
        if not latest_only:
            return result
        latest: dict[str, dict[str, Any]] = {}
        for item in result:
            factor_id = str(item.get("factor_id") or "")
            previous = latest.get(factor_id)
            if previous is None or _version_number(item.get("factor_version")) > _version_number(
                previous.get("factor_version")
            ):
                latest[factor_id] = item
        return [latest[key] for key in sorted(latest)]

    def get_definition(
        self, factor_id: str, factor_version: str | None = None,
    ) -> dict[str, Any] | None:
        candidates = [
            item for item in self.list_definitions(latest_only=False)
            if str(item.get("factor_id")) == str(factor_id)
            and (not factor_version or str(item.get("factor_version")) == str(factor_version))
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: _version_number(item.get("factor_version")))

    def create_definition(self, definition: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one immutable definition version."""

        from factor_lab.research_core import canonical_hash

        payload = dict(definition)
        now = _utc_now()
        metadata_hash = canonical_hash(payload)
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO factor_definitions (
                           factor_id, factor_version, metadata_json, metadata_hash, created_at
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        str(payload["factor_id"]), str(payload["factor_version"]),
                        _dump(payload), metadata_hash, now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("factor definition version already exists") from error
        return {**payload, "metadata_hash": metadata_hash, "registered_at": now}
    def create_task(
        self,
        *,
        task_id: str,
        config: Mapping[str, Any],
        context: Mapping[str, Any],
        context_hash: str,
        preflight: Mapping[str, Any],
        data_version_id: str,
        quality_report_id: str,
        pool_snapshot: Mapping[str, Any],
    ) -> dict[str, Any]:
        now = _utc_now()
        snapshot_id = f"{task_id}-pool"
        from factor_lab.research_core import canonical_hash

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO factor_research_tasks (
                    task_id, status, config_json, context_json, context_hash,
                    preflight_json, progress_json, error_json, data_version_id,
                    quality_report_id, report_id, created_at, updated_at,
                    started_at, finished_at
                ) VALUES (?, 'ready', ?, ?, ?, ?, ?, '{}', ?, ?, NULL, ?, ?, NULL, NULL)
                """,
                (
                    task_id,
                    _dump(config),
                    _dump(context),
                    context_hash,
                    _dump(preflight),
                    _dump(
                        {
                            "phase": "ready",
                            "total_symbols": len(pool_snapshot.get("symbols") or []),
                            "processed_symbols": 0,
                            "observation_count": 0,
                            "percent": 0.0,
                        }
                    ),
                    data_version_id,
                    quality_report_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO factor_research_snapshots (
                    snapshot_id, task_id, snapshot_type, payload_json,
                    content_hash, created_at
                ) VALUES (?, ?, 'pool', ?, ?, ?)
                """,
                (
                    snapshot_id,
                    task_id,
                    _dump(pool_snapshot),
                    canonical_hash(pool_snapshot),
                    now,
                ),
            )
        return self.get_task(task_id)

    def update_task(self, task_id: str, **values: Any) -> None:
        allowed = {
            "status",
            "progress_json",
            "error_json",
            "report_id",
            "started_at",
            "finished_at",
            "preflight_json",
        }
        selected = {key: value for key, value in values.items() if key in allowed}
        if not selected:
            return
        selected["updated_at"] = _utc_now()
        columns = ", ".join(f"{key}=?" for key in selected)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE factor_research_tasks SET {columns} WHERE task_id=?",
                (*selected.values(), task_id),
            )

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM factor_research_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                return {"task_id": task_id, "status": "not_found"}
            snapshots = connection.execute(
                """SELECT snapshot_id, snapshot_type, payload_json, content_hash, created_at
                   FROM factor_research_snapshots WHERE task_id=?
                   ORDER BY created_at, snapshot_id""",
                (task_id,),
            ).fetchall()
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "config": _load(row["config_json"]),
            "context": _load(row["context_json"]),
            "context_hash": row["context_hash"],
            "preflight": _load(row["preflight_json"]),
            "progress": _load(row["progress_json"]),
            "error": _load(row["error_json"]),
            "data_version_id": row["data_version_id"],
            "quality_report_id": row["quality_report_id"],
            "report_id": row["report_id"],
            "snapshots": [
                {
                    "snapshot_id": item["snapshot_id"],
                    "snapshot_type": item["snapshot_type"],
                    "payload": _load(item["payload_json"]),
                    "content_hash": item["content_hash"],
                    "created_at": item["created_at"],
                }
                for item in snapshots
            ],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def list_tasks(self, *, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
        values: list[Any] = []
        where = ""
        if status:
            where = "WHERE status=?"
            values.append(status)
        values.append(max(1, min(int(limit), 200)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT task_id FROM factor_research_tasks {where}
                    ORDER BY created_at DESC LIMIT ?""",
                values,
            ).fetchall()
        return [self.get_task(str(row["task_id"])) for row in rows]

    def replace_observations(
        self,
        task_id: str,
        observations: Sequence[Mapping[str, Any]],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM factor_research_observations WHERE task_id=?", (task_id,)
            )
            connection.executemany(
                """
                INSERT INTO factor_research_observations (
                    task_id, trade_date, symbol, raw_value, processed_value,
                    aligned_value, forward_returns_json, industry, group_no,
                    evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        task_id,
                        str(row["trade_date"]),
                        str(row["symbol"]),
                        row.get("raw_value"),
                        row.get("processed_value"),
                        row.get("aligned_value"),
                        _dump(row.get("forward_returns") or {}),
                        str(row.get("industry") or "") or None,
                        row.get("group_no"),
                        _dump(row.get("evidence") or {}),
                    )
                    for row in observations
                ],
            )

    def fetch_observations(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM factor_research_observations
                   WHERE task_id=? ORDER BY trade_date, symbol""",
                (task_id,),
            ).fetchall()
        return [_observation_dict(row) for row in rows]

    def save_report(
        self,
        *,
        report_id: str,
        task_id: str,
        context_hash: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        from factor_lab.research_core import canonical_hash

        payload_hash = canonical_hash(payload)
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM factor_research_reports WHERE report_id=?",
                (report_id,),
            ).fetchone()
            if existing is not None and str(existing["payload_hash"]) != payload_hash:
                raise ValueError("factor research reports are immutable")
            connection.execute(
                """
                INSERT OR IGNORE INTO factor_research_reports (
                    report_id, task_id, context_hash, payload_json, payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (report_id, task_id, context_hash, _dump(payload), payload_hash, now),
            )
        return self.get_report(report_id)

    def get_report(self, report_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM factor_research_reports WHERE report_id=?", (report_id,)
            ).fetchone()
        if row is None:
            return {"report_id": report_id, "status": "not_found"}
        return {
            "report_id": row["report_id"],
            "task_id": row["task_id"],
            "status": "ready",
            "context_hash": row["context_hash"],
            "payload": _load(row["payload_json"]),
            "payload_hash": row["payload_hash"],
            "created_at": row["created_at"],
        }

    def list_reports(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT report_id FROM factor_research_reports
                   ORDER BY created_at DESC LIMIT ?""",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [self.get_report(str(row["report_id"])) for row in rows]

    def reveal_out_of_sample(
        self, report_id: str, *, actor: str, reason: str,
    ) -> dict[str, Any]:
        report = self.get_report(report_id)
        if report.get("status") != "ready":
            raise ValueError("factor report not found")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO factor_oos_reveals (
                       report_id, task_id, actor, reason, context_hash, revealed_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    report_id, report["task_id"], actor, reason,
                    report["context_hash"], now,
                ),
            )
        return self.get_out_of_sample_reveal(report_id)

    def get_out_of_sample_reveal(self, report_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM factor_oos_reveals WHERE report_id=?", (report_id,)
            ).fetchone()
        return (
            {"status": "revealed", **dict(row)}
            if row is not None
            else {"status": "sealed", "report_id": report_id}
        )

    def publish_artifact(self, task_id: str) -> dict[str, Any]:
        """Two-pass, resumable publication without materializing all values."""

        task = self.get_task(task_id)
        if task.get("status") == "not_found":
            raise KeyError(f"factor task not found: {task_id}")
        with self._connect() as connection:
            summary = connection.execute(
                """SELECT COUNT(*) AS row_count, MIN(trade_date) AS start_date,
                          MAX(trade_date) AS end_date
                   FROM factor_research_observations
                   WHERE task_id=? AND processed_value IS NOT NULL""",
                (task_id,),
            ).fetchone()
        row_count = int(summary["row_count"] if summary is not None else 0)
        if not row_count:
            raise ValueError("factor artifact requires at least one processed value")
        config = dict(task.get("config") or {})
        pool_snapshot = next(
            (dict(item) for item in task.get("snapshots") or []
             if item.get("snapshot_type") == "pool"), {}
        )
        identity = {
            "factor_id": str(config.get("factor_id") or ""),
            "factor_version": str(config.get("factor_version") or ""),
            "source_task_id": task_id,
            "context_hash": str(task.get("context_hash") or ""),
            "data_version_id": str(task.get("data_version_id") or ""),
            "quality_report_id": str(task.get("quality_report_id") or ""),
            "adjustment": str(config.get("factor_adjustment") or "raw"),
            "pool_snapshot_hash": str(pool_snapshot.get("content_hash") or ""),
            "start_date": str(summary["start_date"]),
            "end_date": str(summary["end_date"]),
            "row_count": row_count,
        }
        content_hash = self._stream_artifact_content_hash(task_id, identity)
        artifact_id = f"factor-artifact-{content_hash[:20]}"
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM factor_artifacts WHERE source_task_id=?", (task_id,)
            ).fetchone()
            if existing is not None:
                if str(existing["content_hash"]) != content_hash:
                    raise ValueError("factor artifacts are immutable")
                artifact_id = str(existing["artifact_id"])
            else:
                connection.execute(
                    """INSERT INTO factor_artifacts (
                           artifact_id, factor_id, factor_version, source_task_id,
                           context_hash, data_version_id, quality_report_id, adjustment,
                           pool_snapshot_hash, start_date, end_date, status, row_count,
                           content_hash, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'publishing', ?, ?, ?)""",
                    (
                        artifact_id, identity["factor_id"], identity["factor_version"],
                        task_id, identity["context_hash"], identity["data_version_id"],
                        identity["quality_report_id"], identity["adjustment"],
                        identity["pool_snapshot_hash"], identity["start_date"],
                        identity["end_date"], identity["row_count"], content_hash, now,
                    ),
                )
        with self._connect() as source:
            cursor = source.execute(
                """SELECT trade_date, symbol, processed_value, aligned_value
                   FROM factor_research_observations
                   WHERE task_id=? AND processed_value IS NOT NULL
                   ORDER BY trade_date, symbol""", (task_id,),
            )
            while True:
                batch = cursor.fetchmany(10_000)
                if not batch:
                    break
                with self._connect() as target:
                    target.executemany(
                        """INSERT OR IGNORE INTO factor_artifact_values (
                               artifact_id, trade_date, symbol, value, aligned_value
                           ) VALUES (?, ?, ?, ?, ?)""",
                        ((artifact_id, row["trade_date"], row["symbol"],
                          row["processed_value"], row["aligned_value"]) for row in batch),
                    )
        with self._connect() as connection:
            inserted = connection.execute(
                "SELECT COUNT(*) AS count FROM factor_artifact_values WHERE artifact_id=?",
                (artifact_id,),
            ).fetchone()
            if int(inserted["count"] if inserted is not None else 0) != row_count:
                raise ValueError("factor artifact publication row count mismatch")
            connection.execute(
                "UPDATE factor_artifacts SET status='research_ready' WHERE artifact_id=?",
                (artifact_id,),
            )
        return self.get_artifact(artifact_id)

    def get_artifact_for_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT artifact_id FROM factor_artifacts WHERE source_task_id=?", (task_id,)
            ).fetchone()
        return (
            self.get_artifact(str(row["artifact_id"]))
            if row is not None
            else {"status": "not_found", "source_task_id": task_id}
        )

    def _stream_artifact_content_hash(
        self, task_id: str, identity: Mapping[str, Any],
    ) -> str:
        digest = hashlib.sha256()
        digest.update(b'{"identity":')
        digest.update(_dump(identity).encode("utf-8"))
        digest.update(b',"values":[')
        first = True
        with self._connect() as connection:
            cursor = connection.execute(
                """SELECT trade_date, symbol, processed_value, aligned_value
                   FROM factor_research_observations
                   WHERE task_id=? AND processed_value IS NOT NULL
                   ORDER BY trade_date, symbol""", (task_id,),
            )
            while True:
                rows = cursor.fetchmany(10_000)
                if not rows:
                    break
                for row in rows:
                    if not first:
                        digest.update(b",")
                    first = False
                    digest.update(_dump({
                        "trade_date": str(row["trade_date"]),
                        "symbol": str(row["symbol"]),
                        "value": row["processed_value"],
                        "aligned_value": row["aligned_value"],
                    }).encode("utf-8"))
        digest.update(b"]}")
        return digest.hexdigest()

    def clear_streaming_observations(self, task_id: str) -> None:
        """Reset only the retryable staging rows owned by one research task."""

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM factor_research_observations WHERE task_id=?", (task_id,)
            )
            connection.execute(
                "DELETE FROM factor_research_daily_universe WHERE task_id=?", (task_id,)
            )
            connection.execute(
                "DELETE FROM factor_research_daily_universe_batches WHERE task_id=?", (task_id,)
            )

    def append_observations(
        self, task_id: str, observations: Iterable[Mapping[str, Any]],
    ) -> int:
        """Idempotently append one bounded calculation batch."""

        rows = (
            (
                task_id,
                str(row["trade_date"]),
                str(row["symbol"]),
                row.get("raw_value"),
                row.get("processed_value"),
                row.get("aligned_value"),
                _dump(row.get("forward_returns") or {}),
                str(row.get("industry") or "") or None,
                row.get("group_no"),
                _dump(row.get("evidence") or {}),
            )
            for row in observations
        )
        with self._connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR REPLACE INTO factor_research_observations (
                    task_id, trade_date, symbol, raw_value, processed_value,
                    aligned_value, forward_returns_json, industry, group_no,
                    evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return connection.total_changes - before

    def add_universe_counts(
        self, task_id: str, counts: Mapping[str, int], *, batch_offset: int = 0,
    ) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO factor_research_daily_universe_batches (
                    task_id, batch_offset, trade_date, universe_count
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (task_id, int(batch_offset), str(trade_date), int(count))
                    for trade_date, count in counts.items()
                ),
            )

    def fetch_universe_counts(self, task_id: str) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT trade_date, SUM(universe_count) AS universe_count
                   FROM factor_research_daily_universe_batches
                   WHERE task_id=? GROUP BY trade_date ORDER BY trade_date""",
                (task_id,),
            ).fetchall()
        return {str(row["trade_date"]): int(row["universe_count"]) for row in rows}

    def observation_count(self, task_id: str, *, processed_only: bool = False) -> int:
        suffix = " AND processed_value IS NOT NULL" if processed_only else ""
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS count FROM factor_research_observations WHERE task_id=?{suffix}",
                (task_id,),
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def observation_dates(self, task_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT trade_date FROM factor_research_observations
                   WHERE task_id=? ORDER BY trade_date""",
                (task_id,),
            ).fetchall()
        return [str(row["trade_date"]) for row in rows]

    def fetch_observations_for_date(
        self, task_id: str, trade_date: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM factor_research_observations
                   WHERE task_id=? AND trade_date=? ORDER BY symbol""",
                (task_id, trade_date),
            ).fetchall()
        return [_observation_dict(row) for row in rows]

    def update_processed_observations(
        self, task_id: str, rows: Iterable[Mapping[str, Any]],
    ) -> None:
        with self._connect() as connection:
            connection.executemany(
                """UPDATE factor_research_observations
                   SET processed_value=?, aligned_value=?, evidence_json=?
                   WHERE task_id=? AND trade_date=? AND symbol=?""",
                (
                    (
                        row.get("processed_value"), row.get("aligned_value"),
                        _dump(row.get("evidence") or {}), task_id,
                        str(row["trade_date"]), str(row["symbol"]),
                    )
                    for row in rows
                ),
            )

    def update_group_numbers(
        self, task_id: str, rows: Iterable[Mapping[str, Any]],
    ) -> None:
        with self._connect() as connection:
            connection.executemany(
                """UPDATE factor_research_observations SET group_no=?
                   WHERE task_id=? AND trade_date=? AND symbol=?""",
                (
                    (
                        row.get("group_no"), task_id,
                        str(row["trade_date"]), str(row["symbol"]),
                    )
                    for row in rows if row.get("group_no") is not None
                ),
            )

    def processed_distribution(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS count, AVG(processed_value) AS mean,
                          AVG(processed_value * processed_value) AS mean_square,
                          MIN(processed_value) AS min_value,
                          MAX(processed_value) AS max_value
                   FROM factor_research_observations
                   WHERE task_id=? AND processed_value IS NOT NULL""",
                (task_id,),
            ).fetchone()
            count = int(row["count"] if row is not None else 0)
            if not count:
                return {"status": "unavailable", "reason": "no_finite_values", "count": 0}
            fractions = {
                "p01": 0.01, "p05": 0.05, "p25": 0.25, "median": 0.5,
                "p75": 0.75, "p95": 0.95, "p99": 0.99,
            }
            positions = {
                key: min(1.0, max(0.0, fraction)) * (count - 1)
                for key, fraction in fractions.items()
            }
            offsets = sorted({
                index for position in positions.values()
                for index in (math.floor(position), math.ceil(position))
            })
            placeholders = ",".join("?" for _ in offsets)
            selected = connection.execute(
                f"""WITH ranked AS (
                        SELECT processed_value,
                               ROW_NUMBER() OVER (ORDER BY processed_value) - 1 AS offset_no
                        FROM factor_research_observations
                        WHERE task_id=? AND processed_value IS NOT NULL
                    )
                    SELECT offset_no, processed_value FROM ranked
                    WHERE offset_no IN ({placeholders})""",
                (task_id, *offsets),
            ).fetchall()
            selected_values = {
                int(item["offset_no"]): float(item["processed_value"])
                for item in selected
            }
            quantiles = {}
            for key, position in positions.items():
                lower = math.floor(position)
                upper = math.ceil(position)
                weight = position - lower
                quantiles[key] = (
                    selected_values[lower] * (1.0 - weight)
                    + selected_values[upper] * weight
                )
        mean = float(row["mean"])
        variance = max(0.0, float(row["mean_square"]) - mean * mean)
        return {
            "status": "ready", "count": count, "mean": mean,
            "std": math.sqrt(variance), "min": float(row["min_value"]),
            **quantiles, "max": float(row["max_value"]),
        }

    def industry_observations(
        self, task_id: str, industry: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT aligned_value, forward_returns_json
                   FROM factor_research_observations
                   WHERE task_id=? AND industry=? AND processed_value IS NOT NULL
                   ORDER BY trade_date, symbol""",
                (task_id, industry),
            ).fetchall()
        return [
            {"aligned_value": row["aligned_value"], "forward_returns": _load(row["forward_returns_json"])}
            for row in rows
        ]

    def observation_industries(self, task_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT industry FROM factor_research_observations
                   WHERE task_id=? AND industry IS NOT NULL AND industry<>''
                   ORDER BY industry""",
                (task_id,),
            ).fetchall()
        return [str(row["industry"]) for row in rows]

    def storage_headroom(
        self, *, reserve_bytes: int = 0, estimated_additional_bytes: int = 0,
    ) -> dict[str, Any]:
        usage = shutil.disk_usage(self.database_path.parent.resolve())
        free_after_estimate = int(usage.free) - max(0, int(estimated_additional_bytes))
        return {
            "status": "ready" if free_after_estimate >= int(reserve_bytes) else "blocked",
            "database_path": str(self.database_path.resolve()),
            "free_bytes": int(usage.free),
            "estimated_additional_bytes": max(0, int(estimated_additional_bytes)),
            "free_after_estimate_bytes": free_after_estimate,
            "reserve_bytes": max(0, int(reserve_bytes)),
        }

    def checkpoint_wal(self, *, truncate: bool = False) -> dict[str, int]:
        mode = "TRUNCATE" if truncate else "PASSIVE"
        with self._connect() as connection:
            row = connection.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        return {
            "busy": int(row[0]), "log_frames": int(row[1]),
            "checkpointed_frames": int(row[2]),
        }

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM factor_artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
        if row is None:
            return {"artifact_id": artifact_id, "status": "not_found"}
        artifact = dict(row)
        artifact["governance"] = self.get_artifact_governance(artifact_id, include_events=False)
        return artifact

    def get_artifact_governance(
        self, artifact_id: str, *, include_events: bool = True,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM factor_artifact_governance WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            events = (
                connection.execute(
                    """SELECT event_id, event_type, payload_json, created_at
                       FROM factor_artifact_governance_events WHERE artifact_id=?
                       ORDER BY created_at DESC, event_id DESC""",
                    (artifact_id,),
                ).fetchall()
                if include_events else []
            )
        result = (
            dict(row)
            if row is not None
            else {
                "artifact_id": artifact_id,
                "review_status": "pending",
                "registration_status": "unregistered",
                "policy_id": "",
                "reviewer": "",
                "decision_note": "",
                "reviewed_at": None,
                "registered_at": None,
                "updated_at": None,
            }
        )
        if include_events:
            result["events"] = [
                {
                    "event_id": item["event_id"],
                    "event_type": item["event_type"],
                    "payload": _load(item["payload_json"]),
                    "created_at": item["created_at"],
                }
                for item in events
            ]
        return result

    def review_artifact(
        self, artifact_id: str, *, decision: str, policy_id: str,
        reviewer: str, note: str,
    ) -> dict[str, Any]:
        artifact = self.get_artifact(artifact_id)
        if artifact.get("status") == "not_found":
            raise ValueError("factor artifact not found")
        if decision not in {"approved", "rejected"}:
            raise ValueError("review decision must be approved or rejected")
        now = _utc_now()
        payload = {
            "decision": decision, "policy_id": policy_id,
            "reviewer": reviewer, "note": note,
            "artifact_content_hash": artifact.get("content_hash"),
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO factor_artifact_governance (
                       artifact_id, artifact_content_hash, review_status,
                       registration_status, policy_id, reviewer, decision_note,
                       reviewed_at, registered_at, updated_at
                   ) VALUES (?, ?, ?, 'unregistered', ?, ?, ?, ?, NULL, ?)
                   ON CONFLICT(artifact_id) DO UPDATE SET
                       artifact_content_hash=excluded.artifact_content_hash,
                       review_status=excluded.review_status,
                       registration_status='unregistered',
                       policy_id=excluded.policy_id,
                       reviewer=excluded.reviewer,
                       decision_note=excluded.decision_note,
                       reviewed_at=excluded.reviewed_at,
                       registered_at=NULL,
                       updated_at=excluded.updated_at""",
                (
                    artifact_id, artifact["content_hash"], decision, policy_id,
                    reviewer, note, now, now,
                ),
            )
            self._insert_governance_event(connection, artifact_id, "reviewed", payload, now)
            connection.execute(
                "UPDATE factor_artifacts SET status='research_ready' WHERE artifact_id=?",
                (artifact_id,),
            )
        return self.get_artifact_governance(artifact_id)

    def register_artifact(self, artifact_id: str) -> dict[str, Any]:
        artifact = self.get_artifact(artifact_id)
        governance = self.get_artifact_governance(artifact_id, include_events=False)
        if governance.get("review_status") != "approved":
            raise ValueError("factor artifact must be approved before registration")
        if governance.get("artifact_content_hash") != artifact.get("content_hash"):
            raise ValueError("factor artifact content hash changed after review")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE factor_artifact_governance
                   SET registration_status='registered', registered_at=?, updated_at=?
                   WHERE artifact_id=?""",
                (now, now, artifact_id),
            )
            connection.execute(
                "UPDATE factor_artifacts SET status='ready' WHERE artifact_id=?",
                (artifact_id,),
            )
            self._insert_governance_event(
                connection, artifact_id, "registered",
                {"artifact_content_hash": artifact.get("content_hash")}, now,
            )
        return self.get_artifact_governance(artifact_id)

    def suspend_artifact(self, artifact_id: str, *, note: str) -> dict[str, Any]:
        governance = self.get_artifact_governance(artifact_id, include_events=False)
        if governance.get("registration_status") != "registered":
            raise ValueError("only registered factor artifacts can be suspended")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE factor_artifact_governance
                   SET registration_status='suspended', decision_note=?, updated_at=?
                   WHERE artifact_id=?""",
                (note, now, artifact_id),
            )
            connection.execute(
                "UPDATE factor_artifacts SET status='research_ready' WHERE artifact_id=?",
                (artifact_id,),
            )
            self._insert_governance_event(
                connection, artifact_id, "suspended", {"note": note}, now,
            )
        return self.get_artifact_governance(artifact_id)

    def require_artifact_registration(self, artifact_id: str) -> dict[str, Any]:
        governance = self.get_artifact_governance(artifact_id, include_events=False)
        if (
            governance.get("review_status") != "approved"
            or governance.get("registration_status") != "registered"
        ):
            raise ValueError("factor artifact is not approved and registered")
        artifact = self.get_artifact(artifact_id)
        if governance.get("artifact_content_hash") != artifact.get("content_hash"):
            raise ValueError("registered factor artifact content hash mismatch")
        return governance

    def save_monitoring_snapshot(
        self, artifact_id: str, *, status: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        from factor_lab.research_core import canonical_hash

        payload_hash = canonical_hash(payload)
        snapshot_id = f"factor-monitor-{payload_hash[:20]}"
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO factor_artifact_monitoring_snapshots (
                       snapshot_id, artifact_id, status, payload_json,
                       payload_hash, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (snapshot_id, artifact_id, status, _dump(payload), payload_hash, now),
            )
        return {
            "snapshot_id": snapshot_id,
            "artifact_id": artifact_id,
            "status": status,
            "payload": dict(payload),
            "payload_hash": payload_hash,
            "created_at": now,
        }

    def list_monitoring_snapshots(
        self, artifact_id: str, *, limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM factor_artifact_monitoring_snapshots
                   WHERE artifact_id=? ORDER BY created_at DESC, snapshot_id DESC LIMIT ?""",
                (artifact_id, max(1, min(int(limit), 100))),
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": _load(row["payload_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _insert_governance_event(
        connection: sqlite3.Connection, artifact_id: str, event_type: str,
        payload: Mapping[str, Any], created_at: str,
    ) -> None:
        event_seed = f"{artifact_id}|{event_type}|{created_at}|{_dump(payload)}"
        event_id = f"factor-governance-{hashlib.sha256(event_seed.encode('utf-8')).hexdigest()[:20]}"
        connection.execute(
            """INSERT OR IGNORE INTO factor_artifact_governance_events (
                   event_id, artifact_id, event_type, payload_json, created_at
               ) VALUES (?, ?, ?, ?, ?)""",
            (event_id, artifact_id, event_type, _dump(payload), created_at),
        )

    def list_artifacts(self, *, factor_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        where = "WHERE factor_id=?" if factor_id else ""
        values: list[Any] = [factor_id] if factor_id else []
        values.append(max(1, min(int(limit), 500)))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM factor_artifacts {where} ORDER BY created_at DESC LIMIT ?",
                values,
            ).fetchall()
        return [self.get_artifact(str(row["artifact_id"])) for row in rows]

    def resolve_artifact(self, factor_id: str, artifact_id: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            if artifact_id:
                row = connection.execute(
                    """SELECT * FROM factor_artifacts
                       WHERE artifact_id=? AND factor_id=? AND status='ready'""",
                    (artifact_id, factor_id),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT * FROM factor_artifacts
                       WHERE factor_id=? AND status='ready'
                       ORDER BY created_at DESC LIMIT 1""",
                    (factor_id,),
                ).fetchone()
        if row is None:
            return {
                "status": "unavailable", "reason": "factor_artifact_not_found",
                "factor_id": factor_id, "artifact_id": artifact_id,
            }
        return dict(row)

    def fetch_artifact_values(
        self,
        artifact_id: str,
        *,
        symbol: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> list[dict[str, Any]]:
        conditions = ["artifact_id=?"]
        values: list[Any] = [artifact_id]
        if symbol:
            conditions.append("symbol=?")
            values.append(_symbol(symbol))
        if start_date:
            conditions.append("trade_date>=?")
            values.append(start_date)
        if end_date:
            conditions.append("trade_date<=?")
            values.append(end_date)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT artifact_id, trade_date, symbol, value, aligned_value
                    FROM factor_artifact_values WHERE {' AND '.join(conditions)}
                    ORDER BY trade_date, symbol""",
                values,
            ).fetchall()
        return [dict(row) for row in rows]
    def create_optimization_task(
        self,
        *,
        task_id: str,
        artifact: Mapping[str, Any],
        value_field: str,
        config: Mapping[str, Any],
        context: Mapping[str, Any],
        context_hash: str,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO factor_optimization_tasks (
                    task_id, status, artifact_id, artifact_content_hash,
                    source_task_id, value_field, config_json, context_json,
                    context_hash, progress_json, error_json, report_id,
                    created_at, updated_at, started_at, finished_at
                ) VALUES (?, 'ready', ?, ?, ?, ?, ?, ?, ?, ?, '{}', NULL, ?, ?, NULL, NULL)
                """,
                (
                    task_id,
                    str(artifact["artifact_id"]),
                    str(artifact["content_hash"]),
                    str(artifact["source_task_id"]),
                    value_field,
                    _dump(config),
                    _dump(context),
                    context_hash,
                    _dump({"phase": "ready", "percent": 0.0}),
                    now,
                    now,
                ),
            )
        return self.get_optimization_task(task_id)

    def update_optimization_task(self, task_id: str, **values: Any) -> None:
        allowed = {
            "status", "progress_json", "error_json", "report_id",
            "started_at", "finished_at",
        }
        selected = {key: value for key, value in values.items() if key in allowed}
        if not selected:
            return
        selected["updated_at"] = _utc_now()
        columns = ", ".join(f"{key}=?" for key in selected)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE factor_optimization_tasks SET {columns} WHERE task_id=?",
                (*selected.values(), task_id),
            )

    def get_optimization_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM factor_optimization_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            return {"task_id": task_id, "status": "not_found"}
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "artifact_id": row["artifact_id"],
            "artifact_content_hash": row["artifact_content_hash"],
            "source_task_id": row["source_task_id"],
            "value_field": row["value_field"],
            "config": _load(row["config_json"]),
            "context": _load(row["context_json"]),
            "context_hash": row["context_hash"],
            "progress": _load(row["progress_json"]),
            "error": _load(row["error_json"]),
            "report_id": row["report_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def list_optimization_tasks(
        self, *, status: str = "", limit: int = 50
    ) -> list[dict[str, Any]]:
        values: list[Any] = []
        where = ""
        if status:
            where = "WHERE status=?"
            values.append(status)
        values.append(max(1, min(int(limit), 200)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT task_id FROM factor_optimization_tasks {where}
                    ORDER BY created_at DESC LIMIT ?""",
                values,
            ).fetchall()
        return [self.get_optimization_task(str(row["task_id"])) for row in rows]

    def save_optimization_report(
        self,
        *,
        report_id: str,
        task_id: str,
        artifact_id: str,
        context_hash: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        from factor_lab.research_core import canonical_hash

        payload_hash = canonical_hash(payload)
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM factor_optimization_reports WHERE report_id=?",
                (report_id,),
            ).fetchone()
            if existing is not None and str(existing["payload_hash"]) != payload_hash:
                raise ValueError("factor optimization reports are immutable")
            connection.execute(
                """
                INSERT OR IGNORE INTO factor_optimization_reports (
                    report_id, task_id, artifact_id, context_hash,
                    payload_json, payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id, task_id, artifact_id, context_hash,
                    _dump(payload), payload_hash, now,
                ),
            )
        return self.get_optimization_report(report_id)

    def get_optimization_report(self, report_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM factor_optimization_reports WHERE report_id=?",
                (report_id,),
            ).fetchone()
        if row is None:
            return {"report_id": report_id, "status": "not_found"}
        return {
            "report_id": row["report_id"],
            "task_id": row["task_id"],
            "artifact_id": row["artifact_id"],
            "status": "ready",
            "context_hash": row["context_hash"],
            "payload": _load(row["payload_json"]),
            "payload_hash": row["payload_hash"],
            "created_at": row["created_at"],
        }

    def upsert_index_components(self, rows: Iterable[Mapping[str, Any]]) -> int:
        raise RuntimeError(
            "index components are owned by the data center; use its controlled import"
        )

    def resolve_index_components(self, index_code: str, as_of: str) -> dict[str, Any]:
        if self._index_store is None:
            return {
                "status": "unavailable",
                "reason": "index_component_authority_not_configured",
                "index_code": str(index_code or "").strip().upper(),
                "as_of_date": str(as_of or "")[:10],
                "symbols": [],
            }
        return dict(self._index_store.resolve_index_components(index_code, as_of))

    def resolve_index_component_window(
        self, index_code: str, start_date: str, end_date: str
    ) -> dict[str, Any]:
        if self._index_store is None:
            return {
                "status": "unavailable",
                "reason": "index_component_authority_not_configured",
                "index_code": str(index_code or "").strip().upper(),
                "start_date": str(start_date or "")[:10],
                "end_date": str(end_date or "")[:10],
                "symbols": [],
                "intervals": [],
            }
        return dict(
            self._index_store.resolve_index_component_window(
                index_code, start_date, end_date
            )
        )

    def index_component_coverage(self) -> dict[str, Any]:
        if self._index_store is None:
            return {
                "status": "unavailable",
                "reason": "index_component_authority_not_configured",
                "items": [],
            }
        return dict(self._index_store.index_component_coverage())
    def recover_interrupted_tasks(self) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE factor_research_tasks
                SET status='interrupted', updated_at=?, finished_at=?
                WHERE status IN ('running', 'stop_requested')
                """,
                (now, now),
            )

            connection.execute(
                """
                UPDATE factor_optimization_tasks
                SET status='interrupted', updated_at=?, finished_at=?
                WHERE status='running'
                """,
                (now, now),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection


def _symbol(value: Any) -> str:
    raw = str(value or "").strip().upper()
    code = raw.split(".", 1)[0]
    return code.zfill(6) if code.isdigit() else raw


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _observation_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "trade_date": row["trade_date"],
        "symbol": row["symbol"],
        "raw_value": row["raw_value"],
        "processed_value": row["processed_value"],
        "aligned_value": row["aligned_value"],
        "forward_returns": _load(row["forward_returns_json"]),
        "industry": row["industry"],
        "group_no": row["group_no"],
        "evidence": _load(row["evidence_json"]),
    }


def _version_number(value: Any) -> int:
    text = str(value or "v0").lower().removeprefix("v")
    return int(text) if text.isdigit() else 0

def _load(value: Any) -> dict[str, Any]:
    payload = json.loads(str(value or "{}"))
    return payload if isinstance(payload, dict) else {}
