"""Deterministic Stage-C quality-loop service and HTTP contract smoke test."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.api.data_center import build_data_center_routes
from app.main import SimpleApiApp
from app.runtime.http_adapter import DispatchError, dispatch_request
from app.services.data_center_service import DataCenterService
from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
from data_platform.storage.data_center_store import DataCenterStore


class _NoWriteProvider:
    def sync_symbol(self, *_args, **_kwargs):
        raise AssertionError("Stage-C smoke must not call an upstream provider")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-stage-c-") as temporary:
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
        service = DataCenterService(store, scheduler, governance)
        app = SimpleApiApp(title="stage-c-quality", routes=build_data_center_routes(service))
        status, payload = dispatch_request(
            app, method="GET", path="/api/data-center/quality/rules",
        )
        assert status == 200 and len(payload["items"]) == 4
        assert "trading_status_semantics" in {
            item["rule_id"] for item in payload["items"]
        }
        status, payload = dispatch_request(
            app, method="POST", path="/api/data-center/quality/scans",
            body=json.dumps({
                "dataset": "a_share_daily",
                "date_from": "2026-07-21", "date_to": "2026-07-24",
                "scope": "symbols", "symbols": ["000001.XSHE"],
                "adjustments": ["raw"], "rules": ["ohlcv_validity"],
                "run_now": False,
            }).encode("utf-8"),
        )
        scan_id = payload["result"]["scan_id"]
        status, payload = dispatch_request(
            app, method="POST",
            path=f"/api/data-center/quality/scans/{scan_id}/run",
        )
        assert status == 200 and payload["result"]["execution"]["status"] == "dispatched"
        for _ in range(500):
            scan = service.get_quality_scan(scan_id)
            if scan["status"] in {"passed", "issues_found", "failed"}:
                break
            time.sleep(0.02)
        assert scan["status"] == "passed", scan
        status, payload = dispatch_request(
            app, method="GET", path="/api/data-center/quality/scans",
        )
        assert status == 200 and payload["items"][0]["scan_id"] == scan_id

        connection = sqlite3.connect(database_path)
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(data_quality_refetches)")}
        finally:
            connection.close()
        assert {"completed_at", "last_error", "related_issue_id"} <= columns

        def issue(symbol: str, day: str, rule: str = "price-positive") -> dict:
            return store.create_issue({
                "dataset": "a_share_daily",
                "symbol": symbol,
                "observation_at": day,
                "rule_id": rule,
                "severity": "error",
                "source": "stage-c-smoke",
                "field_name": "close",
                "evidence": {"close": -1, "adjustment": "raw"},
            })

        first = issue("000001.XSHE", "2026-07-23")
        second = issue("000002.XSHE", "2026-07-24")
        other_rule = issue("000003.XSHE", "2026-07-25", "volume-nonnegative")
        filtered = service.list_quality_issues(
            status="open,quarantined", severity="error",
            date_from="2026-07-24", date_to="2026-07-25",
        )
        assert {item["issue_id"] for item in filtered} == {second["issue_id"], other_rule["issue_id"]}
        summary = service.summarize_quality_issues(severity="error")
        assert summary["total"] == 3 and summary["status_counts"]["open"] == 3

        status, payload = dispatch_request(
            app, method="GET", path="/api/data-center/quality/summary",
            query_string="severity=error&date_from=2026-07-23&date_to=2026-07-24",
        )
        assert status == 200 and payload["result"]["total"] == 2
        status, payload = dispatch_request(
            app, method="POST", path="/api/data-center/quality/issues/bulk/disposition",
            body=json.dumps({
                "issue_ids": [first["issue_id"], second["issue_id"]],
                "action": "accept",
                "reason": "same rule fixture acceptance",
                "operator": "qa-lead",
            }).encode("utf-8"),
        )
        assert status == 200 and payload["result"]["processed_count"] == 2
        assert store.get_issue(first["issue_id"])["status"] == "accepted"
        assert store.get_issue(second["issue_id"])["status"] == "accepted"

        cross_a = issue("000004.XSHE", "2026-07-24")
        cross_b = issue("000005.XSHE", "2026-07-24", "volume-nonnegative")
        try:
            dispatch_request(
                app, method="POST", path="/api/data-center/quality/issues/bulk/disposition",
                body=json.dumps({
                    "issue_ids": [cross_a["issue_id"], cross_b["issue_id"]],
                    "action": "reject", "reason": "must be rejected atomically",
                }).encode("utf-8"),
            )
            raise AssertionError("cross-rule bulk disposition must be rejected")
        except DispatchError as exc:
            assert exc.status_code == 400 and "cannot mix" in exc.message
        assert store.get_issue(cross_a["issue_id"])["status"] == "open"
        assert store.get_issue(cross_b["issue_id"])["status"] == "open"

        refetch_a = issue("000006.XSHE", "2026-07-24", "refetch-fixture")
        refetch_b = issue("000007.XSHE", "2026-07-24", "refetch-fixture")
        status, payload = dispatch_request(
            app, method="POST", path="/api/data-center/quality/issues/bulk/refetch",
            body=json.dumps({
                "issue_ids": [refetch_a["issue_id"], refetch_b["issue_id"]],
                "reason": "controlled refetch fixture",
                "operator": "qa-lead", "run_now": False,
            }).encode("utf-8"),
        )
        assert status == 200 and payload["result"]["processed_count"] == 2
        assert all(item["status"] == "quarantined" for item in (
            store.get_issue(refetch_a["issue_id"]), store.get_issue(refetch_b["issue_id"])
        ))
        tasks = [item["task_id"] for item in payload["result"]["items"]]
        for task_id in tasks:
            assert scheduler.get_job(task_id)["status"] == "queued"
            scheduler.stop_job(task_id)
        history = service.get_quality_issue_history(refetch_a["issue_id"])
        assert history["refetches"][0]["status"] == "stopped"
        assert history["refetches"][0]["completed_at"]
        completed_at = history["refetches"][0]["completed_at"]
        assert service.get_quality_issue_history(refetch_a["issue_id"])["refetches"][0]["completed_at"] == completed_at

        status, payload = dispatch_request(
            app, method="GET", path="/api/data-center/quality/issues",
            query_string="status=accepted%2Cquarantined&date_from=2026-07-23&date_to=2026-07-24",
        )
        assert status == 200 and len(payload["items"]) == 4

    print("Stage-C data-center quality smoke passed")


if __name__ == "__main__":
    main()
