"""Create, resume and inspect the stage-78.3 context backfill."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from data_platform.a_share_context_backfill import (
        ALL_DATASETS,
        AShareContextBackfill,
    )
    from data_platform.providers.akshare_governance_provider import (
        AkshareGovernanceProvider,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        default=os.environ.get("SCQ_A_SHARE_CANONICAL_DB_PATH")
        or "var/market/a_share_market.sqlite3",
    )
    parser.add_argument(
        "--action",
        choices=("create-run", "create", "run", "status", "retry"),
        default="create-run",
    )
    parser.add_argument("--job-id")
    parser.add_argument("--symbols")
    parser.add_argument("--all-current", action="store_true")
    parser.add_argument("--start-date", default="2015-01-05")
    parser.add_argument("--end-date")
    parser.add_argument("--datasets", default=",".join(ALL_DATASETS))
    parser.add_argument("--requests-per-minute", type=int, default=60)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--base-backoff-seconds", type=float, default=2.0)
    parser.add_argument("--proxy", default=os.environ.get("SCQ_AKSHARE_PROXY"))
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()

    database_path = Path(args.target)
    if not database_path.is_file():
        raise SystemExit(f"canonical database not found: {database_path}")
    provider = AkshareGovernanceProvider(proxy_url=args.proxy, retry_count=1)
    service = AShareContextBackfill(
        database_path,
        provider=provider,
        requests_per_minute=args.requests_per_minute,
        max_workers=args.max_workers,
        retry_count=args.retry_count,
        base_backoff_seconds=args.base_backoff_seconds,
    )

    if args.action in {"create-run", "create"}:
        if not args.end_date:
            raise SystemExit("--end-date is required when creating a job")
        symbols = _items(args.symbols) if args.symbols else None
        if not symbols and not args.all_current:
            raise SystemExit("provide --symbols or --all-current")
        job = service.create_job(
            start_date=args.start_date,
            end_date=args.end_date,
            symbols=symbols,
            all_current=bool(args.all_current),
            datasets=_items(args.datasets),
        )
        print(json.dumps(job, ensure_ascii=False, indent=2), flush=True)
        if args.action == "create":
            return
        job_id = str(job["job_id"])
    else:
        latest = service.latest_job()
        job_id = args.job_id or (str(latest["job_id"]) if latest else "")
        if not job_id:
            raise SystemExit("--job-id is required when no previous job exists")

    if args.action == "status":
        result = service.get_job(job_id)
    elif args.action == "retry":
        result = service.retry_quarantined(job_id)
    else:
        result = service.run_job(
            job_id,
            publish=not args.no_publish,
            max_items=args.max_items,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


def _items(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


if __name__ == "__main__":
    main()
