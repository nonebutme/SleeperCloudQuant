"""Isolated acceptance for governed closure of stale trading-status issues."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.data_center import build_data_center_routes
from app.services.data_center_service import (
    DataCenterService,
    TRADING_STATUS_ISSUE_RECONCILIATION_CONFIRMATION,
)
from data_platform.a_share_sync_scheduler import AShareSyncScheduler
from data_platform.quality_scan_engine import QualityScanEngine
from data_platform.storage.a_share_governance_store import AShareGovernanceStore
from data_platform.storage.a_share_market_store import AShareMarketStore
from data_platform.storage.data_center_store import DataCenterStore


def _expect_value_error(callable_object) -> None:
    try:
        callable_object()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def main() -> None:
    test_root = PROJECT_ROOT / "tmp"
    test_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="scq-status-issue-reconciliation-", dir=test_root,
    ) as tmp:
        root = Path(tmp)
        database = root / "market.sqlite3"
        task_dir = root / "status-tasks"
        market = AShareMarketStore(database)
        governance = AShareGovernanceStore(database)
        store = DataCenterStore(database)
        market.ensure_schema()
        governance.ensure_schema()
        store.ensure_schema()
        market.upsert_symbols([
            {"symbol": "000001", "name": "fixture-a", "listing_status": "current"},
            {"symbol": "000002", "name": "fixture-b", "listing_status": "current"},
        ])
        for adjustment in ("raw", "qfq", "hfq"):
            market.upsert_daily_prices(
                [
                    {
                        "symbol": symbol, "trade_date": "2025-01-02",
                        "open": 10, "high": 11, "low": 9, "close": 10,
                        "volume": 100, "amount": 1_000,
                    }
                    for symbol in ("000001", "000002")
                ],
                adjustment=adjustment,
                source="isolated-fixture",
            )
        governance.upsert_trading_statuses([
            {
                "symbol": symbol, "trade_date": "2025-01-02",
                "status": "normal", "is_tradable": True,
                "source": "isolated-fixture",
            }
            for symbol in ("000001", "000002")
        ])
        for index, symbol in enumerate(("000001", "000002"), start=1):
            store.create_issue({
                "issue_id": f"dqi-stale-status-{index}",
                "dataset": "trading_status", "symbol": symbol,
                "observation_at": "2025-01-02",
                "rule_id": "trading_status_semantics", "severity": "error",
                "status": "open", "source": "quality_scan_engine",
                "source_task_id": "old-status-scan",
                "field_name": "is_tradable,volume",
                "evidence": {"issue_type": "suspended_with_positive_volume"},
                "workflow_status": "open", "block_release": True,
            })

        scheduler = AShareSyncScheduler(database, provider=object())
        engine = QualityScanEngine(database, scheduler)
        scan = engine.create_scan(
            dataset="a_share_daily", date_from="2025-01-02",
            date_to="2025-01-02", scope="symbols",
            symbols=["000001", "000002"], adjustments=["raw", "qfq", "hfq"],
            rules=["trading_status_semantics"],
        )
        scan = engine.run_scan(str(scan["scan_id"]))
        assert scan["status"] == "passed" and scan["issues_found"] == 0

        preview = store.preview_trading_status_issue_reconciliation()
        assert preview["status"] == "ready", preview
        assert preview["issue_count"] == preview["closable_count"] == 2
        assert preview["blocking_count"] == 0
        assert preview["scan_id"] == scan["scan_id"]
        assert len(preview["issue_set_hash"]) == 64

        _expect_value_error(lambda: store.reconcile_trading_status_issues(
            scan_id=scan["scan_id"], expected_issue_set_hash="0" * 64,
            operator="qa-admin", reason="isolated mismatch",
        ))
        assert store.summarize_issues(rule_id="trading_status_semantics")[
            "status_counts"
        ]["open"] == 2

        governance.upsert_trading_statuses([{
            "symbol": "000002", "trade_date": "2025-01-02",
            "status": "suspended", "is_tradable": False,
            "source": "isolated-drift",
        }])
        drift = store.preview_trading_status_issue_reconciliation(
            scan_id=scan["scan_id"]
        )
        assert drift["status"] == "blocked"
        assert drift["closable_count"] == 1 and drift["blocking_count"] == 1
        _expect_value_error(lambda: store.reconcile_trading_status_issues(
            scan_id=scan["scan_id"],
            expected_issue_set_hash=preview["issue_set_hash"],
            operator="qa-admin", reason="stale preview must fail",
        ))
        governance.upsert_trading_statuses([{
            "symbol": "000002", "trade_date": "2025-01-02",
            "status": "normal", "is_tradable": True,
            "source": "isolated-restored",
        }])
        preview = store.preview_trading_status_issue_reconciliation(
            scan_id=scan["scan_id"]
        )
        before_status = governance.fetch_trading_status_history(
            "000001", "2025-01-02", "2025-01-02"
        ) + governance.fetch_trading_status_history(
            "000002", "2025-01-02", "2025-01-02"
        )

        service = DataCenterService(
            store, scheduler, governance,
            trading_status_remediation_dir=task_dir,
        )
        route_paths = {route.path for route in build_data_center_routes(service)}
        assert (
            "/api/data-center/quality/trading-status-remediation/closure/"
            "reconcile-issues"
        ) in route_paths
        _expect_value_error(lambda: service.reconcile_trading_status_quality_issues(
            scan_id=scan["scan_id"],
            expected_issue_set_hash=preview["issue_set_hash"],
            operator="qa-admin", reason="isolated physical recheck passed",
            confirmation="WRONG",
        ))
        result = service.reconcile_trading_status_quality_issues(
            scan_id=scan["scan_id"],
            expected_issue_set_hash=preview["issue_set_hash"],
            operator="qa-admin", reason="isolated physical recheck passed",
            confirmation=TRADING_STATUS_ISSUE_RECONCILIATION_CONFIRMATION,
        )
        assert result["issue_reconciliation_result"]["closed_count"] == 2
        assert result["issue_reconciliation"]["status"] == "no_changes"
        after_status = governance.fetch_trading_status_history(
            "000001", "2025-01-02", "2025-01-02"
        ) + governance.fetch_trading_status_history(
            "000002", "2025-01-02", "2025-01-02"
        )
        assert before_status == after_status, "issue closure changed physical status facts"
        for issue_id in ("dqi-stale-status-1", "dqi-stale-status-2"):
            issue = store.get_issue(issue_id)
            assert issue["status"] == issue["workflow_status"] == "corrected"
            assert not issue["block_release"]
            history = store.get_issue_history(issue_id)
            assert history["dispositions"][-1]["action"] == "correct"
            assert history["dispositions"][-1]["related_task_id"] == scan["scan_id"]
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM data_correction_overlays"
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM data_quality_remediations"
            ).fetchone()[0] == 0

    print("trading status issue reconciliation smoke passed")


if __name__ == "__main__":
    main()
