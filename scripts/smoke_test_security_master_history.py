"""Golden checks for governed point-in-time security-master intervals."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


class _IndexReader:
    pass


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.services.strategy_dataset_resolver import StrategyDatasetResolver
    from data_platform.security_master_history import (
        build_security_master_intervals,
        validate_security_master_intervals,
    )
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.a_share_market_store import AShareMarketStore

    dates = [f"2026-01-{index:02d}" for index in range(1, 9)]
    daily = []
    for trade_date in dates:
        risk_warning = trade_date in {"2026-01-04", "2026-01-05"}
        daily.append(
            {
                "symbol": "000001",
                "trade_date": trade_date,
                "name": "ST黄金样本" if risk_warning else "黄金样本",
                "listing_status": "listed",
                "risk_warning": risk_warning,
                "available_at": trade_date,
                "source": "golden:daily-security-state",
                "source_observed_at": "2026-01-09T00:00:00+08:00",
            }
        )
    intervals = build_security_master_intervals(daily, expected_trade_dates=dates)
    for interval in intervals:
        interval["evidence"] = {
            **dict(interval.get("evidence") or {}),
            "job_id": "security-snapshot-v1",
        }
    assert [(row["valid_from"], row["valid_to"], row["risk_warning"]) for row in intervals] == [
        ("2026-01-01", "2026-01-03", False),
        ("2026-01-04", "2026-01-05", True),
        ("2026-01-06", "2026-01-08", False),
    ]
    assert validate_security_master_intervals(intervals)["ok"]
    try:
        build_security_master_intervals(daily[:-1], expected_trade_dates=dates)
    except ValueError as error:
        assert "coverage is incomplete" in str(error)
    else:
        raise AssertionError("missing daily security state must fail closed")

    with tempfile.TemporaryDirectory(prefix="scq-security-master-") as directory:
        database = Path(directory) / "market.sqlite3"
        governance = AShareGovernanceStore(database)
        market = AShareMarketStore(database)
        market.ensure_schema()
        governance.ensure_schema()
        assert governance.upsert_security_master_intervals(intervals) == 3
        governance.save_quality_report(
            quality_report_id="security-quality-v1",
            rule_version="security-master-test-v1",
            status="passed",
            payload={"snapshot_refs": ["security-snapshot-v1"]},
        )
        version_v1 = governance.publish_data_version(
            as_of_trade_date="2026-01-08",
            quality_report_id="security-quality-v1",
            members=[{
                "dataset": "security_master_intervals",
                "adjustment": "",
                "symbol_scope": "golden",
                "row_count": 3,
                "symbol_count": 1,
                "min_date": dates[0],
                "max_date": dates[-1],
                "source": "golden",
                "sync_run_ref": "security-snapshot-v1",
                "content_hash": "security-v1",
                "quality_status": "passed",
                "details": {"snapshot_refs": ["security-snapshot-v1"]},
            }],
        )
        rows = market.fetch_symbol_history("000001.XSHE", "2026-01-01", "2026-01-08")
        assert len(rows) == 3
        assert rows[1]["risk_warning"] is True
        assert market.security_master_history_coverage()["symbol_count"] == 1

        strict_source = '''
DATASET_REQUIREMENTS = ["a_share_daily", "a_share_catalog"]
DATASET_CONTRACTS = [
    {"dataset_id": "a_share_daily", "required_fields": ["close"],
     "minimum_history": 3, "adjustment": "qfq", "coverage_mode": "same_trade_date"},
    {"dataset_id": "a_share_catalog",
     "required_fields": ["symbol", "listing_status", "risk_warning", "valid_from", "available_at"],
     "coverage_mode": "as_of_trade_date"},
]
def generate_target_weights(bars, parameters):
    return [0.0 if bar["datasets"]["a_share_catalog"]["risk_warning"] else 1.0 for bar in bars]
'''
        bars = [
            {"symbol": "000001.XSHE", "date": trade_date, "close": 10.0}
            for trade_date in dates
        ]
        resolved = StrategyDatasetResolver(_IndexReader(), market_reader=market).resolve(
            strict_source,
            bars,
            {},
            {"evaluation_start_date": "2026-01-04", "evaluation_end_date": "2026-01-08",
             "adjustment": "qfq",
             "data_version_id": version_v1["data_version_id"]},
        )
        states = [row["datasets"]["a_share_catalog"]["risk_warning"] for row in resolved["bars"]]
        assert states == [False, False, False, True, True, False, False, False]
        assert resolved["evidence"][-2]["mode"] == "point_in_time_security_interval"

        replacement = build_security_master_intervals(
            [
                {
                    "symbol": "000001",
                    "trade_date": trade_date,
                    "listing_status": "listed",
                    "risk_warning": False,
                    "available_at": trade_date,
                    "source": "golden:daily-security-state",
                    "source_observed_at": "2026-01-10T00:00:00+08:00",
                }
                for trade_date in dates
            ],
            expected_trade_dates=dates,
        )
        for interval in replacement:
            interval["evidence"] = {
                **dict(interval.get("evidence") or {}),
                "job_id": "security-snapshot-v2",
            }
        assert governance.upsert_security_master_intervals(replacement) == 1
        governance.save_quality_report(
            quality_report_id="security-quality-v2",
            rule_version="security-master-test-v1",
            status="passed",
            payload={"snapshot_refs": ["security-snapshot-v2"]},
        )
        version_v2 = governance.publish_data_version(
            as_of_trade_date="2026-01-08",
            quality_report_id="security-quality-v2",
            members=[{
                "dataset": "security_master_intervals",
                "adjustment": "",
                "symbol_scope": "golden",
                "row_count": 1,
                "symbol_count": 1,
                "min_date": dates[0],
                "max_date": dates[-1],
                "source": "golden",
                "sync_run_ref": "security-snapshot-v2",
                "content_hash": "security-v2",
                "quality_status": "passed",
                "details": {"snapshot_refs": ["security-snapshot-v2"]},
            }],
        )
        active = market.fetch_symbol_history("000001", dates[0], dates[-1])
        assert len(active) == 1 and active[0]["risk_warning"] is False
        replay_v1 = market.fetch_symbol_history(
            "000001", dates[0], dates[-1], data_version_id=version_v1["data_version_id"]
        )
        replay_v2 = market.fetch_symbol_history(
            "000001", dates[0], dates[-1], data_version_id=version_v2["data_version_id"]
        )
        assert [row["risk_warning"] for row in replay_v1] == [False, True, False]
        assert len(replay_v2) == 1 and replay_v2[0]["risk_warning"] is False
        assert market.fetch_symbol_history(
            "000001", dates[0], dates[-1], data_version_id="missing-version"
        ) == []

    print("[security-master-history] passed")


if __name__ == "__main__":
    main()
