"""Synchronize the six core A-share indices into the governed local store."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.providers.akshare_governance_provider import AkshareGovernanceProvider
from data_platform.storage.a_share_governance_store import AShareGovernanceStore


CORE_INDICES = (
    ("000001", "上证指数"),
    ("399001", "深证成指"),
    ("899050", "北证50"),
    ("000300", "沪深300"),
    ("399006", "创业板指"),
    ("000688", "科创50"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        default="var/market/a_share_market.sqlite3",
        help="Canonical A-share SQLite database.",
    )
    parser.add_argument("--start-date", default="2015-01-05")
    parser.add_argument("--end-date", default=date.today().isoformat())
    args = parser.parse_args()

    store = AShareGovernanceStore(Path(args.database))
    store.ensure_schema()
    provider = AkshareGovernanceProvider(retry_count=3)
    summaries: list[dict[str, object]] = []
    for symbol, name in CORE_INDICES:
        rows = provider.fetch_index_daily_prices(
            index_symbol=symbol,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        if not rows:
            raise RuntimeError(f"{symbol} {name} returned no index rows")
        invalid = [
            row
            for row in rows
            if not row.get("trade_date")
            or row.get("open") is None
            or row.get("high") is None
            or row.get("low") is None
            or row.get("close") is None
        ]
        if invalid:
            raise RuntimeError(f"{symbol} {name} returned {len(invalid)} invalid rows")
        written = store.upsert_index_prices(rows)
        summaries.append(
            {
                "index_symbol": symbol,
                "name": name,
                "fetched": len(rows),
                "written": written,
                "min_date": rows[0]["trade_date"],
                "max_date": rows[-1]["trade_date"],
                "source": rows[-1]["source"],
            }
        )
    print(json.dumps({"status": "completed", "indices": summaries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
