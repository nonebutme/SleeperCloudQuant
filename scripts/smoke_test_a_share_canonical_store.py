"""Smoke test for canonical A-share migration, deduplication, and reads."""

from __future__ import annotations

import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from data_platform.storage.a_share_market_store import AShareMarketStore

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        legacy_path = root / "legacy.db"
        target_path = root / "canonical.sqlite3"
        _build_legacy_fixture(legacy_path)

        store = AShareMarketStore(target_path)
        first = store.import_legacy(
            legacy_path,
            adjustments=("raw", "qfq", "hfq"),
            batch_size=2,
            max_batches=1,
        )
        if any(item["rows_read"] != 2 for item in first["adjustments"].values()):
            raise SystemExit("canonical A-share smoke failed: bounded migration mismatch")

        second = store.import_legacy(
            legacy_path,
            adjustments=("raw", "qfq", "hfq"),
            batch_size=2,
        )
        if any(not item["completed"] for item in second["adjustments"].values()):
            raise SystemExit("canonical A-share smoke failed: resume did not complete")

        overview = store.get_overview()
        if overview["current_symbol_count"] != 2:
            raise SystemExit("canonical A-share smoke failed: symbol count mismatch")
        if any(overview["adjustments"][mode]["duplicate_row_count"] != 0 for mode in ("raw", "qfq", "hfq")):
            raise SystemExit("canonical A-share smoke failed: duplicate rows remain")

        daily = store.fetch_daily_prices(
            symbol="000001",
            adjustment="raw",
            start_date="2026-03-30",
            end_date="2026-03-31",
        )
        if daily["total"] != 2 or daily["rows"][0]["date"] != "2026-03-31":
            raise SystemExit("canonical A-share smoke failed: daily rows mismatch")
        if float(daily["rows"][-1]["close"]) != 11.0:
            raise SystemExit("canonical A-share smoke failed: later duplicate did not win")

        catalog = store.list_symbols(query="平安")
        if catalog["total"] != 1 or catalog["items"][0]["symbol"] != "000001":
            raise SystemExit("canonical A-share smoke failed: catalog query mismatch")

        print(
            "canonical A-share smoke passed:",
            f"symbols={overview['current_symbol_count']}",
            f"raw_rows={overview['adjustments']['raw']['row_count']}",
            f"latest={overview['adjustments']['raw']['max_date']}",
            "duplicates=0",
            "resume=passed",
        )


def _build_legacy_fixture(path: Path) -> None:
    columns = (
        '"日期" TEXT, "股票代码" TEXT, "开盘" REAL, "收盘" REAL, "最高" REAL, '
        '"最低" REAL, "成交量" REAL, "成交额" REAL, "振幅" REAL, "涨跌幅" REAL, '
        '"涨跌额" REAL, "换手率" REAL'
    )
    rows = [
        ("2026-03-30", "000001", 10, 10.5, 11, 9.8, 100, 1000, 1, 2, 0.2, 3),
        ("2026-03-30", "000001", 10, 11.0, 11.2, 9.8, 110, 1100, 1, 2, 0.5, 3),
        ("2026-03-31", "000001", 11, 11.5, 12, 10.8, 120, 1200, 1, 2, 0.5, 3),
        ("2026-03-31", "600000", 8, 8.2, 8.4, 7.9, 90, 900, 1, 2, 0.2, 2),
    ]
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE stock_list (code TEXT, name TEXT)")
        connection.executemany(
            "INSERT INTO stock_list VALUES (?, ?)",
            [("000001", "平安银行"), ("600000", "浦发银行")],
        )
        for table in ("stock_hist", "stock_hist_qfq", "stock_hist_hfq"):
            connection.execute(f"CREATE TABLE {table} ({columns})")
            connection.executemany(
                f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )


if __name__ == "__main__":
    main()
