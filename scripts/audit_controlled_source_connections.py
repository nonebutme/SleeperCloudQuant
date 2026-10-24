"""Run every controlled-source connection test and report zero-write evidence."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.data_center_service import DataCenterService
from app.services.market_panorama_service import MarketPanoramaService
from data_platform.providers.akshare_governance_provider import AkshareGovernanceProvider
from data_platform.storage.data_center_store import DataCenterStore
from data_platform.storage.market_panorama_store import MarketPanoramaStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKET_DATABASE = PROJECT_ROOT / "var" / "market" / "a_share_market.sqlite3"
PANORAMA_DATABASE = PROJECT_ROOT / "var" / "runtime" / "market_panorama.sqlite3"
CLASSIFICATION_DATABASE = (
    PROJECT_ROOT / "var" / "runtime" / "a_share_classification_history.sqlite3"
)
BUSINESS_TABLES = (
    "market_daily_prices",
    "market_symbols",
    "market_trade_calendar",
    "market_index_daily_prices",
    "corporate_action_events",
    "index_component_intervals",
    "data_versions",
    "market_incremental_sync_jobs",
)


def _business_counts() -> dict[str, int]:
    uri = f"file:{MARKET_DATABASE.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in BUSINESS_TABLES
        }


def _summary(result: dict) -> dict:
    return {
        "source_id": result["source_id"],
        "status": result["status"],
        "tested_count": result["tested_count"],
        "active_tested_count": result["active_tested_count"],
        "skipped_count": result["skipped_count"],
        "items": [
            {
                "dataset_id": item["dataset_id"],
                "endpoint_id": item["endpoint_id"],
                "status": item["status"],
                "error_code": item.get("error_code"),
                "latency_ms": item.get("latency_ms", 0),
                "sample_rows": item.get("sample_rows", 0),
                "message": (item.get("evidence") or {}).get("message"),
            }
            for item in result["items"]
        ],
    }


def main() -> None:
    before = _business_counts()
    store = DataCenterStore(MARKET_DATABASE)
    provider = AkshareGovernanceProvider(retry_count=2)
    panorama = MarketPanoramaService(
        MarketPanoramaStore(PANORAMA_DATABASE),
        market_database=MARKET_DATABASE,
        classification_database=CLASSIFICATION_DATABASE,
        max_workers=1,
    )
    service = object.__new__(DataCenterService)
    service.store = store
    service.scheduler = SimpleNamespace(governance_provider=provider)
    service.panorama_service = panorama

    results = []
    for source in store.list_sources():
        source_id = str(source["source_id"])
        print(f"[source-audit] testing {source_id}", flush=True)
        result = _summary(service.test_source(source_id, live=True))
        results.append(result)
        print(
            f"[source-audit] {source_id}: {result['status']} "
            f"({result['active_tested_count']} active, {result['skipped_count']} skipped)",
            flush=True,
        )

    after = _business_counts()
    report = {
        "status": "passed" if before == after else "business_data_changed",
        "writes": 0 if before == after else None,
        "business_counts_before": before,
        "business_counts_after": after,
        "business_counts_unchanged": before == after,
        "sources": results,
    }
    print("SCQ_SOURCE_AUDIT=" + json.dumps(report, ensure_ascii=False, default=str))
    if before != after:
        raise SystemExit("business table counts changed during connection audit")


if __name__ == "__main__":
    main()
