"""Minimal verification script for the formal SQLite market-data cache."""

from __future__ import annotations

from pathlib import Path

from data_platform import SqliteMetadataStore


def main() -> None:
    database_path = Path("tmp") / "phase1_market_cache.sqlite3"
    store = SqliteMetadataStore(database_path)
    store.ensure_schema()

    cache_key = "price_history|000001.XSHE|2020-01-01|2020-01-02"
    rows = [
        {
            "date": "2020-01-01",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "volume": 1000.0,
        },
        {
            "date": "2020-01-02",
            "open": 10.2,
            "high": 10.8,
            "low": 10.1,
            "close": 10.7,
            "volume": 1200.0,
        },
    ]

    store.upsert_market_data_cache(
        cache_key=cache_key,
        symbol="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-01-02",
        rows=rows,
        created_at="2026-06-30T00:00:00+08:00",
    )

    loaded = store.fetch_market_data_cache(cache_key=cache_key)
    if loaded != rows:
        raise SystemExit("formal sqlite cache verification failed")

    print("formal sqlite cache verification passed")


if __name__ == "__main__":
    main()
