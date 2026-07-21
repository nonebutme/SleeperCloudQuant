"""Migrate the accepted legacy A-share database into the canonical project store."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from data_platform.storage.a_share_market_store import AShareMarketStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.environ.get("SCQ_A_SHARE_DB_PATH") or _default_source())
    parser.add_argument("--target", default=os.environ.get("SCQ_A_SHARE_CANONICAL_DB_PATH") or "var/market/a_share_market.sqlite3")
    parser.add_argument("--adjustments", default="raw,qfq,hfq")
    parser.add_argument("--batch-size", type=int, default=20_000)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()

    store = AShareMarketStore(Path(args.target))
    result = store.import_legacy(
        Path(args.source),
        adjustments=[item.strip() for item in args.adjustments.split(",") if item.strip()],
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        progress=lambda mode, count, rowid: print(
            f"[migration] adjustment={mode} rows_read={count} source_rowid={rowid}",
            flush=True,
        ),
    )
    result["overview"] = store.get_overview()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _default_source() -> str:
    return str(
        Path(__file__).resolve().parents[2]
        / "SleeperCloudQuant-old"
        / "PyDB"
        / "StockMarket"
        / "stock_database"
        / "data"
        / "stockmarket.db"
    )


if __name__ == "__main__":
    main()
