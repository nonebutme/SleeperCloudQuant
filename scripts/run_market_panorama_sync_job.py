"""Run one persisted market-panorama sync job in a standalone process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.market_panorama_service import MarketPanoramaService
from data_platform import MarketPanoramaStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="var/runtime/market_panorama.sqlite3")
    parser.add_argument("--market-database", default="var/market/a_share_market.sqlite3")
    parser.add_argument("--classification-database", default="var/runtime/a_share_classification_history.sqlite3")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    service = MarketPanoramaService(
        MarketPanoramaStore(Path(args.database)),
        market_database=Path(args.market_database),
        classification_database=Path(args.classification_database),
        max_workers=args.workers,
    )
    print(json.dumps(service.run_job(args.job_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()