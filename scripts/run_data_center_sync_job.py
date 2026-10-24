"""Run one data-center sync job outside the Web service process."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
from data_platform import DataCenterStore
from data_platform.providers.akshare_governance_provider import AkshareGovernanceProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()

    database_path = Path(args.database)
    frozen = DataCenterStore(database_path).get_route_snapshot(task_id=args.job_id)
    effective = dict((frozen or {}).get("effective_config") or {})
    market_store = AShareMarketStore(database_path)
    governance_store = AShareGovernanceStore(database_path)
    scheduler = AShareSyncScheduler(
        database_path,
        market_store=market_store,
        governance_store=governance_store,
        provider=AkshareGovernanceProvider(
            proxy_url=os.environ.get("SCQ_AKSHARE_PROXY"),
            retry_count=int(effective.get("retry_count") or
                os.environ.get("SCQ_A_SHARE_SCHEDULER_PROVIDER_RETRIES", "2")),
        ),
        requests_per_minute=int(effective.get("requests_per_minute") or
            os.environ.get("SCQ_A_SHARE_SCHEDULER_RPM", "60")),
        max_workers=int(effective.get("concurrency") or
            os.environ.get("SCQ_A_SHARE_SCHEDULER_WORKERS", "4")),
        retry_count=int(effective.get("retry_count") or
            os.environ.get("SCQ_A_SHARE_SCHEDULER_RETRIES", "3")),
        base_backoff_seconds=float(effective.get("backoff_seconds") or 2.0),
    )
    scheduler.ensure_schema()
    result = scheduler.run_job(args.job_id)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
