"""Point-in-time security classification history storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


class ClassificationHistoryStore:
    """Resolve industry/concept labels as of a historical date."""

    def __init__(self, database_path: str | Path = "var/runtime/a_share_classification_history.sqlite3") -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS classification_intervals (
                    symbol TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    category TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    source TEXT NOT NULL,
                    source_version TEXT,
                    evidence_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, dimension, category, valid_from, source)
                );
                CREATE INDEX IF NOT EXISTS idx_classification_asof
                    ON classification_intervals (symbol, dimension, valid_from, valid_to);                CREATE TABLE IF NOT EXISTS classification_sync_state (
                    job_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    interval_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, symbol)
                );
                CREATE INDEX IF NOT EXISTS idx_classification_sync_job_status
                    ON classification_sync_state (job_id, status, symbol);
                """
            )

    def upsert_intervals(self, rows: Iterable[dict[str, Any]]) -> int:
        normalized = []
        for row in rows:
            symbol = _symbol(row.get("symbol"))
            dimension = str(row.get("dimension") or "").strip().lower()
            category = str(row.get("category") or "").strip()
            valid_from = str(row.get("valid_from") or "").strip()[:10]
            if not symbol or dimension not in {"industry", "concept"} or not category or not valid_from:
                continue
            normalized.append((
                symbol,
                dimension,
                category,
                valid_from,
                str(row.get("valid_to") or "").strip()[:10] or None,
                str(row.get("source") or "manual_point_in_time_import"),
                str(row.get("source_version") or "") or None,
                json.dumps(dict(row.get("evidence") or {}), ensure_ascii=False, sort_keys=True),
                str(row.get("observed_at") or ""),
            ))
        with self._connect() as connection:
            connection.executemany(
                """INSERT INTO classification_intervals (
                    symbol, dimension, category, valid_from, valid_to, source,
                    source_version, evidence_json, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, dimension, category, valid_from, source) DO UPDATE SET
                    valid_to=excluded.valid_to,
                    source_version=excluded.source_version,
                    evidence_json=excluded.evidence_json,
                    observed_at=excluded.observed_at
                """,
                normalized,
            )
        return len(normalized)

    def resolve(self, symbol: str, dimension: str, as_of: str) -> list[dict[str, Any]]:
        code = _symbol(symbol)
        target_date = str(as_of or "")[:10]
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM classification_intervals
                   WHERE symbol=? AND dimension=? AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?)
                   ORDER BY valid_from DESC, category""",
                (code, str(dimension).lower(), target_date, target_date),
            ).fetchall()
        if not rows:
            return []
        latest = str(rows[0]["valid_from"])
        return [
            {
                "symbol": row["symbol"],
                "dimension": row["dimension"],
                "category": row["category"],
                "valid_from": row["valid_from"],
                "valid_to": row["valid_to"],
                "source": row["source"],
                "source_version": row["source_version"],
                "evidence": json.loads(row["evidence_json"] or "{}"),
            }
            for row in rows
            if str(row["valid_from"]) == latest
        ]

    def coverage(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT dimension, COUNT(*) AS interval_count,
                          COUNT(DISTINCT symbol) AS symbol_count,
                          MIN(valid_from) AS earliest, MAX(valid_from) AS latest
                   FROM classification_intervals GROUP BY dimension"""
            ).fetchall()
        dimensions = {str(row["dimension"]): dict(row) for row in rows}
        return {"status": "ready", "dimensions": dimensions}

    def prepare_sync_job(self, job_id: str, symbols: Iterable[str], *, observed_at: str) -> int:
        normalized = sorted({_symbol(value) for value in symbols if _symbol(value)})
        with self._connect() as connection:
            connection.executemany(
                """INSERT INTO classification_sync_state (
                    job_id, symbol, status, attempt_count, interval_count,
                    error_message, updated_at
                ) VALUES (?, ?, 'pending', 0, 0, NULL, ?)
                ON CONFLICT(job_id, symbol) DO NOTHING""",
                [(job_id, symbol, observed_at) for symbol in normalized],
            )
        return len(normalized)

    def list_sync_symbols(self, job_id: str, *, statuses: Iterable[str] = ("pending", "failed")) -> list[str]:
        values = tuple(str(status) for status in statuses)
        placeholders = ",".join("?" for _ in values)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT symbol FROM classification_sync_state WHERE job_id=? AND status IN ({placeholders}) ORDER BY symbol",
                (job_id, *values),
            ).fetchall()
        return [str(row["symbol"]) for row in rows]

    def mark_sync_state(self, job_id: str, symbol: str, *, status: str, attempt_count: int, interval_count: int = 0, error_message: str | None = None, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE classification_sync_state SET status=?, attempt_count=?,
                   interval_count=?, error_message=?, updated_at=?
                   WHERE job_id=? AND symbol=?""",
                (status, int(attempt_count), int(interval_count), error_message, updated_at, job_id, _symbol(symbol)),
            )

    def sync_job_summary(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT status, COUNT(*) AS count, SUM(interval_count) AS intervals
                   FROM classification_sync_state WHERE job_id=? GROUP BY status""",
                (job_id,),
            ).fetchall()
        by_status = {str(row["status"]): {"count": int(row["count"] or 0), "intervals": int(row["intervals"] or 0)} for row in rows}
        return {"job_id": job_id, "by_status": by_status, "total": sum(item["count"] for item in by_status.values())}
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _symbol(value: Any) -> str:
    text = str(value or "").strip().split(".")[0]
    return text.zfill(6) if text else ""
