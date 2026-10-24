"""Deterministic active quality-discovery and recheck smoke test."""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
from data_platform.quality_scan_engine import QualityScanEngine
from data_platform.storage.data_center_store import DataCenterStore


class _NoWriteProvider:
    def sync_symbol(self, *_args, **_kwargs):
        raise AssertionError("quality scan smoke must not call an upstream provider")


def _price(symbol: str, trade_date: str) -> dict[str, object]:
    return {
        "symbol": symbol, "trade_date": trade_date,
        "open": 10, "high": 11, "low": 9, "close": 10,
        "volume": 100, "amount": 1000,
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-quality-scan-") as temporary:
        database = Path(temporary) / "market.sqlite3"
        market = AShareMarketStore(database)
        governance = AShareGovernanceStore(database)
        control = DataCenterStore(database)
        control.ensure_schema()
        scheduler = AShareSyncScheduler(
            database, market_store=market, governance_store=governance,
            provider=_NoWriteProvider(), requests_per_minute=60,
            max_workers=1, retry_count=1,
        )
        scheduler.ensure_schema()
        market.replace_current_symbols([
            {"symbol": "000001", "name": "fixture", "source": "smoke"},
        ])
        governance.upsert_trade_calendar([
            {"market": "CN", "trade_date": day, "is_open": True, "source": "smoke"}
            for day in ("2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24")
        ])
        governance.upsert_lifecycle_events([{
            "symbol": "000001", "event_type": "listed",
            "effective_from": "2026-07-21", "source": "smoke",
        }])
        market.upsert_daily_prices([
            _price("000001", day) for day in ("2026-07-21", "2026-07-23", "2026-07-24")
        ], adjustment="raw", source="smoke")
        market.upsert_daily_prices([
            _price("000001", day) for day in ("2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24")
        ], adjustment="qfq", source="smoke")
        market.upsert_daily_prices([
            _price("000001", day) for day in ("2026-07-21", "2026-07-22", "2026-07-23")
        ], adjustment="hfq", source="smoke")
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                """
                UPDATE market_daily_prices SET high=8
                WHERE symbol='000001' AND trade_date='2026-07-23' AND adjustment='qfq'
                """
            )

        engine = QualityScanEngine(database, scheduler)
        scan = engine.create_scan(
            dataset="a_share_daily", date_from="2026-07-21", date_to="2026-07-24",
            scope="symbols", symbols=["000001.XSHE"],
            adjustments=["raw", "qfq", "hfq"],
            rules=["missing_open_day", "ohlcv_validity", "adjustment_date_consistency"],
        )
        completed = engine.run_scan(scan["scan_id"])
        assert completed["status"] == "issues_found"
        assert completed["completed_rules"] == 3
        issues = control.list_issues(source_task_id=scan["scan_id"], limit=100)
        assert completed["issues_found"] == 6, (completed, issues)
        assert {issue["rule_id"] for issue in issues} == {
            "missing_open_day", "ohlcv_validity", "adjustment_date_consistency",
        }
        assert any(issue["observation_at"] == "2026-07-22" for issue in issues)
        assert any("high" in issue["field_name"] for issue in issues)

        market.upsert_daily_prices([
            _price("000001", "2026-07-22")
        ], adjustment="raw", source="repair")
        market.upsert_daily_prices([
            _price("000001", "2026-07-24")
        ], adjustment="hfq", source="repair")
        market.upsert_daily_prices([
            _price("000001", "2026-07-23")
        ], adjustment="qfq", source="repair")
        for issue in issues:
            remediation = control.create_remediation(
                issue["issue_id"], method="refetch", executor_type="quality_scan_smoke",
                executor_id="quality-scan-repair", reason="fixture data repaired",
                operator="smoke",
            )
            control.update_remediation(
                remediation["remediation_id"], status="awaiting_recheck",
            )
        recheck = engine.recheck(scan["scan_id"])
        verified = engine.run_scan(recheck["scan_id"])
        assert verified["status"] == "passed"
        assert verified["issues_found"] == 0
        assert verified["corrected_by_recheck"] == 6, verified
        assert all(
            issue["status"] == "corrected"
            for issue in control.list_issues(source_task_id=scan["scan_id"], limit=100)
        )

        # 已登记停牌日不应被 OHLCV 或复权日期一致性规则误报。
        market.upsert_symbols([
            {"symbol": "000002", "name": "suspended fixture", "source": "smoke"},
        ])
        governance.upsert_lifecycle_events([{
            "symbol": "000002", "event_type": "listed",
            "effective_from": "2026-07-21", "source": "smoke",
        }])
        for adjustment in ("raw", "qfq", "hfq"):
            market.upsert_daily_prices([
                _price("000002", "2026-07-21"),
            ], adjustment=adjustment, source="smoke")
        suspended_row = _price("000002", "2026-07-24")
        suspended_row.update({"open": 0, "high": 0, "low": 0, "close": 9, "volume": 0, "amount": 0})
        market.upsert_daily_prices([suspended_row], adjustment="raw", source="smoke")
        market.upsert_daily_prices([
            _price("000002", "2026-07-24"),
        ], adjustment="hfq", source="smoke")
        governance.upsert_trading_statuses([{
            "symbol": "000002", "trade_date": "2026-07-24",
            "status": "suspended", "is_tradable": False, "source": "smoke",
        }])
        suspended_scan = engine.create_scan(
            dataset="a_share_daily", date_from="2026-07-24", date_to="2026-07-24",
            scope="symbols", symbols=["000002.XSHE"],
            adjustments=["raw", "qfq", "hfq"],
            rules=["ohlcv_validity", "adjustment_date_consistency"],
        )
        suspended_completed = engine.run_scan(suspended_scan["scan_id"])
        assert suspended_completed["status"] == "passed", suspended_completed
        assert suspended_completed["issues_found"] == 0, suspended_completed

        # M3 必须显式发现未知可交易性，以及停牌状态与正成交量相冲突的事实。
        market.upsert_symbols([{
            "symbol": "000003", "name": "status semantics fixture", "source": "smoke",
        }, {
            "symbol": "000004", "name": "status without bar fixture", "source": "smoke",
        }])
        governance.upsert_lifecycle_events([{
            "symbol": "000003", "event_type": "listed",
            "effective_from": "2026-07-21", "source": "smoke",
        }, {
            "symbol": "000004", "event_type": "listed",
            "effective_from": "2026-07-21", "source": "smoke",
        }])
        market.upsert_daily_prices([
            _price("000003", "2026-07-23"),
            _price("000003", "2026-07-24"),
        ], adjustment="qfq", source="smoke")
        governance.upsert_trading_statuses([
            {
                "symbol": "000003", "trade_date": "2026-07-23",
                "status": "unknown", "is_tradable": None, "source": "smoke",
            },
            {
                "symbol": "000003", "trade_date": "2026-07-24",
                "status": "suspended", "is_tradable": False, "source": "smoke",
            },
            {
                "symbol": "000004", "trade_date": "2026-07-24",
                "status": "unknown", "is_tradable": None, "source": "smoke",
            },
        ])
        status_scan = engine.create_scan(
            dataset="a_share_daily", date_from="2026-07-23", date_to="2026-07-24",
            scope="symbols", symbols=["000003.XSHE", "000004.XSHE"], adjustments=["qfq"],
            rules=["trading_status_semantics"],
        )
        status_completed = engine.run_scan(status_scan["scan_id"])
        status_issues = control.list_issues(
            source_task_id=status_scan["scan_id"], limit=100,
        )
        assert status_completed["status"] == "issues_found", status_completed
        assert status_completed["issues_found"] == 3, status_issues
        assert any(
            issue["symbol"] == "000004"
            and issue["evidence"]["bar_count"] == 0
            for issue in status_issues
        ), status_issues
        assert {issue["rule_id"] for issue in status_issues} == {
            "trading_status_semantics",
        }
        assert {
            issue["evidence"]["issue_type"] for issue in status_issues
        } == {"unknown_tradability", "suspended_with_positive_volume"}

        entered = threading.Event()
        release = threading.Event()
        original_run_rule = engine._run_rule
        def slow_rule(_scan, _rule_id):
            entered.set()
            assert release.wait(5)
            return [], 1
        engine._run_rule = slow_rule
        controlled = engine.create_scan(
            dataset="a_share_daily", date_from="2026-07-21", date_to="2026-07-24",
            scope="symbols", symbols=["000001.XSHE"], adjustments=["raw"],
            rules=["missing_open_day", "ohlcv_validity"],
        )
        worker = threading.Thread(target=engine.run_scan, args=(controlled["scan_id"],))
        worker.start()
        assert entered.wait(5)
        paused = engine.request_pause(controlled["scan_id"])
        assert paused["control_state"] == "pausing"
        release.set()
        for _ in range(50):
            paused = engine.get_scan(controlled["scan_id"])
            if paused["completed_rules"] == 1 and paused["control_state"] == "paused":
                break
            time.sleep(0.02)
        assert (
            paused["completed_rules"] == 1
            and paused["control_state"] == "paused"
            and worker.is_alive()
        ), paused
        assert engine.resume(controlled["scan_id"])["control_state"] == "running"
        worker.join(5)
        assert not worker.is_alive()
        assert engine.get_scan(controlled["scan_id"])["status"] == "passed"

        entered = threading.Event()
        release = threading.Event()
        engine._run_rule = slow_rule
        stoppable = engine.create_scan(
            dataset="a_share_daily", date_from="2026-07-21", date_to="2026-07-24",
            scope="symbols", symbols=["000001.XSHE"], adjustments=["raw"],
            rules=["missing_open_day", "ohlcv_validity"],
        )
        worker = threading.Thread(target=engine.run_scan, args=(stoppable["scan_id"],))
        worker.start()
        assert entered.wait(5)
        stopping = engine.request_stop(stoppable["scan_id"])
        assert stopping["control_state"] == "stopping"
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        stopped = engine.get_scan(stoppable["scan_id"])
        assert stopped["control_state"] == "stopped", stopped
        assert stopped["last_error"] == "stopped_by_user"
        engine._run_rule = original_run_rule

    print("active quality scan/recheck smoke passed")


if __name__ == "__main__":
    main()
