"""SQLite-backed metadata store for phase-1 market-data caching."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class SqliteMetadataStore:
    """Persist cached market-data rows and sync metadata for the phase-1 data platform."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    @property
    def database_path(self) -> Path:
        """Return the SQLite database path."""

        return self._database_path

    def ensure_schema(self) -> None:
        """Create only the cache tables needed by the phase-1 data platform."""

        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_data_cache (
                    cache_key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    start_date TEXT,
                    end_date TEXT,
                    rows_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_market_data_cache_symbol
                ON market_data_cache(symbol, start_date, end_date);

                CREATE TABLE IF NOT EXISTS trading_calendar_cache (
                    cache_key TEXT PRIMARY KEY,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    days_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trading_calendar_cache_range
                ON trading_calendar_cache(start_date, end_date);

                CREATE TABLE IF NOT EXISTS market_sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset TEXT NOT NULL,
                    symbol TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    status TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    cache_key TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_market_sync_runs_dataset
                ON market_sync_runs(dataset, finished_at);

                CREATE TABLE IF NOT EXISTS market_price_bars (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    source TEXT,
                    synced_at TEXT NOT NULL,
                    PRIMARY KEY(symbol, date)
                );

                CREATE INDEX IF NOT EXISTS idx_market_price_bars_symbol_date
                ON market_price_bars(symbol, date);
                """
            )

    def fetch_market_data_cache(
        self,
        *,
        cache_key: str,
    ) -> Sequence[Mapping[str, Any]] | None:
        """Return cached price-history rows if present."""

        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT rows_json
                FROM market_data_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["rows_json"]))

    def fetch_market_data_cache_snapshot(
        self,
        *,
        cache_key: str,
    ) -> Mapping[str, Any] | None:
        """Return one market-data cache snapshot with metadata."""

        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT cache_key, symbol, start_date, end_date, rows_json, created_at
                FROM market_data_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        rows = json.loads(str(row["rows_json"]))
        return {
            "dataset": "price_history",
            "cache_key": row["cache_key"],
            "symbol": row["symbol"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "row_count": len(rows),
            "created_at": row["created_at"],
        }

    def upsert_market_data_cache(
        self,
        *,
        cache_key: str,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        rows: Sequence[Mapping[str, Any]],
        created_at: str,
    ) -> None:
        """Insert or replace cached price-history rows."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_data_cache (
                    cache_key,
                    symbol,
                    start_date,
                    end_date,
                    rows_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    symbol = excluded.symbol,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    rows_json = excluded.rows_json,
                    created_at = excluded.created_at
                """,
                (
                    cache_key,
                    symbol,
                    start_date,
                    end_date,
                    self._dump_rows(rows),
                    created_at,
                ),
            )

    def upsert_price_bars(
        self,
        *,
        symbol: str,
        rows: Sequence[Mapping[str, Any]],
        source: str | None,
        synced_at: str,
    ) -> int:
        """Insert or replace normalized OHLCV bars for stable local range queries."""

        normalized_rows = [_normalize_price_bar(row) for row in rows]
        normalized_rows = [row for row in normalized_rows if row.get("date")]
        self.ensure_schema()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO market_price_bars (
                    symbol,
                    date,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    source,
                    synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    source = excluded.source,
                    synced_at = excluded.synced_at
                """,
                [
                    (
                        symbol,
                        row["date"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        source,
                        synced_at,
                    )
                    for row in normalized_rows
                ],
            )
        return len(normalized_rows)

    def fetch_price_bars(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        """Return normalized locally stored OHLCV bars for one symbol and date range."""

        self.ensure_schema()
        filters = ["symbol = ?"]
        values: list[Any] = [symbol]
        if start_date:
            filters.append("date >= ?")
            values.append(start_date)
        if end_date:
            filters.append("date <= ?")
            values.append(end_date)
        limit_clause = ""
        if limit is not None:
            limit_clause = " LIMIT ?"
            values.append(max(1, min(int(limit), 5000)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT symbol, date, open, high, low, close, volume, source, synced_at
                FROM market_price_bars
                WHERE {' AND '.join(filters)}
                ORDER BY date ASC
                {limit_clause}
                """,
                tuple(values),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_price_bar_status(self, *, symbol: str | None = None) -> Mapping[str, Any]:
        """Return local normalized bar storage status."""

        self.ensure_schema()
        filters = []
        values: list[Any] = []
        if symbol:
            filters.append("symbol = ?")
            values.append(symbol)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS row_count, MIN(date) AS min_date, MAX(date) AS max_date, MAX(synced_at) AS last_synced_at
                FROM market_price_bars
                {where}
                """,
                tuple(values),
            ).fetchone()
        return dict(row) if row is not None else {"row_count": 0, "min_date": None, "max_date": None, "last_synced_at": None}
    def inspect_price_bar_quality(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Mapping[str, Any]:
        """Inspect local OHLCV quality for one symbol/date window."""

        rows = [dict(row) for row in self.fetch_price_bars(symbol=symbol, start_date=start_date, end_date=end_date)]
        rows_by_date = {str(row.get("date")): row for row in rows}
        expected_dates = _date_range(start_date, end_date)
        missing_dates = [date for date in expected_dates if date not in rows_by_date]
        invalid_rows: list[dict[str, Any]] = []
        required_fields = ("date", "open", "high", "low", "close", "volume")
        field_presence = {field: 0 for field in required_fields}
        for row in rows:
            for field in required_fields:
                if row.get(field) not in (None, ""):
                    field_presence[field] += 1
            reasons = _price_bar_quality_reasons(row)
            if reasons:
                invalid_rows.append({"date": row.get("date"), "reasons": reasons, "row": row})
        coverage = {
            field: (field_presence[field] / len(rows) if rows else 0.0)
            for field in required_fields
        }
        duplicate_count = self.count_price_bar_duplicates(symbol=symbol, start_date=start_date, end_date=end_date)
        status = "passed"
        if missing_dates or invalid_rows or duplicate_count:
            status = "needs_attention"
        if not rows:
            status = "empty"
        return {
            "dataset": "price_history",
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "expected_count": len(expected_dates),
            "stored_count": len(rows),
            "missing_count": len(missing_dates),
            "missing_dates": missing_dates,
            "duplicate_count": duplicate_count,
            "invalid_count": len(invalid_rows),
            "invalid_rows": invalid_rows,
            "field_coverage": coverage,
            "repair_plan": _build_repair_plan(symbol=symbol, missing_dates=missing_dates),
        }

    def count_price_bar_duplicates(self, *, symbol: str, start_date: str, end_date: str) -> int:
        """Return duplicate count for normalized table. Kept for future non-PK imports."""

        self.ensure_schema()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, date, COUNT(*) AS row_count
                FROM market_price_bars
                WHERE symbol = ? AND date >= ? AND date <= ?
                GROUP BY symbol, date
                HAVING COUNT(*) > 1
                """,
                (symbol, start_date, end_date),
            ).fetchall()
        return sum(int(row["row_count"]) - 1 for row in rows)
    def fetch_price_bar_symbols(self, *, limit: int = 100) -> Sequence[Mapping[str, Any]]:
        """Return local symbols with coverage summary for the data browser."""

        self.ensure_schema()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, COUNT(*) AS row_count, MIN(date) AS min_date, MAX(date) AS max_date, MAX(synced_at) AS last_synced_at
                FROM market_price_bars
                GROUP BY symbol
                ORDER BY last_synced_at DESC, symbol ASC
                LIMIT ?
                """,
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_price_bar_source_counts(self, *, symbol: str) -> Mapping[str, int]:
        """Return row counts by local bar source for one symbol."""

        self.ensure_schema()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT COALESCE(source, 'unknown') AS source, COUNT(*) AS row_count
                FROM market_price_bars
                WHERE symbol = ?
                GROUP BY COALESCE(source, 'unknown')
                ORDER BY row_count DESC, source ASC
                """,
                (symbol,),
            ).fetchall()
        return {str(row["source"]): int(row["row_count"] or 0) for row in rows}
    def fetch_market_sync_runs(
        self,
        *,
        dataset: str = "price_history",
        symbol: str | None = None,
        limit: int = 20,
    ) -> Sequence[Mapping[str, Any]]:
        """Return recent sync runs for the data browser."""

        self.ensure_schema()
        filters = ["dataset = ?"]
        values: list[Any] = [dataset]
        if symbol:
            filters.append("symbol = ?")
            values.append(symbol)
        values.append(max(1, min(int(limit), 200)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT dataset, symbol, start_date, end_date, status, row_count, cache_key, started_at, finished_at
                FROM market_sync_runs
                WHERE {' AND '.join(filters)}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [dict(row) for row in rows]
    def fetch_trading_calendar_cache(
        self,
        *,
        cache_key: str,
    ) -> Sequence[str] | None:
        """Return cached trading-calendar rows if present."""

        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT days_json
                FROM trading_calendar_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["days_json"]))

    def fetch_trading_calendar_cache_snapshot(
        self,
        *,
        cache_key: str,
    ) -> Mapping[str, Any] | None:
        """Return one trading-calendar cache snapshot with metadata."""

        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT cache_key, start_date, end_date, days_json, created_at
                FROM trading_calendar_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        days = json.loads(str(row["days_json"]))
        return {
            "dataset": "trading_calendar",
            "cache_key": row["cache_key"],
            "symbol": None,
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "row_count": len(days),
            "created_at": row["created_at"],
        }

    def upsert_trading_calendar_cache(
        self,
        *,
        cache_key: str,
        start_date: str,
        end_date: str,
        days: Sequence[str],
        created_at: str,
    ) -> None:
        """Insert or replace cached trading-calendar rows."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trading_calendar_cache (
                    cache_key,
                    start_date,
                    end_date,
                    days_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    days_json = excluded.days_json,
                    created_at = excluded.created_at
                """,
                (
                    cache_key,
                    start_date,
                    end_date,
                    self._dump_text_sequence(days),
                    created_at,
                ),
            )

    def insert_market_sync_run(
        self,
        *,
        dataset: str,
        symbol: str | None,
        start_date: str | None,
        end_date: str | None,
        status: str,
        row_count: int,
        cache_key: str | None,
        started_at: str,
        finished_at: str,
    ) -> None:
        """Append one explicit market-data sync execution record."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_sync_runs (
                    dataset,
                    symbol,
                    start_date,
                    end_date,
                    status,
                    row_count,
                    cache_key,
                    started_at,
                    finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset,
                    symbol,
                    start_date,
                    end_date,
                    status,
                    int(row_count),
                    cache_key,
                    started_at,
                    finished_at,
                ),
            )

    def fetch_latest_market_sync_run(
        self,
        *,
        dataset: str,
    ) -> Mapping[str, Any] | None:
        """Return the most recent sync execution record for one dataset."""

        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT dataset, symbol, start_date, end_date, status, row_count, cache_key, started_at, finished_at
                FROM market_sync_runs
                WHERE dataset = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (dataset,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    @contextmanager
    def _connect(self) -> Any:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _dump_rows(rows: Sequence[Mapping[str, Any]]) -> str:
        return json.dumps([dict(row) for row in rows], ensure_ascii=False)

    @staticmethod
    def _dump_text_sequence(rows: Sequence[str]) -> str:
        return json.dumps([str(row) for row in rows], ensure_ascii=False)


def _normalize_price_bar(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "date": str(payload.get("date") or ""),
        "open": float(payload.get("open") or 0.0),
        "high": float(payload.get("high") or 0.0),
        "low": float(payload.get("low") or 0.0),
        "close": float(payload.get("close") or 0.0),
        "volume": float(payload.get("volume") or 0.0),
    }

def _date_range(start_date: str, end_date: str) -> list[str]:
    from datetime import date, timedelta

    try:
        current = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
    except ValueError:
        return []
    if end < current:
        return []
    days: list[str] = []
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _price_bar_quality_reasons(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    try:
        open_price = float(row.get("open"))
        high = float(row.get("high"))
        low = float(row.get("low"))
        close = float(row.get("close"))
        volume = float(row.get("volume"))
    except (TypeError, ValueError):
        return ["non_numeric_ohlcv"]
    if min(open_price, high, low, close) < 0:
        reasons.append("negative_price")
    if volume < 0:
        reasons.append("negative_volume")
    if high < low:
        reasons.append("high_below_low")
    if high < max(open_price, close):
        reasons.append("high_below_open_or_close")
    if low > min(open_price, close):
        reasons.append("low_above_open_or_close")
    return reasons


def _build_repair_plan(*, symbol: str, missing_dates: list[str]) -> list[dict[str, str]]:
    if not missing_dates:
        return []
    ranges: list[dict[str, str]] = []
    start = previous = missing_dates[0]
    for current in missing_dates[1:]:
        if _is_next_date(previous, current):
            previous = current
            continue
        ranges.append({"symbol": symbol, "start_date": start, "end_date": previous})
        start = previous = current
    ranges.append({"symbol": symbol, "start_date": start, "end_date": previous})
    return ranges


def _is_next_date(previous: str, current: str) -> bool:
    from datetime import date, timedelta

    try:
        return date.fromisoformat(current) == date.fromisoformat(previous) + timedelta(days=1)
    except ValueError:
        return False
