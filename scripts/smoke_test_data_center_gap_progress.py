"""Regression checks for M2 live progress/history gaps and M3 filter facets."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
from data_platform.storage.data_center_store import DataCenterStore


class _NoWriteProvider:
    def sync_symbol(self, *_args, **_kwargs):
        raise AssertionError("gap/progress smoke must not call an upstream provider")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-gap-progress-") as temporary:
        database = Path(temporary) / "market.sqlite3"
        market = AShareMarketStore(database)
        governance = AShareGovernanceStore(database)
        scheduler = AShareSyncScheduler(
            database, market_store=market, governance_store=governance,
            provider=_NoWriteProvider(), requests_per_minute=60,
            max_workers=1, retry_count=1,
        )
        scheduler.ensure_schema()
        market.replace_current_symbols([
            {"symbol": "000001", "name": "fixture", "source": "smoke"},
            {"symbol": "000002", "name": "no-lifecycle-fixture", "source": "smoke"},
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
            {"symbol": "000001", "trade_date": day, "open": 10, "high": 11,
             "low": 9, "close": 10, "volume": 1, "amount": 10}
            for day in ("2026-07-21", "2026-07-23", "2026-07-24")
        ], adjustment="raw", source="smoke")
        market.upsert_daily_prices([
            {"symbol": "000002", "trade_date": day, "open": 10, "high": 11,
             "low": 9, "close": 10, "volume": 1, "amount": 10}
            for day in ("2026-07-23", "2026-07-24")
        ], adjustment="raw", source="smoke")


        preview = scheduler.preview_job(
            target_trade_date="2026-07-24", symbols=["000001"],
            adjustments=["raw"], start_floor="2026-07-21", gap_scan=True,
        )
        assert preview["request_count"] == 1
        assert preview["missing_date_count"] == 1
        assert preview["tasks"][0]["first_missing_date"] == "2026-07-22"
        assert preview["tasks"][0]["last_missing_date"] == "2026-07-22"
        assert preview["tasks"][0]["missing_dates"] == ["2026-07-22"]
        assert preview["tasks"][0]["missing_dates_truncated"] is False
        all_current_preview = scheduler.preview_job(
            target_trade_date="2026-07-24", all_current=True,
            adjustments=["raw"], start_floor="2026-07-21", gap_scan=True,
        )
        assert all_current_preview["request_count"] == 1
        assert all_current_preview["missing_date_count"] == 1
        assert all_current_preview["tasks"][0]["symbol"] == "000001"
        assert all_current_preview["tasks"][0]["first_missing_date"] == "2026-07-22"

        no_lifecycle_quality = market.fetch_daily_prices(
            symbol="000002", adjustment="raw",
            start_date="2026-07-21", end_date="2026-07-24",
        )["quality"]
        assert no_lifecycle_quality["status"] == "passed"
        assert scheduler.latest_sync_target()["target_trade_date"] == "2026-07-24"

        job = scheduler.create_job(
            target_trade_date="2026-07-24", symbols=["000001"],
            adjustments=["raw"], start_floor="2026-07-21", gap_scan=True,
            mode="data_center_gap",
        )
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "UPDATE market_incremental_sync_items SET status='completed', rows_written=7 WHERE job_id=?",
                (job["job_id"],),
            )
        live = scheduler.get_job(job["job_id"])
        assert live["completed_items"] == 1
        assert live["processed_items"] == 1
        assert live["rows_written"] == 7

        store = DataCenterStore(database)
        issue = store.create_issue({
            "dataset": "a_share_daily", "symbol": "000001",
            "observation_at": "2026-07-22", "rule_id": "missing-open-day",
            "severity": "error", "source": "akshare",
            "source_task_id": job["job_id"], "evidence": {"missing": True},
        })
        assert store.list_issues(source="akshare")[0]["issue_id"] == issue["issue_id"]
        facets = store.quality_facets()
        assert facets["datasets"][0]["value"] == "a_share_daily"
        assert facets["sources"][0]["value"] == "akshare"
        assert facets["tasks"][0]["value"] == job["job_id"]

    print("data-center gap/progress/facets smoke passed")


if __name__ == "__main__":
    main()
