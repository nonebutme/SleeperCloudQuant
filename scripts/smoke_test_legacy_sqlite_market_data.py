"""Smoke test for the read-only legacy SQLite market-data repository."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from data_platform import LegacySQLiteMarketDataRepository

    with tempfile.TemporaryDirectory() as tmpdir:
        database_path = Path(tmpdir) / "legacy_market.sqlite3"
        _seed_legacy_cache(database_path)

        repository = LegacySQLiteMarketDataRepository(database_path)
        rows = repository.fetch_price_history("000001.XSHE", start_date="2020-01-02", end_date="2020-01-03")
        if [row["date"] for row in rows] != ["2020-01-02", "2020-01-03"]:
            raise SystemExit("legacy SQLite market smoke test failed: price window mismatch")
        if rows[0]["open"] != 10.0 or rows[1]["close"] != 10.8:
            raise SystemExit("legacy SQLite market smoke test failed: normalized OHLC mismatch")
        if repository.fetch_price_history("UNKNOWN.XSHG", start_date="2020-01-02", end_date="2020-01-03"):
            raise SystemExit("legacy SQLite market smoke test failed: unknown symbol should be empty")

        days = repository.fetch_trading_calendar(start_date="2020-01-02", end_date="2020-01-03")
        if days != ["2020-01-02", "2020-01-03"]:
            raise SystemExit("legacy SQLite market smoke test failed: trading calendar mismatch")

    print("legacy SQLite market smoke test passed")


def _seed_legacy_cache(database_path: Path) -> None:
    rows = [
        {"date": "2020-01-02", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1000},
        {"date": "2020-01-03", "open": 10.2, "high": 10.9, "low": 10.1, "close": 10.8, "volume": 1200},
        {"date": "2020-01-06", "open": 10.8, "high": 11.0, "low": 10.6, "close": 10.7, "volume": 900},
    ]
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE market_data_cache (
                cache_key TEXT PRIMARY KEY,
                symbol TEXT,
                start_date TEXT,
                end_date TEXT,
                rows_json TEXT,
                created_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO market_data_cache (cache_key, symbol, start_date, end_date, rows_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("demo-cache", "000001.XSHE", "2020-01-01", "2020-01-06", json.dumps(rows), "2020-01-06T15:00:00+08:00"),
        )
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    main()

