"""Deterministic smoke test for the stage-78.2 incremental scheduler."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self.reference_calls: list[str] = []
        self.request_gate = None
        self.fail_once: set[tuple[str, str]] = {("000001", "qfq")}
        self.fail_always: set[tuple[str, str]] = set()
        self.no_rows: set[tuple[str, str]] = set()
        self.suspended_dates: set[str] = set()

    def sync_symbol(
        self,
        store,
        *,
        symbol: str,
        adjustment: str,
        start_date: str,
        end_date: str,
    ):
        if self.request_gate is not None:
            self.request_gate()
        key = (symbol, adjustment)
        self.calls.append((symbol, adjustment, start_date, end_date))
        if key in self.fail_always:
            raise RuntimeError(f"permanent failure for {key}")
        if key in self.fail_once:
            self.fail_once.remove(key)
            raise RuntimeError(f"transient failure for {key}")
        if key in self.no_rows:
            return {
                "status": "completed",
                "symbol": symbol,
                "adjustment": adjustment,
                "start_date": start_date,
                "end_date": end_date,
                "rows_received": 0,
                "rows_written": 0,
            }
        row = {
            "symbol": symbol,
            "date": end_date,
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "volume": 1000,
            "amount": 10200,
        }
        written = store.upsert_daily_prices(
            [row],
            adjustment=adjustment,
            source="stage78.2-fake",
        )
        return {
            "status": "completed",
            "symbol": symbol,
            "adjustment": adjustment,
            "start_date": start_date,
            "end_date": end_date,
            "rows_received": 1,
            "rows_written": written,
        }


    def list_symbols(self):
        if self.request_gate is not None:
            self.request_gate()
        self.reference_calls.append("catalog")
        return [{"symbol": "000001", "name": "sample", "source": "smoke"}]

    def fetch_trade_calendar(self, *, start_date: str, end_date: str, market: str = "CN"):
        if self.request_gate is not None:
            self.request_gate()
        self.reference_calls.append("calendar")
        return [{
            "market": market,
            "trade_date": end_date,
            "is_open": True,
            "source": "smoke",
            "source_observed_at": "2026-01-08T00:00:00+00:00",
        }]

    def fetch_suspensions(self, *, trade_date: str):
        self.reference_calls.append("suspensions")
        if trade_date not in self.suspended_dates:
            return []
        return [{
            "symbol": "000001",
            "trade_date": trade_date,
            "status": "suspended",
            "is_tradable": False,
            "source": "smoke",
            "source_observed_at": "2026-01-08T00:00:00+00:00",
            "evidence": {"reason": "smoke suspension"},
        }]

    def fetch_index_daily_prices(self, *, index_symbol: str, start_date: str, end_date: str):
        if self.request_gate is not None:
            self.request_gate()
        self.reference_calls.append("index")
        return [{
            "index_symbol": index_symbol,
            "trade_date": end_date,
            "open": 4000,
            "high": 4010,
            "low": 3990,
            "close": 4005,
            "volume": 1,
            "amount": 1,
            "source": "smoke",
            "source_observed_at": "2026-01-08T00:00:00+00:00",
        }]

def main() -> None:
    ensure_project_root_on_sys_path()

    from data_platform.a_share_sync_scheduler import AShareSyncScheduler
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.a_share_market_store import AShareMarketStore

    with tempfile.TemporaryDirectory(prefix="scq-stage782-") as directory:
        database = Path(directory) / "market.sqlite3"
        market = AShareMarketStore(database)
        governance = AShareGovernanceStore(database)
        market.ensure_schema()
        governance.ensure_schema()
        market.replace_current_symbols(
            [{"symbol": "000001", "name": "sample", "source": "smoke"}]
        )
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "UPDATE market_symbols SET updated_at='2026-01-02T00:00:00+00:00'"
            )
        for adjustment in ("raw", "qfq", "hfq"):
            market.upsert_daily_prices(
                [{
                    "symbol": "000001",
                    "date": "2026-01-02",
                    "open": 10,
                    "high": 10.5,
                    "low": 9.5,
                    "close": 10.2,
                    "volume": 1000,
                    "amount": 10200,
                }],
                adjustment=adjustment,
                source="smoke",
            )
        _seed_governance(governance)
        initial = _publish_initial(governance)

        provider = FakeProvider()
        scheduler = AShareSyncScheduler(
            database,
            market_store=market,
            governance_store=governance,
            provider=provider,
            requests_per_minute=1_000_000,
            max_workers=3,
            retry_count=2,
            base_backoff_seconds=0,
            sleep=lambda _: None,
        )
        scheduler.ensure_schema()
        first = scheduler.create_job(
            target_trade_date="2026-01-05",
            symbols=["000001"],
            adjustments=["raw", "qfq", "hfq"],
        )
        first = scheduler.run_job(first["job_id"])
        _require(first["status"] == "published", f"transient retry did not publish: {first}")
        with closing(sqlite3.connect(database)) as connection:
            normal_status = connection.execute(
                """SELECT status, is_tradable, source
                   FROM security_trading_status_daily
                   WHERE symbol='000001' AND trade_date='2026-01-05'"""
            ).fetchone()
        _require(
            normal_status == (
                "normal", 1, "canonical_market_daily_prices:positive_bar",
            ),
            "successful price rows did not materialize point-in-time tradability",
        )
        _require(
            sum(1 for call in provider.calls if call[:2] == ("000001", "qfq")) == 2,
            "transient item was not retried exactly once",
        )
        first_version = first["data_version_id"]
        _require(first_version and first_version != initial, "new release was not published")
        first_release = governance.fetch_data_version(first_version)
        status_member = next(
            member for member in first_release["members"]
            if member["dataset"] == "security_trading_status_daily"
        )
        with closing(sqlite3.connect(database)) as connection:
            physical_status = connection.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT symbol),
                       MIN(trade_date), MAX(trade_date)
                FROM security_trading_status_daily
                """
            ).fetchone()
        _require(
            (
                status_member["row_count"], status_member["symbol_count"],
                status_member["min_date"], status_member["max_date"],
            ) == physical_status,
            "published trading-status member differs from the physical table",
        )
        _require(
            status_member["sync_run_ref"] == first["job_id"]
            and status_member["source"]
            == "stage78.2-incremental-status-materialization",
            "trading-status member was carried instead of regenerated",
        )
        inconsistent_members = [dict(member) for member in first_release["members"]]
        inconsistent_status = next(
            member for member in inconsistent_members
            if member["dataset"] == "security_trading_status_daily"
        )
        inconsistent_status["row_count"] += 1
        try:
            scheduler._validate_release_member_consistency(inconsistent_members)
        except RuntimeError as exc:
            _require(
                "release member consistency blocked" in str(exc),
                "inconsistent member failed without the expected gate evidence",
            )
        else:
            raise SystemExit(
                "stage78.2 smoke failed: inconsistent member was not blocked"
            )

        provider.fail_always.add(("000001", "hfq"))
        second = scheduler.create_job(
            target_trade_date="2026-01-06",
            symbols=["000001"],
            adjustments=["raw", "qfq", "hfq"],
        )
        second = scheduler.run_job(second["job_id"])
        _require(second["status"] == "failed", "failed batch was not rolled back")
        with closing(sqlite3.connect(database)) as connection:
            _require(connection.execute("SELECT COUNT(*) FROM market_daily_prices WHERE trade_date='2026-01-06'").fetchone()[0] == 0,
                     "failed batch leaked successful shards")
        _require(
            governance.get_overview()["published_version"]["data_version_id"]
            == first_version,
            "failed sync replaced the last published version",
        )
        provider.fail_always.clear()
        scheduler.retry_quarantined(second["job_id"])
        second = scheduler.run_job(second["job_id"])
        _require(second["status"] == "published", "quarantine retry did not publish")

        provider.no_rows.add(("000001", "raw"))
        provider.suspended_dates.add("2026-01-07")
        suspended = scheduler.create_job(
            target_trade_date="2026-01-07",
            symbols=["000001"],
            adjustments=["raw"],
        )
        suspended = scheduler.run_job(suspended["job_id"])
        _require(suspended["status"] == "published", "suspended no-row item did not publish")
        _require(
            suspended["items"][0]["result"]["completion_reason"]
            == "target_trade_date_suspended",
            "suspended no-row completion lacks explicit evidence",
        )
        provider.no_rows.clear()
        provider.suspended_dates.clear()

        recovery = scheduler.create_job(
            target_trade_date="2026-01-07",
            symbols=["000001"],
            adjustments=["raw"],
        )
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "UPDATE market_incremental_sync_jobs SET status='running' WHERE job_id=?",
                (recovery["job_id"],),
            )
            connection.execute(
                """
                UPDATE market_incremental_sync_items SET status='running'
                WHERE job_id=?
                """,
                (recovery["job_id"],),
            )
        recovered = scheduler.recover_interrupted_jobs()
        _require(recovered["recovered_jobs"] == 1, "running job was not recovered")
        _require(
            scheduler.get_job(recovery["job_id"], include_items=True)["items"][0]["status"]
            == "pending",
            "running item was not returned to pending",
        )

        scheduler.configure(enabled=True, run_time="18:15")
        due_now = datetime(2026, 1, 8, 12, 0, tzinfo=timezone.utc)
        due = scheduler.run_due(now=due_now)
        _require(due["status"] == "published", "due schedule did not publish")
        _require(
            {"catalog", "calendar", "index"} <= set(provider.reference_calls),
            "scheduled tick did not refresh catalog/calendar/index",
        )
        duplicate_due = scheduler.run_due(now=due_now)
        _require(
            duplicate_due["status"] == "already_scheduled",
            "same local day scheduled more than once",
        )

        overview = governance.get_overview()
        _require(
            overview["published_version"]["as_of_trade_date"] == "2026-01-08",
            "scheduled release did not become current",
        )
        release = governance.fetch_data_version(
            overview["published_version"]["data_version_id"]
        )
        reference_members = {
            member["dataset"]: member
            for member in release["members"]
            if member["dataset"] in {
                "market_trade_calendar", "market_index_daily_prices"
            }
        }
        _require(
            all(member["max_date"] == "2026-01-08" for member in reference_members.values()),
            "published manifest retained stale reference-data bounds",
        )
        _verify_suspended_increment_window(Path(directory))

        print(
            "stage78.2 incremental scheduler smoke passed "
            f"version={overview['published_version']['data_version_id']} "
            f"calls={len(provider.calls)}"
        )

