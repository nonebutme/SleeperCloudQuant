"""Run an isolated live audit for global-index config, probes and downloads."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.data_center_service import DataCenterService
from app.services.market_panorama_service import MarketPanoramaService
from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
from data_platform.providers.akshare_governance_provider import AkshareGovernanceProvider
from data_platform.storage.data_center_store import DataCenterStore
from data_platform.storage.market_panorama_store import MarketPanoramaStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-global-index-live-") as temporary:
        root = Path(temporary)
        market_database = root / "market.sqlite3"
        provider = AkshareGovernanceProvider(retry_count=1)
        market_store = AShareMarketStore(market_database)
        governance_store = AShareGovernanceStore(market_database)
        scheduler = AShareSyncScheduler(
            market_database,
            market_store=market_store,
            governance_store=governance_store,
            provider=provider,
            requests_per_minute=60,
            max_workers=1,
            retry_count=1,
        )
        scheduler.ensure_schema()
        panorama = MarketPanoramaService(
            MarketPanoramaStore(root / "panorama.sqlite3"),
            market_database=market_database,
            classification_database=root / "classification.sqlite3",
            max_workers=1,
        )
        panorama.governance_provider = provider
        store = DataCenterStore(market_database)
        service = DataCenterService(
            store, scheduler, governance_store, panorama_service=panorama,
        )

        dataset = next(
            item for item in service.list_datasets()
            if item["dataset_id"] == "global_index_daily"
        )
        routes = {
            item["route_id"]: item for item in service.list_routes()
            if item["dataset"] == "global_index_daily"
        }
        probes = {
            route_id: service.test_route(route_id, live=True)
            for route_id in (
                "global-index-us-sina",
                "global-index-international-sina",
            )
        }
        preview = service.preview_sync(
            dataset="global_index_daily",
            start_trade_date="2026-10-08",
            target_trade_date="2026-10-09",
            symbols=[], all_current=False, adjustments=[],
            mode="historical_gap", selected_shards=["SPX", "N225"],
        )
        task = service.create_sync_task(
            dataset="global_index_daily",
            start_trade_date="2026-10-08",
            target_trade_date="2026-10-09",
            symbols=[], all_current=False, adjustments=[], run_now=False,
            mode="historical_gap", preview_token=preview["preview_token"],
            selected_shards=["SPX", "N225"],
        )
        snapshot = store.get_route_snapshot(task_id=task["job_id"])
        result = panorama.run_job(
            task["job_id"], routes=list((snapshot or {}).get("routes") or []),
        )
        post_download_preview = panorama.preview_job(
            datasets=["global_index_daily"],
            start_trade_date="2026-10-08",
            target_trade_date="2026-10-09",
            mode="historical_gap", selected_shards=["SPX", "N225"],
        )
        with closing(sqlite3.connect(market_database)) as connection:
            downloaded = [
                {"index_symbol": row[0], "row_count": int(row[1]),
                 "min_date": row[2], "max_date": row[3]}
                for row in connection.execute(
                    """
                    SELECT index_symbol, COUNT(*), MIN(trade_date), MAX(trade_date)
                    FROM market_index_daily_prices
                    WHERE index_symbol IN ('SPX', 'N225')
                    GROUP BY index_symbol ORDER BY index_symbol
                    """
                ).fetchall()
            ]

        payload = {
            "audit_status": "passed",
            "dataset": dataset,
            "routes": routes,
            "probes": probes,
            "preview": {
                "status": preview["status"],
                "writes": preview["writes"],
                "coverage_strategy": preview["coverage_strategy"],
                "shards": preview["shards"],
            },
            "task": {
                "job_id": result["job_id"],
                "status": result["status"],
                "completed_items": result["completed_items"],
                "failed_items": result["failed_items"],
                "rows_written": result["rows_written"],
                "release_status": result["global_index_release"]["status"],
                "quality_rule_version": result["global_index_release"][
                    "quality_rule_version"
                ],
                "history_conflict_rows": result["global_index_release"][
                    "conflict_rows"
                ],
            },
            "post_download_preview": {
                "coverage_strategy": post_download_preview["coverage_strategy"],
                "request_count": post_download_preview["request_count"],
            },
            "downloaded": downloaded,
            "business_database_writes": 0,
        }
        assert dataset["route_status"] == "ready" and dataset["sync_enabled"]
        assert all(item["status"] == "passed" for item in probes.values())
        assert result["status"] == "published" and result["failed_items"] == 0
        assert result["global_index_release"]["status"] == "published"
        assert result["global_index_release"]["conflict_rows"] == 0
        assert post_download_preview["coverage_strategy"] == "market_session_gap"
        assert post_download_preview["request_count"] == 0
        assert {
            (item["index_symbol"], item["row_count"], item["min_date"], item["max_date"])
            for item in downloaded
        } == {
            ("N225", 2, "2026-10-08", "2026-10-09"),
            ("SPX", 2, "2026-10-08", "2026-10-09"),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
