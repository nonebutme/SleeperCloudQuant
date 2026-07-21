"""Formal quality smoke for the project-owned full-market A-share database."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from data_platform.storage.a_share_market_store import AShareMarketStore

    path = Path("var/market/a_share_market.sqlite3")
    store = AShareMarketStore(path)
    overview = store.get_overview()
    if overview.get("source") != "canonical_a_share_sqlite":
        raise SystemExit("full-market A-share quality failed: canonical store is unavailable")
    if int(overview.get("current_symbol_count") or 0) < 5500:
        raise SystemExit("full-market A-share quality failed: current catalog is incomplete")
    if int(overview.get("catalog_symbol_count") or 0) <= int(overview["current_symbol_count"]):
        raise SystemExit("full-market A-share quality failed: historical catalog is missing")

    with closing(sqlite3.connect(path)) as connection:
        raw_missing_volume = int(connection.execute(
            """SELECT COUNT(*) FROM market_daily_prices
               WHERE adjustment='raw' AND (volume IS NULL OR volume < 0)"""
        ).fetchone()[0])
        raw_invalid_ohlc = int(connection.execute(
            """SELECT COUNT(*) FROM market_daily_prices
               WHERE adjustment='raw'
                 AND (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
                      OR open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                      OR high < open OR high < close OR high < low
                      OR low > open OR low > close)"""
        ).fetchone()[0])
    if raw_missing_volume or raw_invalid_ohlc:
        raise SystemExit(
            "full-market A-share quality failed: "
            f"raw_missing_volume={raw_missing_volume} raw_invalid_ohlc={raw_invalid_ohlc}"
        )

    for mode in ("raw", "qfq", "hfq"):
        item = overview["adjustments"][mode]
        if int(item.get("row_count") or 0) < 11_000_000:
            raise SystemExit(f"full-market A-share quality failed: {mode} row count is too small")
        if int(item.get("duplicate_row_count") or 0) != 0:
            raise SystemExit(f"full-market A-share quality failed: {mode} duplicates remain")
        if float(item.get("fresh_coverage_pct") or 0) < 99:
            raise SystemExit(f"full-market A-share quality failed: {mode} coverage is below 99%")
        if item.get("quality_status") != "passed":
            raise SystemExit(f"full-market A-share quality failed: {mode} status is not passed")
        if (date.today() - date.fromisoformat(item["max_date"])).days > 7:
            raise SystemExit(f"full-market A-share quality failed: {mode} is stale")

    for symbol in ("000001", "920000", "689009"):
        for mode in ("raw", "qfq", "hfq"):
            daily = store.fetch_daily_prices(
                symbol=symbol,
                adjustment=mode,
                start_date="2026-07-13",
                end_date="2026-07-17",
                limit=10,
            )
            rows = daily["rows"]
            if not rows or rows[0]["date"] != "2026-07-17":
                raise SystemExit(
                    f"full-market A-share quality failed: {symbol}/{mode} latest row is missing"
                )
            latest = rows[0]
            if not all(
                float(latest[field] or 0) > 0
                for field in ("open", "high", "low", "close", "volume")
            ):
                raise SystemExit(
                    f"full-market A-share quality failed: {symbol}/{mode} OHLCV is invalid"
                )

    for mode in ("raw", "qfq", "hfq"):
        targets = store.list_sync_targets(adjustment=mode, end_date="2026-07-17")
        if len(targets) > 10:
            raise SystemExit(f"full-market A-share quality failed: {mode} has too many late symbols")

    print(
        "full-market A-share quality passed:",
        f"current={overview['current_symbol_count']}",
        f"catalog={overview['catalog_symbol_count']}",
        "latest=2026-07-17",
        "coverage=" + ",".join(
            f"{mode}:{overview['adjustments'][mode]['fresh_coverage_pct']}%"
            for mode in ("raw", "qfq", "hfq")
        ),
        "duplicates=0",
        "raw_ohlcv=valid",
    )


if __name__ == "__main__":
    main()
