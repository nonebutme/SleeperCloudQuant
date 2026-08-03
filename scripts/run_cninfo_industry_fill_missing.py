"""Run an audited CNINFO industry fill-missing job without publishing a data version."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from _project_bootstrap import ensure_project_root_on_sys_path


STANDARD_PRIORITIES = {
    "??????????????????": 0,
    "????????": 1,
    "??????????": 2,
    "????????": 3,
}
ROUTE_IDS = (
    "cninfo-industry-category",
    "cninfo-industry-change",
)


def main() -> None:
    ensure_project_root_on_sys_path()
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="000001")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--history-start", default="1990-01-01")
    parser.add_argument(
        "--control-database", default="var/market/a_share_market.sqlite3"
    )
    parser.add_argument(
        "--classification-database",
        default="var/runtime/a_share_classification_history.sqlite3",
    )
    parser.add_argument("--requests-per-minute", type=int, default=10)
    args = parser.parse_args()

    from data_platform.providers.cninfo_controlled_provider import (
        CninfoControlledProvider,
    )
    from data_platform.storage.classification_history_store import (
        ClassificationHistoryStore,
    )
    from data_platform.storage.data_center_store import DataCenterStore

    symbols = tuple(
        dict.fromkeys(
            item.strip().split(".")[0].zfill(6)
            for item in args.symbols.split(",")
            if item.strip()
        )
    )
    if not symbols:
        raise SystemExit("at least one symbol is required")
    if args.requests_per_minute < 1 or args.requests_per_minute > 10:
        raise SystemExit("requests-per-minute must be between 1 and 10")

    control_store = DataCenterStore(Path(args.control_database))
    fact_store = ClassificationHistoryStore(Path(args.classification_database))
    routes = _validate_control_plane(control_store)
    job_id = f"cninfo-industry-fill-{args.as_of.replace('-', '')}-{uuid.uuid4().hex[:10]}"
    observed_at = _utc_now()
    snapshot = control_store.freeze_route_snapshot(
        "industry_classification", task_id=job_id
    )
    fact_store.prepare_sync_job(job_id, symbols, observed_at=observed_at)
    provider = CninfoControlledProvider(
        requests_per_minute=args.requests_per_minute,
    )

    category_route = routes["cninfo-industry-category"]
    try:
        categories = _probe(
            control_store,
            category_route["route_id"],
            provider.fetch_industry_categories,
        )
        if len(categories) < 250 or any(
            not row.get("category_code") or not row.get("category_name")
            for row in categories
        ):
            raise RuntimeError("industry category catalog contract failed")
    except Exception as error:
        for symbol in symbols:
            fact_store.mark_sync_state(
                job_id,
                symbol,
                status="failed",
                attempt_count=1,
                error_message=f"category_catalog: {type(error).__name__}: {error}",
                updated_at=_utc_now(),
            )
        _print_result(
            job_id=job_id,
            snapshot=snapshot,
            items=[],
            writes=0,
            status="failed",
            summary=fact_store.sync_job_summary(job_id),
        )
        raise SystemExit(2)

    items: list[dict[str, Any]] = []
    writes = 0
    change_route = routes["cninfo-industry-change"]
    for symbol in symbols:
        try:
            remote_rows = _probe(
                control_store,
                change_route["route_id"],
                lambda symbol=symbol: provider.fetch_industry_intervals(
                    symbol,
                    args.history_start,
                    args.as_of,
                    observed_at=observed_at,
                ),
            )
            if not _industry_contract(remote_rows):
                raise RuntimeError("industry history contract failed")
            remote_current = _select_current(remote_rows, args.as_of)
            if remote_current is None:
                raise RuntimeError("industry history has no current classification")
            local_current = fact_store.resolve(symbol, "industry", args.as_of)
            local_categories = sorted(
                {str(row.get("category") or "") for row in local_current if row.get("category")}
            )
            remote_category = str(remote_current["category"])
            selected_standard = str(
                remote_current.get("evidence", {}).get("classification_standard") or ""
            )
            selected_rows = [
                row
                for row in remote_rows
                if str(row.get("evidence", {}).get("classification_standard") or "")
                == selected_standard
            ]
            if local_categories:
                if remote_category not in local_categories:
                    status = "conflict"
                    error_message = (
                        f"local={local_categories}; remote={remote_category}; "
                        f"standard={selected_standard}"
                    )
                    interval_count = 0
                else:
                    status = "completed_noop"
                    error_message = None
                    interval_count = 0
            else:
                interval_count = fact_store.upsert_intervals(selected_rows)
                writes += interval_count
                status = "completed"
                error_message = None
            fact_store.mark_sync_state(
                job_id,
                symbol,
                status=status,
                attempt_count=1,
                interval_count=interval_count,
                error_message=error_message,
                updated_at=_utc_now(),
            )
            items.append(
                {
                    "symbol": symbol,
                    "status": status,
                    "writes": interval_count,
                    "local_categories": local_categories,
                    "remote_category": remote_category,
                    "selected_standard": selected_standard,
                    "remote_rows": len(remote_rows),
                    "selected_rows": len(selected_rows),
                    "error": error_message,
                }
            )
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            fact_store.mark_sync_state(
                job_id,
                symbol,
                status="failed",
                attempt_count=1,
                error_message=message,
                updated_at=_utc_now(),
            )
            items.append(
                {
                    "symbol": symbol,
                    "status": "failed",
                    "writes": 0,
                    "error": message,
                }
            )

    status = (
        "passed"
        if all(item["status"] in {"completed", "completed_noop"} for item in items)
        else "failed"
    )
    summary = fact_store.sync_job_summary(job_id)
    _print_result(
        job_id=job_id,
        snapshot=snapshot,
        items=items,
        writes=writes,
        status=status,
        summary=summary,
    )
    raise SystemExit(0 if status == "passed" else 2)


def _validate_control_plane(control_store) -> dict[str, dict[str, Any]]:
    source = control_store.get_source("cninfo")
    if not source["enabled"] or source["verification_status"] != "verified":
        raise RuntimeError("CNINFO source is not enabled and verified")
    routes = {
        route["route_id"]: route
        for route in control_store.list_routes()
        if route["route_id"] in ROUTE_IDS
    }
    if set(routes) != set(ROUTE_IDS) or any(
        not route["enabled"]
        or route["fallback_policy"] != "fill_missing"
        or route["source_id"] != "cninfo"
        for route in routes.values()
    ):
        raise RuntimeError("CNINFO industry fill-missing routes are not enabled")
    return routes


def _probe(control_store, route_id: str, loader: Callable[[], list[dict[str, Any]]]):
    started = time.monotonic()
    try:
        result = list(loader())
    except Exception as error:
        control_store.record_route_probe(
            route_id,
            succeeded=False,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=f"{type(error).__name__}: {error}",
        )
        raise
    control_store.record_route_probe(
        route_id,
        succeeded=True,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return result


def _industry_contract(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    keys: set[tuple[str, str, str]] = set()
    for row in rows:
        standard = str(row.get("evidence", {}).get("classification_standard") or "")
        key = (standard, str(row.get("valid_from") or ""), str(row.get("category") or ""))
        if not all(key) or key in keys:
            return False
        keys.add(key)
        grouped[standard].append(row)
    for items in grouped.values():
        items.sort(key=lambda row: str(row["valid_from"]))
        for index, row in enumerate(items):
            if index + 1 == len(items):
                if row.get("valid_to") is not None:
                    return False
                continue
            next_from = str(items[index + 1]["valid_from"])
            expected = (date.fromisoformat(next_from) - timedelta(days=1)).isoformat()
            if row.get("valid_to") != expected or str(row["valid_from"]) >= next_from:
                return False
    return True


def _select_current(rows: list[dict[str, Any]], as_of: str) -> dict[str, Any] | None:
    active = [
        row
        for row in rows
        if str(row.get("valid_from") or "") <= as_of
        and (not row.get("valid_to") or str(row.get("valid_to")) >= as_of)
    ]
    if not active:
        return None
    return max(
        active,
        key=lambda row: (
            str(row.get("valid_from") or ""),
            -STANDARD_PRIORITIES.get(
                str(row.get("evidence", {}).get("classification_standard") or ""),
                99,
            ),
        ),
    )


def _print_result(*, job_id: str, snapshot: dict[str, Any], items: list[dict[str, Any]], writes: int, status: str, summary: dict[str, Any]) -> None:
    print(
        json.dumps(
            {
                "status": status,
                "mode": "controlled_fill_missing",
                "job_id": job_id,
                "route_snapshot_id": snapshot["snapshot_id"],
                "routes": [route["route_id"] for route in snapshot["routes"]],
                "writes": writes,
                "published": False,
                "items": items,
                "summary": summary,
            },
            ensure_ascii=False,
        )
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
