"""Synchronize selected or all current A-share symbols into the canonical store."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    import akshare as _akshare  # Preload native dependencies before worker threads.

    from data_platform.providers.akshare_a_share_provider import AkshareAShareProvider
    from data_platform.storage.a_share_market_store import AShareMarketStore

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        default=os.environ.get("SCQ_A_SHARE_CANONICAL_DB_PATH")
        or "var/market/a_share_market.sqlite3",
    )
    parser.add_argument("--symbols", default="", help="Comma-separated six-digit symbols")
    parser.add_argument("--all-current", action="store_true")
    parser.add_argument("--adjustments", default="raw")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--proxy", default=os.environ.get("SCQ_AKSHARE_PROXY"))
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--refresh-symbols", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--result-log", default="var/market/a_share_sync_results.jsonl")
    args = parser.parse_args()
    if not args.symbols and not args.all_current:
        parser.error("one of --symbols or --all-current is required")
    if args.symbols and args.all_current:
        parser.error("--symbols and --all-current are mutually exclusive")
    if args.symbols and not args.start_date:
        parser.error("--start-date is required with --symbols")

    store = AShareMarketStore(Path(args.target))
    store.ensure_schema()
    provider = AkshareAShareProvider(
        proxy_url=args.proxy,
        retry_count=args.retry_count,
    )
    if args.refresh_symbols:
        symbols = provider.list_symbols()
        replaced = store.replace_current_symbols(symbols)
        print(
            f"[akshare] symbols_received={len(symbols)} current_replaced={replaced}",
            flush=True,
        )

    tasks = _build_tasks(store, args)
    print(
        f"[akshare] tasks={len(tasks)} workers={max(1, args.workers)} "
        f"end_date={args.end_date}",
        flush=True,
    )
    if tasks and args.workers > 1:
        warmup = tasks[0]
        provider.fetch_daily_prices(
            symbol=warmup["symbol"],
            adjustment=warmup["adjustment"],
            start_date=warmup["start_date"],
            end_date=args.end_date,
        )
        print(f"[akshare] worker_runtime_warmed symbol={warmup['symbol']}", flush=True)
    results: list[dict[str, Any]] = []
    result_log = Path(args.result_log)
    result_log.parent.mkdir(parents=True, exist_ok=True)
    with result_log.open("a", encoding="utf-8") as log_handle, ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, 32))
    ) as executor:
        future_map = {
            executor.submit(
                provider.sync_symbol,
                store,
                symbol=task["symbol"],
                adjustment=task["adjustment"],
                start_date=task["start_date"],
                end_date=args.end_date,
            ): task
            for task in tasks
        }
        for future in as_completed(future_map):
            task = future_map[future]
            try:
                result = future.result()
            except Exception as error:
                result = {
                    "status": "failed",
                    **task,
                    "end_date": args.end_date,
                    "error": f"{type(error).__name__}: {error}",
                }
            results.append(result)
            log_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            log_handle.flush()
            if not args.compact or result.get("status") != "completed":
                print(json.dumps(result, ensure_ascii=False), flush=True)
            elif len(results) % max(1, args.progress_every) == 0:
                failures_so_far = sum(
                    item.get("status") != "completed" for item in results
                )
                print(
                    f"[akshare] completed={len(results)}/{len(tasks)} "
                    f"failed={failures_so_far}",
                    flush=True,
                )

    failures = [item for item in results if item.get("status") != "completed"]
    rows_written = sum(int(item.get("rows_written") or 0) for item in results)
    summary = {
        "status": "completed" if not failures else "partial_failure",
        "task_count": len(tasks),
        "completed_count": len(results) - len(failures),
        "failed_count": len(failures),
        "rows_written": rows_written,
        "end_date": args.end_date,
        "overview": store.get_overview(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


def _build_tasks(store: Any, args: argparse.Namespace) -> list[dict[str, str]]:
    adjustments = _items(args.adjustments)
    if not args.all_current:
        return [
            {
                "symbol": symbol,
                "adjustment": adjustment,
                "start_date": str(args.start_date),
            }
            for symbol in _items(args.symbols)
            for adjustment in adjustments
        ]

    tasks = []
    floor = str(args.start_date or "2015-01-05")
    for adjustment in adjustments:
        targets = store.list_sync_targets(
            adjustment=adjustment,
            end_date=args.end_date,
            limit=args.limit,
        )
        for target in targets:
            latest = target.get("latest_date")
            resume_date = (
                (date.fromisoformat(str(latest)) + timedelta(days=1)).isoformat()
                if latest
                else floor
            )
            tasks.append(
                {
                    "symbol": str(target["symbol"]),
                    "adjustment": adjustment,
                    "start_date": max(floor, resume_date),
                }
            )
    return tasks


def _items(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


if __name__ == "__main__":
    main()
