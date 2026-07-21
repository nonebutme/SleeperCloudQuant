"""Resumable, auditable batch sync for historical A-share industries."""

from __future__ import annotations

import argparse
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


_SYNC_RATE_LOCK = threading.Lock()
_SYNC_NEXT_REQUEST_AT = 0.0


def main() -> None:
    ensure_project_root_on_sys_path()
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-database", required=True)
    parser.add_argument("--classification-database", default="var/runtime/a_share_classification_history.sqlite3")
    parser.add_argument("--job-id", default="a-share-industry-history-v1")
    parser.add_argument("--start-date", default="19900101")
    parser.add_argument("--end-date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-pending", type=int, default=0)
    parser.add_argument("--statuses", default="pending,failed")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--request-interval", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()

    from data_platform import AShareMarketStore, ClassificationHistoryStore
    from scripts.sync_a_share_classification_history import _fetch_cninfo_industries

    market_store = AShareMarketStore(Path(args.canonical_database))
    symbols = _current_symbols(market_store, args.limit)
    classification_store = ClassificationHistoryStore(args.classification_database)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prepared = classification_store.prepare_sync_job(args.job_id, symbols, observed_at=now)
    statuses = tuple(value.strip() for value in str(args.statuses).split(",") if value.strip())
    pending = classification_store.list_sync_symbols(args.job_id, statuses=statuses)
    if int(args.max_pending) > 0:
        pending = pending[: int(args.max_pending)]
    workers = max(1, min(int(args.workers), 8, len(pending) or 1))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="industry-sync") as executor:
        futures = {
            executor.submit(_fetch_with_retry, symbol, args.start_date, args.end_date, args.retries, args.request_interval): symbol
            for symbol in pending
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                rows, attempt = future.result()
                interval_count = classification_store.upsert_intervals(rows)
                classification_store.mark_sync_state(
                    args.job_id,
                    symbol,
                    status="completed" if interval_count else "completed_empty",
                    attempt_count=attempt,
                    interval_count=interval_count,
                    updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
            except Exception as exc:
                classification_store.mark_sync_state(
                    args.job_id,
                    symbol,
                    status="failed",
                    attempt_count=int(args.retries) + 1,
                    error_message=f"{type(exc).__name__}: {exc}",
                    updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
    print({"prepared": prepared, "pending_processed": len(pending), "summary": classification_store.sync_job_summary(args.job_id)})


def _current_symbols(store: Any, limit: int) -> list[str]:
    symbols: list[str] = []
    offset = 0
    while True:
        page = store.list_symbols(limit=500, offset=offset)
        items = list(page.get("items") or [])
        symbols.extend(
            str(item.get("symbol") or "").split(".")[0].zfill(6)
            for item in items
            if str(item.get("listing_status") or "") == "current"
        )
        if limit > 0 and len(symbols) >= limit:
            return symbols[:limit]
        offset += len(items)
        if not items or offset >= int(page.get("total") or 0):
            return symbols


def _fetch_with_retry(symbol: str, start_date: str, end_date: str, retries: int, request_interval: float = 1.0):
    from scripts.sync_a_share_classification_history import _fetch_cninfo_industries

    last_error = None
    for attempt in range(1, max(0, int(retries)) + 2):
        try:
            _wait_for_request_slot(request_interval)
            return _fetch_cninfo_industries([symbol], start_date, end_date), attempt
        except Exception as exc:
            last_error = exc
            if attempt <= int(retries):
                time.sleep(min(5 * (2 ** (attempt - 1)), 30) + random.uniform(0.0, 1.0))
    raise last_error or RuntimeError("industry sync failed")


def _wait_for_request_slot(interval: float) -> None:
    global _SYNC_NEXT_REQUEST_AT
    with _SYNC_RATE_LOCK:
        now = time.monotonic()
        scheduled_at = max(now, _SYNC_NEXT_REQUEST_AT)
        _SYNC_NEXT_REQUEST_AT = scheduled_at + max(0.0, float(interval))
    delay = scheduled_at - now
    if delay > 0:
        time.sleep(delay)

if __name__ == "__main__":
    main()
