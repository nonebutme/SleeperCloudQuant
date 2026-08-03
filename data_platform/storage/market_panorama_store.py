"""Additive SQLite storage for M4 market-panorama datasets and sync jobs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


class MarketPanoramaStore:
    """Own board history, fund flows, events and resumable panorama jobs."""

    def __init__(self, database_path: str | Path = "var/runtime/market_panorama.sqlite3") -> None:
        self.database_path = Path(database_path)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS panorama_board_catalog (
                    dimension TEXT NOT NULL CHECK (dimension IN ('industry','concept')),
                    board_code TEXT NOT NULL,
                    board_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (dimension, board_code)
                );
                CREATE INDEX IF NOT EXISTS idx_panorama_board_name
                    ON panorama_board_catalog (dimension, board_name);

                CREATE TABLE IF NOT EXISTS panorama_board_daily (
                    dimension TEXT NOT NULL CHECK (dimension IN ('industry','concept')),
                    board_code TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL,
                    change_pct REAL, change_amount REAL,
                    volume REAL, amount REAL, amplitude REAL, turnover_rate REAL,
                    source TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    PRIMARY KEY (dimension, board_code, trade_date)
                );
                CREATE INDEX IF NOT EXISTS idx_panorama_board_daily_date
                    ON panorama_board_daily (dimension, trade_date);

                CREATE TABLE IF NOT EXISTS panorama_board_fund_flow (
                    dimension TEXT NOT NULL CHECK (dimension IN ('industry','concept')),
                    board_code TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    main_net_inflow REAL, main_net_ratio REAL,
                    super_large_net_inflow REAL, super_large_net_ratio REAL,
                    large_net_inflow REAL, large_net_ratio REAL,
                    medium_net_inflow REAL, medium_net_ratio REAL,
                    small_net_inflow REAL, small_net_ratio REAL,
                    source TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    PRIMARY KEY (dimension, board_code, trade_date)
                );
                CREATE INDEX IF NOT EXISTS idx_panorama_flow_date
                    ON panorama_board_fund_flow (dimension, trade_date);

                CREATE TABLE IF NOT EXISTS panorama_events (
                    event_id TEXT PRIMARY KEY,
                    event_date TEXT NOT NULL,
                    published_at TEXT,
                    symbol TEXT,
                    scope TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_panorama_events_date_symbol
                    ON panorama_events (event_date, symbol, event_type);

                CREATE TABLE IF NOT EXISTS panorama_sync_jobs (
                    job_id TEXT PRIMARY KEY,
                    datasets_json TEXT NOT NULL,
                    target_trade_date TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_items INTEGER NOT NULL DEFAULT 0,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    failed_items INTEGER NOT NULL DEFAULT 0,
                    quarantined_items INTEGER NOT NULL DEFAULT 0,
                    rows_written INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    stop_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS panorama_sync_job_ranges (
                    job_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    start_trade_date TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES panorama_sync_jobs (job_id)
                );
                CREATE TABLE IF NOT EXISTS panorama_sync_items (
                    job_id TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, dataset, item_key)
                );
                CREATE INDEX IF NOT EXISTS idx_panorama_sync_item_status
                    ON panorama_sync_items (job_id, status, dataset);
                """
            )

    def upsert_board_catalog(self, dimension: str, rows: Iterable[Mapping[str, Any]]) -> int:
        now = _utc_now()
        values = []
        for row in rows:
            code = str(row.get("board_code") or "").strip()
            name = str(row.get("board_name") or "").strip()
            if code and name:
                values.append((dimension, code, name, str(row.get("source") or "akshare"), now))
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO panorama_board_catalog
                    (dimension, board_code, board_name, source, observed_at, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT(dimension, board_code) DO UPDATE SET
                      board_name=excluded.board_name, source=excluded.source,
                      observed_at=excluded.observed_at, is_active=1""",
                values,
            )
        return len(values)

    def list_board_catalog(self, dimension: str) -> list[dict[str, Any]]:
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                "SELECT * FROM panorama_board_catalog WHERE dimension=? AND is_active=1 ORDER BY board_name",
                (dimension,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_board_daily(self, dimension: str, board_code: str, rows: Iterable[Mapping[str, Any]]) -> int:
        now = _utc_now()
        values = []
        for row in rows:
            trade_date = str(row.get("trade_date") or "")[:10]
            if not trade_date:
                continue
            values.append((dimension, board_code, trade_date, *[_number(row.get(key)) for key in (
                "open", "high", "low", "close", "change_pct", "change_amount",
                "volume", "amount", "amplitude", "turnover_rate",
            )], str(row.get("source") or "akshare"), now))
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO panorama_board_daily (
                    dimension, board_code, trade_date, open, high, low, close,
                    change_pct, change_amount, volume, amount, amplitude, turnover_rate,
                    source, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dimension, board_code, trade_date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                    change_pct=excluded.change_pct, change_amount=excluded.change_amount,
                    volume=excluded.volume, amount=excluded.amount, amplitude=excluded.amplitude,
                    turnover_rate=excluded.turnover_rate, source=excluded.source,
                    imported_at=excluded.imported_at""",
                values,
            )
        return len(values)

    def upsert_fund_flows(self, dimension: str, board_code: str, rows: Iterable[Mapping[str, Any]]) -> int:
        now = _utc_now()
        values = []
        for row in rows:
            trade_date = str(row.get("trade_date") or "")[:10]
            if not trade_date:
                continue
            values.append((dimension, board_code, trade_date, *[_number(row.get(key)) for key in (
                "main_net_inflow", "main_net_ratio", "super_large_net_inflow", "super_large_net_ratio",
                "large_net_inflow", "large_net_ratio", "medium_net_inflow", "medium_net_ratio",
                "small_net_inflow", "small_net_ratio",
            )], str(row.get("source") or "akshare"), now))
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO panorama_board_fund_flow (
                    dimension, board_code, trade_date, main_net_inflow, main_net_ratio,
                    super_large_net_inflow, super_large_net_ratio, large_net_inflow, large_net_ratio,
                    medium_net_inflow, medium_net_ratio, small_net_inflow, small_net_ratio,
                    source, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dimension, board_code, trade_date) DO UPDATE SET
                    main_net_inflow=excluded.main_net_inflow, main_net_ratio=excluded.main_net_ratio,
                    super_large_net_inflow=excluded.super_large_net_inflow,
                    super_large_net_ratio=excluded.super_large_net_ratio,
                    large_net_inflow=excluded.large_net_inflow, large_net_ratio=excluded.large_net_ratio,
                    medium_net_inflow=excluded.medium_net_inflow, medium_net_ratio=excluded.medium_net_ratio,
                    small_net_inflow=excluded.small_net_inflow, small_net_ratio=excluded.small_net_ratio,
                    source=excluded.source, imported_at=excluded.imported_at""",
                values,
            )
        return len(values)

    def upsert_events(self, rows: Iterable[Mapping[str, Any]]) -> int:
        values = []
        for row in rows:
            event_date = str(row.get("event_date") or "")[:10]
            title = str(row.get("title") or "").strip()
            if not event_date or not title:
                continue
            symbol = str(row.get("symbol") or "").split(".")[0]
            source = str(row.get("source") or "unknown")
            url = str(row.get("url") or "")
            identity = "|".join((event_date, symbol, str(row.get("event_type") or "news"), title, url, source))
            event_id = str(row.get("event_id") or "evt-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24])
            values.append((event_id, event_date, str(row.get("published_at") or "") or None,
                           symbol or None, str(row.get("scope") or ("symbol" if symbol else "market")),
                           str(row.get("event_type") or "news"), title, url or None, source,
                           str(row.get("observed_at") or _utc_now()),
                           json.dumps(dict(row.get("evidence") or {}), ensure_ascii=False, sort_keys=True)))
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO panorama_events (
                    event_id, event_date, published_at, symbol, scope, event_type,
                    title, url, source, observed_at, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    published_at=excluded.published_at, title=excluded.title, url=excluded.url,
                    observed_at=excluded.observed_at, evidence_json=excluded.evidence_json""",
                values,
            )
        return len(values)

    def board_snapshot(self, dimension: str, requested_date: str) -> dict[str, Any]:
        with closing(self._connect(read_only=True)) as connection:
            effective = connection.execute(
                "SELECT MAX(trade_date) FROM panorama_board_daily WHERE dimension=? AND trade_date<=?",
                (dimension, requested_date),
            ).fetchone()[0]
            if not effective:
                return {"status": "unavailable", "requested_trade_date": requested_date, "effective_trade_date": None, "items": []}
            rows = connection.execute(
                """SELECT d.*, c.board_name FROM panorama_board_daily d
                   JOIN panorama_board_catalog c
                     ON c.dimension=d.dimension AND c.board_code=d.board_code
                   WHERE d.dimension=? AND d.trade_date=?
                   ORDER BY d.change_pct DESC, c.board_name""",
                (dimension, effective),
            ).fetchall()
        return {"status": "ready" if effective == requested_date else "stale", "requested_trade_date": requested_date,
                "effective_trade_date": effective, "items": [dict(row) for row in rows], "source": "local_panorama_sqlite"}

    def flow_snapshot(self, dimension: str, requested_date: str) -> dict[str, Any]:
        with closing(self._connect(read_only=True)) as connection:
            effective = connection.execute(
                "SELECT MAX(trade_date) FROM panorama_board_fund_flow WHERE dimension=? AND trade_date<=?",
                (dimension, requested_date),
            ).fetchone()[0]
            if not effective:
                return {"status": "unavailable", "requested_trade_date": requested_date, "effective_trade_date": None, "items": []}
            rows = connection.execute(
                """SELECT f.*, c.board_name FROM panorama_board_fund_flow f
                   JOIN panorama_board_catalog c
                     ON c.dimension=f.dimension AND c.board_code=f.board_code
                   WHERE f.dimension=? AND f.trade_date=?
                   ORDER BY f.main_net_inflow DESC, c.board_name""",
                (dimension, effective),
            ).fetchall()
        return {"status": "ready" if effective == requested_date else "stale", "requested_trade_date": requested_date,
                "effective_trade_date": effective, "items": [dict(row) for row in rows], "source": "local_panorama_sqlite"}

    def list_events(self, requested_date: str, *, symbol: str = "", limit: int = 100) -> dict[str, Any]:
        code = str(symbol or "").split(".")[0]
        with closing(self._connect(read_only=True)) as connection:
            values: list[Any] = [requested_date]
            where = "event_date=?"
            if code:
                where += " AND (symbol=? OR symbol IS NULL)"
                values.append(code)
            values.append(max(1, min(int(limit), 500)))
            rows = connection.execute(
                f"SELECT * FROM panorama_events WHERE {where} ORDER BY published_at DESC, title LIMIT ?",
                values,
            ).fetchall()
        return {"status": "ready" if rows else "unavailable", "requested_trade_date": requested_date,
                "effective_trade_date": requested_date if rows else None,
                "items": [{**dict(row), "evidence": json.loads(row["evidence_json"] or "{}")} for row in rows]}

    def covered_dates(
        self, dataset: str, *, dimension: str = "", item_key: str = "",
        start_date: str, end_date: str,
    ) -> set[str]:
        with closing(self._connect(read_only=True)) as connection:
            if dataset in {"industry_board", "concept_board"}:
                rows = connection.execute(
                    """SELECT trade_date FROM panorama_board_daily
                       WHERE dimension=? AND board_code=? AND trade_date BETWEEN ? AND ?""",
                    (dimension, item_key, start_date, end_date),
                ).fetchall()
            elif dataset in {"industry_flow", "concept_flow"}:
                rows = connection.execute(
                    """SELECT trade_date FROM panorama_board_fund_flow
                       WHERE dimension=? AND board_code=? AND trade_date BETWEEN ? AND ?""",
                    (dimension, item_key, start_date, end_date),
                ).fetchall()
            elif dataset == "events":
                rows = connection.execute(
                    """SELECT DISTINCT event_date AS trade_date FROM panorama_events
                       WHERE symbol=? AND event_date BETWEEN ? AND ?""",
                    (item_key.split(".")[0], start_date, end_date),
                ).fetchall()
            else:
                return set()
        return {str(row["trade_date"]) for row in rows}
    def create_job(self, job_id: str, datasets: list[str], target_trade_date: str, symbols: list[str], *, mode: str = "incremental", start_trade_date: str = "") -> dict[str, Any]:
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO panorama_sync_jobs (
                    job_id, datasets_json, target_trade_date, symbols_json, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
                (job_id, json.dumps(datasets), target_trade_date, json.dumps(symbols), now, now),
            )
            connection.execute(
                "INSERT INTO panorama_sync_job_ranges (job_id, mode, start_trade_date) VALUES (?, ?, ?)",
                (job_id, mode, start_trade_date or target_trade_date),
            )
        return self.get_job(job_id)

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """SELECT jobs.*, COALESCE(ranges.mode, 'incremental') AS sync_mode,
                          COALESCE(ranges.start_trade_date, jobs.target_trade_date) AS start_trade_date
                   FROM panorama_sync_jobs jobs
                   LEFT JOIN panorama_sync_job_ranges ranges ON ranges.job_id=jobs.job_id
                   ORDER BY jobs.created_at DESC LIMIT ?""", (limit,)
            ).fetchall()
        return [self._job_payload(row) for row in rows]

    def get_job(self, job_id: str) -> dict[str, Any]:
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                """SELECT jobs.*, COALESCE(ranges.mode, 'incremental') AS sync_mode,
                          COALESCE(ranges.start_trade_date, jobs.target_trade_date) AS start_trade_date
                   FROM panorama_sync_jobs jobs
                   LEFT JOIN panorama_sync_job_ranges ranges ON ranges.job_id=jobs.job_id
                   WHERE jobs.job_id=?""", (job_id,),
            ).fetchone()
        return self._job_payload(row) if row else {"status": "not_found", "job_id": job_id}

    def start_job(self, job_id: str) -> None:
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE panorama_sync_jobs SET status='running', started_at=COALESCE(started_at, ?),
                   finished_at=NULL, stop_requested=0, last_error=NULL, updated_at=? WHERE job_id=?""",
                (now, now, job_id),
            )

    def set_job_total(self, job_id: str, total_items: int) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("UPDATE panorama_sync_jobs SET total_items=?, updated_at=? WHERE job_id=?",
                               (int(total_items), _utc_now(), job_id))

    def mark_item(self, job_id: str, dataset: str, item_key: str, *, status: str,
                  row_count: int = 0, error: str | None = None) -> None:
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO panorama_sync_items (job_id, dataset, item_key, status, row_count, error_message, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id, dataset, item_key) DO UPDATE SET status=excluded.status,
                     row_count=excluded.row_count, error_message=excluded.error_message, updated_at=excluded.updated_at""",
                (job_id, dataset, item_key, status, int(row_count), error, now),
            )
            summary = connection.execute(
                """SELECT COUNT(*) total,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
                   SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
                   SUM(row_count) rows_written FROM panorama_sync_items WHERE job_id=?""",
                (job_id,),
            ).fetchone()
            connection.execute(
                """UPDATE panorama_sync_jobs SET total_items=MAX(total_items, ?), completed_items=?,
                   failed_items=?, rows_written=?, updated_at=? WHERE job_id=?""",
                (int(summary["total"] or 0), int(summary["completed"] or 0), int(summary["failed"] or 0),
                 int(summary["rows_written"] or 0), now, job_id),
            )

    def finish_job(self, job_id: str, *, error: str | None = None) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.get("stop_requested"):
            status = "stopped"
        elif error:
            status = "failed"
        elif int(job.get("failed_items") or 0):
            status = "partial_failure"
        else:
            status = "published"
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE panorama_sync_jobs SET status=?, last_error=?, finished_at=?, updated_at=? WHERE job_id=?",
                (status, error or ("one or more panorama items failed" if status == "partial_failure" else None), now, now, job_id),
            )
        return self.get_job(job_id)

    def request_stop(self, job_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE panorama_sync_jobs SET stop_requested=1, status='stopping', updated_at=? WHERE job_id=?",
                (_utc_now(), job_id),
            )
        return self.get_job(job_id)

    def should_stop(self, job_id: str) -> bool:
        return bool(self.get_job(job_id).get("stop_requested"))

    def reset_job(self, job_id: str) -> dict[str, Any]:
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM panorama_sync_items WHERE job_id=?", (job_id,))
            connection.execute(
                """UPDATE panorama_sync_jobs SET status='queued', total_items=0, completed_items=0,
                   failed_items=0, quarantined_items=0, rows_written=0, last_error=NULL,
                   stop_requested=0, started_at=NULL, finished_at=NULL, updated_at=? WHERE job_id=?""",
                (now, job_id),
            )
        return self.get_job(job_id)

    def delete_job(self, job_id: str) -> dict[str, Any]:
        """Delete one inactive panorama task while preserving synchronized datasets."""

        job = self.get_job(job_id)
        if job.get("status") == "not_found":
            raise KeyError(f"sync task not found: {job_id}")
        if str(job.get("status") or "") in {"running", "validating", "stopping"}:
            raise ValueError("running, validating or stopping tasks cannot be deleted")
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM panorama_sync_items WHERE job_id=?", (job_id,))
            connection.execute("DELETE FROM panorama_sync_job_ranges WHERE job_id=?", (job_id,))
            deleted = connection.execute("DELETE FROM panorama_sync_jobs WHERE job_id=?", (job_id,)).rowcount
        if deleted != 1:
            raise KeyError(f"sync task not found: {job_id}")
        return {
            "job_id": job_id,
            "status": "deleted",
            "deleted_items": int(job.get("total_items") or 0),
            "market_data_deleted": False,
        }
    @staticmethod
    def _job_payload(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["datasets"] = json.loads(payload.pop("datasets_json") or "[]")
        payload["symbols"] = json.loads(payload.pop("symbols_json") or "[]")
        payload["stop_requested"] = bool(payload["stop_requested"])
        payload["mode"] = str(payload.pop("sync_mode", "incremental"))
        payload["symbol_scope"] = ",".join(payload["symbols"]) if payload["symbols"] else "all_current"
        payload["adjustments"] = payload["datasets"]
        return payload

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            connection = sqlite3.connect(f"file:{self.database_path.resolve().as_posix()}?mode=ro", uri=True, timeout=30)
        else:
            connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        if not read_only:
            connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _number(value: Any) -> float | None:
    if value is None or value == "" or str(value).strip() in {"-", "nan", "NaN"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")