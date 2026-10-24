"""Deterministic stage-91 source effectiveness and quality remediation smoke test."""

from __future__ import annotations

import tempfile
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.api.data_center import build_data_center_routes
from app.services.data_center_service import DataCenterService
from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
from data_platform.storage.data_center_store import DataCenterStore


class _LocalProvider:
    def __init__(self) -> None:
        self.request_gate = None
        self.calls: list[tuple[str, str, str, str]] = []

    def sync_symbol(self, store, *, symbol: str, adjustment: str, start_date: str, end_date: str) -> dict:
        if self.request_gate:
            self.request_gate()
        self.calls.append((symbol, adjustment, start_date, end_date))
        written = store.upsert_daily_prices(
            [{"symbol": symbol, "date": end_date, "open": 10.0, "high": 10.5,
              "low": 9.5, "close": 10.2, "volume": 1000, "amount": 10200}],
            adjustment=adjustment, source="stage91-local-provider",
        )
        return {"status": "completed", "symbol": symbol, "adjustment": adjustment,
                "start_date": start_date, "end_date": end_date, "rows_received": 1,
                "rows_written": written}


def _seed_reference(governance: AShareGovernanceStore) -> None:
    governance.upsert_trade_calendar([{
        "market": "CN", "trade_date": "2026-01-05", "is_open": True,
        "source": "stage91-smoke", "source_observed_at": "2026-01-05T00:00:00+00:00",
    }])
    governance.upsert_index_prices([{
        "index_symbol": "000300", "trade_date": "2026-01-05", "open": 4000,
        "high": 4010, "low": 3990, "close": 4005, "volume": 1, "amount": 1,
        "source": "stage91-smoke", "source_observed_at": "2026-01-05T00:00:00+00:00",
    }])


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    workspace_temp = project_root / "tmp"
    workspace_temp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scq-stage91-", dir=workspace_temp) as temporary:
        database = Path(temporary) / "market.sqlite3"
        market, governance = AShareMarketStore(database), AShareGovernanceStore(database)
        market.ensure_schema()
        governance.ensure_schema()
        market.replace_current_symbols([
            {"symbol": "000001", "name": "valid", "source": "stage91-smoke"},
            {"symbol": "000002", "name": "invalid", "source": "stage91-smoke"},
        ])
        _seed_reference(governance)
        provider = _LocalProvider()
        scheduler = AShareSyncScheduler(
            database, market_store=market, governance_store=governance, provider=provider,
            requests_per_minute=1_000_000, max_workers=4, retry_count=3,
            base_backoff_seconds=0, sleep=lambda _seconds: None,
        )
        scheduler.ensure_schema()
        store = DataCenterStore(database)
        service = DataCenterService(store, scheduler, governance, sync_worker_launcher=lambda job_id: {"pid": 91})

        sources_before = store.list_sources()
        source_test = service.test_source("akshare", live=False)
        assert source_test["writes"] == 0
        assert source_test["tested_count"] == len(store.get_source("akshare")["capabilities"])
        assert len(service.list_source_probes(source_id="akshare")) == source_test["tested_count"]
        for sequence in range(25):
            store.record_source_probe({
                "probe_id": f"stage91-history-{sequence:02d}",
                "source_id": "akshare",
                "dataset_id": "a_share_daily",
                "endpoint_id": f"history-fixture-{sequence:02d}",
                "mode": "contract_only",
                "status": "passed",
                "latency_ms": sequence,
            })
        recent_probes = service.list_source_probes(source_id="akshare", limit=20)
        assert len(recent_probes) == 20
        assert [item["created_at"] for item in recent_probes] == sorted(
            (item["created_at"] for item in recent_probes), reverse=True,
        )
        assert recent_probes[0]["endpoint_id"] == "history-fixture-24"
        assert [item["enabled"] for item in store.list_sources()] == [item["enabled"] for item in sources_before]
        for source in store.list_sources():
            assert "secret_values" not in source
            assert all(set(item) == {"env_name", "status"} for item in source["credential_states"])

        route = next(item for item in store.list_routes() if item["dataset"] == "a_share_daily")
        store.update_source("akshare", {"requests_per_minute": 5, "concurrency": 2, "retry_count": 2})
        store.update_routes([{"route_id": route["route_id"], "requests_per_minute": 7,
                              "concurrency": 1, "retry_count": 2, "backoff_seconds": 0}])
        preview = service.preview_sync(dataset="a_share_daily", target_trade_date="2026-01-05",
                                       symbols=["000001"], all_current=False, adjustments=["raw"],
                                       mode="incremental")
        task = service.create_sync_task(
            dataset="a_share_daily", target_trade_date="2026-01-05", symbols=["000001"],
            all_current=False, adjustments=["raw"], run_now=False, mode="incremental",
            preview_token=preview["preview_token"],
            selected_shards=[item["shard_id"] for item in preview["tasks"]],
        )
        frozen = store.get_route_snapshot(task_id=str(task["job_id"]))
        assert frozen["effective_config"]["requests_per_minute"] == 5
        assert task["effective_config"]["requests_per_minute"] == 5
        store.update_source("akshare", {"requests_per_minute": 60, "concurrency": 4, "retry_count": 3})
        completed = scheduler.run_job(str(task["job_id"]))
        assert completed["status"] == "published"
        assert completed["actual_config"]["source"] == "frozen_task_snapshot"
        assert completed["actual_config"]["requests_per_minute"] == 5
        assert completed["actual_config"]["max_workers"] == 1

        market.upsert_daily_prices([{
            "symbol": "000002", "date": "2026-01-05", "open": 10.0, "high": 9.0,
            "low": 8.0, "close": 10.2, "volume": 1000, "amount": 10200,
        }], adjustment="raw", source="stage91-invalid-seed")
        scan = service.quality_scan_engine.create_scan(
            dataset="a_share_daily", date_from="2026-01-05", date_to="2026-01-05",
            scope="symbols", symbols=["000002"], adjustments=["raw"], rules=["ohlcv_validity"],
        )
        initial_scan = service.quality_scan_engine.run_scan(str(scan["scan_id"]))
        assert initial_scan["status"] == "issues_found"
        issue = store.list_issues(source_task_id=str(scan["scan_id"]))[0]
        previous_version = store.list_versions()['default_version_id']
        try:
            service.disposition_quality_issue(
                str(issue['issue_id']), action='correct', reason='invalid correction must roll back',
                operator='stage91-smoke', before={'high': 9.0}, after={'high': 8.5},
            )
        except ValueError:
            pass
        else:
            raise AssertionError('invalid correction unexpectedly activated')
        assert store.list_versions()['default_version_id'] == previous_version
        assert store.get_issue_history(str(issue['issue_id']))['overlays'] == []
        corrected = service.disposition_quality_issue(
            str(issue["issue_id"]), action="correct", reason="stage91 deterministic correction",
            operator="stage91-smoke", before={"high": 9.0}, after={"high": 10.5},
        )
        assert corrected["status"] == "corrected" and corrected["automatically_effective"]
        history = store.get_issue_history(str(issue["issue_id"]))
        assert history["overlays"][0]["status"] == "published"
        assert history["remediations"][0]["status"] == "corrected"
        rechecked = service.quality_scan_engine.get_scan(corrected["verification_scan_id"])
        assert rechecked["status"] == "passed"
        closed = store.get_issue(str(issue["issue_id"]))
        assert closed["status"] == "corrected" and closed["workflow_status"] == "corrected"
        assert store.release_readiness()["status"] == "ready"
        assert market.fetch_price_history(
            "000002", "2026-01-05", "2026-01-05", adjustment="raw",
        )[0]["high"] == 10.5
        assert store.list_versions()["default_version_id"] == corrected["data_version_id"]
        with closing(sqlite3.connect(database)) as connection:
            report = connection.execute('SELECT q.payload_json FROM data_quality_reports q JOIN data_versions v '
                                        'ON v.quality_report_id=q.quality_report_id WHERE v.data_version_id=?',
                                        (corrected['data_version_id'],)).fetchone()
        assert json.loads(report[0])['verification_scan_id'] == corrected['verification_scan_id']
        assert market.fetch_price_history("000002", "2026-01-05", "2026-01-05", adjustment="raw")[0]["high"] == 10.5

        paths = {route.path for route in build_data_center_routes(service)}
        assert "/api/data-center/source-probes" in paths
        assert "/api/data-center/versions/release-readiness" in paths
        assert "/api/data-center/quality/issues/{issue_id}/publish-overlay" in paths
        html = (project_root / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (project_root / "web" / "data_center_stage_c.js").read_text(encoding="utf-8")
        styles = (project_root / "web" / "data_center.css").read_text(encoding="utf-8")
        vtable = (project_root / "web" / "vtable-adapter.js").read_text(encoding="utf-8")
        assert "dc-source-workspace" in html and "dc-source-probe-history" in html
        assert "dc-source-dialog" in html and "dc-release-readiness" in html
        assert "可获数据类别" in javascript and "data-source-edit" in javascript
        assert "data-source-test" in javascript and "source-probes?source_id=" in javascript
        assert "&limit=20" in javascript and 'live:true' in javascript
        assert "config-market-provider-panel" not in html
        assert ".dc-source-workspace" in styles and "vtableRowAction" in vtable
        assert "route_snapshot?.effective_config" in javascript and "actual_config" in javascript
        assert "dc-publish-overlay" in javascript

    print("[stage91] source effectiveness and remediation smoke passed")


if __name__ == "__main__":
    main()
