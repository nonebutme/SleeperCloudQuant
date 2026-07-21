"""Minimal verification script for the formal SQLite market-data cache."""

from __future__ import annotations

from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from data_platform import SqliteMetadataStore

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
        raise SystemExit("formal sqlite cache verification failed: market cache mismatch")
    snapshot = store.fetch_market_data_cache_snapshot(cache_key=cache_key)
    if snapshot is None or snapshot.get("row_count") != 2:
        raise SystemExit("formal sqlite cache verification failed: market cache snapshot missing")

    calendar_key = "trading_calendar|2020-01-01|2020-01-03"
    days = ["2020-01-01", "2020-01-02", "2020-01-03"]
    store.upsert_trading_calendar_cache(
        cache_key=calendar_key,
        start_date="2020-01-01",
        end_date="2020-01-03",
        days=days,
        created_at="2026-06-30T00:00:00+08:00",
    )

    loaded_days = store.fetch_trading_calendar_cache(cache_key=calendar_key)
    if loaded_days != days:
        raise SystemExit("formal sqlite cache verification failed: trading calendar cache mismatch")
    calendar_snapshot = store.fetch_trading_calendar_cache_snapshot(cache_key=calendar_key)
    if calendar_snapshot is None or calendar_snapshot.get("row_count") != 3:
        raise SystemExit("formal sqlite cache verification failed: trading calendar snapshot missing")

    store.insert_market_sync_run(
        dataset="price_history",
        symbol="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-01-02",
        status="completed",
        row_count=2,
        cache_key=cache_key,
        started_at="2026-06-30T00:00:00+08:00",
        finished_at="2026-06-30T00:01:00+08:00",
    )
    latest = store.fetch_latest_market_sync_run(dataset="price_history")
    if latest is None or latest.get("row_count") != 2:
        raise SystemExit("formal sqlite cache verification failed: sync run missing")

    print("formal sqlite cache verification passed")


if __name__ == "__main__":
    main()