def _verify_suspended_increment_window(directory: Path) -> None:
    from data_platform.a_share_sync_scheduler import AShareSyncScheduler
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.a_share_market_store import AShareMarketStore

    database = directory / "suspended-window.sqlite3"
    market = AShareMarketStore(database)
    governance = AShareGovernanceStore(database)
    market.ensure_schema()
    governance.ensure_schema()
    market.replace_current_symbols(
        [{"symbol": "000001", "name": "sample", "source": "smoke"}]
    )
    for adjustment in ("raw", "qfq", "hfq"):
        market.upsert_daily_prices(
            [{
                "symbol": "000001", "date": "2026-01-02", "open": 10,
                "high": 10.5, "low": 9.5, "close": 10.2,
                "volume": 1000, "amount": 10200,
            }],
            adjustment=adjustment,
            source="smoke",
        )
    _seed_governance(governance)
    governance.upsert_trade_calendar([{
        "market": "CN", "trade_date": "2026-01-08", "is_open": True,
        "source": "smoke", "source_observed_at": "2026-01-08T00:00:00+00:00",
    }])
    governance.upsert_index_prices([{
        "index_symbol": "000300", "trade_date": "2026-01-08",
        "open": 4000, "high": 4010, "low": 3990, "close": 4005,
        "volume": 1, "amount": 1, "source": "smoke",
        "source_observed_at": "2026-01-08T00:00:00+00:00",
    }])
    governance.upsert_trading_statuses([
        {
            "symbol": "000001", "trade_date": day,
            "status": "suspended", "is_tradable": False,
            "suspension_reason": "smoke suspension", "source": "smoke",
            "source_observed_at": "2026-01-08T00:00:00+00:00",
        }
        for day in ("2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08")
    ])
    provider = FakeProvider()
    provider.no_rows.add(("000001", "hfq"))
    provider.suspended_dates.add("2026-01-08")
    scheduler = AShareSyncScheduler(
        database,
        market_store=market,
        governance_store=governance,
        provider=provider,
        requests_per_minute=1_000_000,
        max_workers=1,
        retry_count=1,
        base_backoff_seconds=0,
        sleep=lambda _: None,
    )
    scheduler.ensure_schema()
    suspended_window = scheduler.create_job(
        target_trade_date="2026-01-08",
        symbols=["000001"],
        adjustments=["hfq"],
    )
    suspended_window = scheduler.run_job(suspended_window["job_id"])
    _require(
        suspended_window["status"] == "published",
        f"evidence-backed suspended increment window did not publish: {suspended_window}",
    )
    _require(
        suspended_window["items"][0]["result"]["completion_reason"]
        == "suspended_increment_window_without_any_prices",
        "multi-day suspended zero-row completion lacks explicit evidence",
    )

    market.upsert_daily_prices(
        [{
            "symbol": "000001", "date": "2026-01-09", "open": 10,
            "high": 10.5, "low": 9.5, "close": 10.2,
            "volume": 1000, "amount": 10200,
        }],
        adjustment="raw",
        source="smoke-adjustment-gap",
    )
    governance.upsert_trade_calendar([{
        "market": "CN", "trade_date": "2026-01-09", "is_open": True,
        "source": "smoke", "source_observed_at": "2026-01-09T00:00:00+00:00",
    }])
    provider.suspended_dates.add("2026-01-09")
    adjustment_gap = scheduler.create_job(
        target_trade_date="2026-01-09",
        symbols=["000001"],
        adjustments=["hfq"],
    )
    adjustment_gap = scheduler.run_job(adjustment_gap["job_id"])
    _require(
        adjustment_gap["status"] == "failed",
        "multi-day zero rows hid an adjustment-specific data gap",
    )


