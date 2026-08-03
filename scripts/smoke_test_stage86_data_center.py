"""Deterministic stage-86 data-center service and HTTP contract smoke test."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.api.data_center import build_data_center_routes
from app.main import SimpleApiApp
from app.runtime.http_adapter import dispatch_request
from app.services.data_center_service import DataCenterService
from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
from data_platform.storage.data_center_store import DataCenterStore


class _NoWriteProvider:
    def sync_symbol(self, *_args, **_kwargs):
        raise AssertionError("stage-86 smoke must not call an upstream provider")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-stage86-") as temporary:
        database_path = Path(temporary) / "market.sqlite3"
        market = AShareMarketStore(database_path)
        governance = AShareGovernanceStore(database_path)
        scheduler = AShareSyncScheduler(
            database_path,
            market_store=market,
            governance_store=governance,
            provider=_NoWriteProvider(),
            requests_per_minute=60,
            max_workers=1,
            retry_count=1,
        )
        scheduler.ensure_schema()
        store = DataCenterStore(database_path)
        launched_jobs = []
        service = DataCenterService(
            store,
            scheduler,
            governance,
            sync_worker_launcher=lambda job_id: launched_jobs.append(job_id) or {"pid": 86},
        )
        app = SimpleApiApp(
            title="stage86-smoke", routes=build_data_center_routes(service)
        )

        def create_previewed_task(symbol: str) -> dict:
            preview = service.preview_sync(
                dataset="a_share_daily", target_trade_date="2026-07-24",
                symbols=[symbol], all_current=False, adjustments=["raw"],
                mode="incremental",
            )
            return service.create_sync_task(
                dataset="a_share_daily", target_trade_date="2026-07-24",
                symbols=[symbol], all_current=False, adjustments=["raw"],
                run_now=False, mode="incremental",
                preview_token=preview["preview_token"],
                selected_shards=[item["shard_id"] for item in preview["tasks"]],
            )

        status, payload = dispatch_request(
            app, method="GET", path="/api/data-center/overview"
        )
        assert status == 200
        assert payload["result"]["usage_boundary"] == "noncommercial_local_research"
        assert payload["result"]["route_count"] >= 8

        before_jobs = scheduler.list_jobs()
        status, preview = dispatch_request(
            app,
            method="POST",
            path="/api/data-center/sync/preview",
            body=json.dumps(
                {
                    "target_trade_date": "2026-07-24",
                    "symbols": ["000001.XSHE"],
                    "adjustments": ["raw"],
                    "mode": "incremental",
                }
            ).encode("utf-8"),
        )
        assert status == 200
        assert preview["result"]["status"] == "previewed"
        assert preview["result"]["writes"] == 0
        assert scheduler.list_jobs() == before_jobs
        assert preview["result"]["preview_token"].startswith("dcp-")
        assert preview["result"]["route_summary"][0]["source_id"] == "akshare"
        status, sources = dispatch_request(app, method="GET", path="/api/data-center/sources")
        assert status == 200 and any(item["verification_status"] == "candidate" for item in sources["items"])
        expected_source_ids = {
            "akshare", "baostock", "mootdx", "tencent_finance", "iwencai",
            "eastmoney_reportapi", "akshare_ths", "cninfo", "a_stock_data",
        }
        assert {item["source_id"] for item in sources["items"]} == expected_source_ids
        assert [item["source_id"] for item in sources["items"] if item["enabled"]] == [
            "akshare", "akshare_ths", "cninfo",
        ]
        cninfo_source = next(item for item in sources["items"] if item["source_id"] == "cninfo")
        assert {
            item["endpoint_id"] for item in cninfo_source["capabilities"] if item["enabled"]
        } == {
            "stock_industry_category_cninfo",
            "stock_industry_change_cninfo",
        }
        cninfo_routes = {
            item["route_id"]: item for item in store.list_routes()
            if item["route_id"].startswith("cninfo-")
        }
        assert {route_id for route_id, item in cninfo_routes.items() if item["enabled"]} == {
            "cninfo-industry-category",
            "cninfo-industry-change",
        }
        assert not cninfo_routes["cninfo-announcement-search"]["enabled"]
        assert not cninfo_routes["cninfo-share-change"]["enabled"]
        assert all(
            not capability["enabled"]
            for item in sources["items"]
            if item["verification_status"] != "verified"
            for capability in item["capabilities"]
        )
        ths_routes = {
            item["route_id"]: item for item in store.list_routes()
            if item["route_id"].endswith("-ths")
        }
        assert set(ths_routes) == {
            "industry-board-history-ths", "concept-board-history-ths", "concept-catalog-ths",
        }
        assert all(item["enabled"] for item in ths_routes.values())
        assert all(item["source_id"] == "akshare_ths" for item in ths_routes.values())
        assert ths_routes["industry-board-history-ths"]["fallback_policy"] == "on_failure"
        assert ths_routes["concept-board-history-ths"]["fallback_policy"] == "on_failure"
        assert ths_routes["concept-catalog-ths"]["fallback_policy"] == "primary"
        concept_snapshot = store.freeze_route_snapshot("concept_board", task_id="stage86-ths-route-smoke")
        assert [item["route_id"] for item in concept_snapshot["routes"]] == [
            "concept-board-history", "concept-board-history-ths",
        ]
        status, datasets = dispatch_request(app, method="GET", path="/api/data-center/datasets")
        assert status == 200 and {item["layer_id"] for item in datasets["items"]} == {f"L{i}" for i in range(1, 8)}
        dataset_map = {item["dataset_id"]: item for item in datasets["items"]}
        route_dataset_ids = {item["dataset"] for item in store.list_routes()}
        assert route_dataset_ids <= set(dataset_map)
        assert all(
            not item["route_required"] or item["dataset_id"] in route_dataset_ids
            for item in dataset_map.values()
        )
        assert dataset_map["global_index_daily"]["availability_status"] == "disabled"
        assert dataset_map["global_index_daily"]["route_required"]
        assert dataset_map["research_reports"]["producer_type"] == "disabled_candidate"
        assert not dataset_map["research_reports"]["route_required"]
        assert {
            dataset_id: (dataset_map[dataset_id]["producer_type"], dataset_map[dataset_id]["producer_id"])
            for dataset_id in ("trading_status", "quality_issues", "data_versions")
        } == {
            "trading_status": ("internal_pipeline", "a_share_sync_scheduler"),
            "quality_issues": ("internal_control_plane", "data_quality_engine"),
            "data_versions": ("internal_control_plane", "a_share_governance_store"),
        }
        assert all(
            not dataset_map[dataset_id]["route_required"]
            for dataset_id in ("trading_status", "quality_issues", "data_versions")
        )

        status, routes = dispatch_request(
            app,
            method="PUT",
            path="/api/data-center/routes",
            body=json.dumps(
                {
                    "routes": [
                        {
                            "route_id": "a-share-daily",
                            "requests_per_minute": 55,
                            "concurrency": 3,
                        }
                    ]
                }
            ).encode("utf-8"),
        )
        assert status == 200
        selected = next(
            item for item in routes["items"] if item["route_id"] == "a-share-daily"
        )
        assert selected["requests_per_minute"] == 55
        assert selected["concurrency"] == 3

        background_job = create_previewed_task("600000.XSHG")
        dispatched = service.run_sync_task(background_job["job_id"])
        assert dispatched["execution"]["mode"] == "background_process"
        assert dispatched["execution"]["status"] == "dispatched"
        assert launched_jobs == [background_job["job_id"]]
        interrupted = scheduler.mark_job_interrupted(
            background_job["job_id"], error="worker_exit_fixture"
        )
        assert interrupted["status"] == "interrupted"
        assert interrupted["last_error"] == "worker_exit_fixture"

        job = create_previewed_task("000001.XSHE")
        stopped = service.stop_sync_task(job["job_id"])
        assert stopped["status"] == "stopped"
        assert all(item["status"] == "stopped" for item in stopped["items"])

        issue = store.create_issue(
            {
                "dataset": "a_share_daily",
                "symbol": "000001.XSHE",
                "observation_at": "2026-07-24",
                "rule_id": "positive-price",
                "severity": "error",
                "source": "stage86-smoke",
                "source_task_id": background_job["job_id"],
                "field_name": "close",
                "evidence": {"close": -1, "adjustment": "raw"},
            }
        )
        corrected = service.disposition_quality_issue(
            issue["issue_id"],
            action="correct",
            reason="fixture correction",
            operator="qa-lead",
            before={"close": -1},
            after={"close": 1},
        )
        assert corrected["status"] == "corrected"
        history = service.get_quality_issue_history(issue["issue_id"])
        assert history["dispositions"][0]["reason"] == "fixture correction"
        exported = service.export_quality_issues(source_task_id=background_job["job_id"])
        assert exported["row_count"] == 1 and "issue_id" in exported["content"]

        governance.save_quality_report(
            quality_report_id="stage86-smoke-quality",
            rule_version="86.1",
            status="passed",
            payload={"status": "passed"},
        )
        version = governance.publish_data_version(
            as_of_trade_date="2026-07-24",
            quality_report_id="stage86-smoke-quality",
            members=[
                {
                    "dataset": "market_daily_prices",
                    "adjustment": "raw",
                    "symbol_scope": "fixture",
                    "row_count": 1,
                    "symbol_count": 1,
                    "min_date": "2026-07-24",
                    "max_date": "2026-07-24",
                    "source": "stage86-smoke",
                    "quality_status": "passed",
                }
            ],
        )
        versions_before_default = service.list_versions()
        assert versions_before_default["default_version_id"] is None
        assert versions_before_default["latest_published_version_id"] == version["data_version_id"]
        default = service.set_default_version(version["data_version_id"])
        assert default["default_version_id"] == version["data_version_id"]
        assert service.list_assets()["version_id"] == version["data_version_id"]
        store.update_routes([
            {"route_id": "cninfo-industry-category", "enabled": False},
            {"route_id": "cninfo-industry-change", "enabled": False},
        ])
        store.update_source("cninfo", {"enabled": False})
        store.ensure_schema()
        assert not store.get_source("cninfo")["enabled"]
        assert not any(
            item["enabled"]
            for item in store.list_routes()
            if item["route_id"] in {
                "cninfo-industry-category", "cninfo-industry-change",
            }
        )

    print("stage86 data-center smoke passed")


if __name__ == "__main__":
    main()