def _seed_governance(governance) -> None:
    days = ("2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07")
    governance.upsert_trade_calendar(
        [
            {
                "market": "CN",
                "trade_date": day,
                "is_open": True,
                "source": "smoke",
                "source_observed_at": "2026-01-08T00:00:00+00:00",
            }
            for day in days
        ]
    )
    governance.upsert_index_prices(
        [
            {
                "index_symbol": "000300",
                "trade_date": day,
                "open": 4000,
                "high": 4010,
                "low": 3990,
                "close": 4005,
                "volume": 1,
                "amount": 1,
                "source": "smoke",
                "source_observed_at": "2026-01-08T00:00:00+00:00",
            }
            for day in days
        ]
    )


def _publish_initial(governance) -> str:
    report_id = "stage782-smoke-initial-quality"
    governance.save_quality_report(
        quality_report_id=report_id,
        rule_version="smoke",
        status="passed",
        payload={"status": "passed"},
    )
    members = [
        {
            "dataset": "market_daily_prices",
            "adjustment": adjustment,
            "symbol_scope": "canonical_all",
            "row_count": 1,
            "symbol_count": 1,
            "min_date": "2026-01-02",
            "max_date": "2026-01-02",
            "source": "smoke",
            "content_hash": f"daily-{adjustment}",
            "quality_status": "passed",
        }
        for adjustment in ("raw", "qfq", "hfq")
    ]
    members.extend([
        {
            "dataset": "market_trade_calendar",
            "symbol_scope": "CN",
            "row_count": 4,
            "symbol_count": 1,
            "min_date": "2026-01-02",
            "max_date": "2026-01-07",
            "source": "smoke",
            "content_hash": "calendar",
            "quality_status": "passed",
        },
        {
            "dataset": "market_index_daily_prices",
            "symbol_scope": "000300",
            "row_count": 4,
            "symbol_count": 1,
            "min_date": "2026-01-02",
            "max_date": "2026-01-07",
            "source": "smoke",
            "content_hash": "index",
            "quality_status": "passed",
        },
    ])
    return governance.publish_data_version(
        as_of_trade_date="2026-01-02",
        quality_report_id=report_id,
        members=members,
        notes="stage78.2 smoke initial release",
    )["data_version_id"]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"stage78.2 smoke failed: {message}")


if __name__ == "__main__":
    main()
