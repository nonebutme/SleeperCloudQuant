"""Smoke checks for point-in-time universe and sealed OOS evidence gates."""

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.governed_point_in_time_universe import build_point_in_time_a_share_universe
from app.services.sealed_oos_evidence_gate import (
    build_oos_view_record,
    build_sealed_oos_manifest,
    verify_frozen_inputs,
)


def main() -> None:
    facts = [
        {
            "symbol": "000001.XSHE", "name": "平安银行", "market": "SZ",
            "listing_status": "listed", "risk_warning": False,
            "valid_from": "2020-01-01", "valid_to": None,
            "available_at": "2020-01-01T08:00:00+08:00",
        },
        {
            "symbol": "000002.XSHE", "name": "示例ST", "market": "SZ",
            "listing_status": "listed", "risk_warning": True,
            "valid_from": "2025-05-01", "valid_to": "2026-05-31",
            "available_at": "2025-05-01T08:00:00+08:00",
        },
    ]
    universe = build_point_in_time_a_share_universe(facts, as_of_date="2026-01-15")
    assert universe["ok"] is True, universe
    assert [item["symbol"] for item in universe["eligible"]] == ["000001.XSHE"]
    assert universe["excluded"][0]["exclusion_reason"] == "risk_warning"
    invalid = build_point_in_time_a_share_universe(
        [{**facts[0], "risk_warning": "unknown"}], as_of_date="2026-01-15"
    )
    assert invalid["ok"] is False
    assert invalid["eligible"] == []
    assert invalid["issues"][0]["code"] == "risk_warning_value_invalid"

    structurally_excluded = build_point_in_time_a_share_universe(
        [{
            "symbol": "920001.XBSE",
            "listing_status": "listed",
            "risk_warning": None,
            "valid_from": "2025-01-01",
            "valid_to": None,
            "available_at": "2025-01-01",
        }],
        as_of_date="2026-01-15",
        structural_exclusion_prefixes=("92",),
    )
    assert structurally_excluded["ok"]
    assert not structurally_excluded["eligible"]
    assert structurally_excluded["excluded"][0]["exclusion_reason"] == "structural_symbol_scope"

    datasets = [
        {
            "dataset_id": "a_share_daily",
            "version_id": "release-001",
            "quality_report_id": "quality-001",
        }
    ]
    factors = [{"factor_id": "winner_proxy_120d", "artifact_id": "artifact-001"}]
    manifest = build_sealed_oos_manifest(
        strategy_id="fujing_v2",
        strategy_version="7-candidate",
        source_sha256="source-sha",
        parameters={"trough_window": 16, "amplitude_ratio_min": 0.01},
        dataset_bindings=datasets,
        factor_bindings=factors,
        universe_snapshot_id="universe-20260115",
        development_window={"start_date": "2022-01-01", "end_date": "2024-12-31"},
        oos_window={"start_date": "2025-01-01", "end_date": "2025-12-31"},
        primary_metrics=("annualized_return", "max_drawdown"),
        decision_thresholds={"max_drawdown_gte": -0.25},
    )
    matching = verify_frozen_inputs(
        manifest,
        source_sha256="source-sha",
        parameters={"trough_window": 16, "amplitude_ratio_min": 0.01},
        dataset_bindings=datasets,
        factor_bindings=factors,
        universe_snapshot_id="universe-20260115",
    )
    assert matching["ok"] is True
    changed = verify_frozen_inputs(
        manifest,
        source_sha256="source-sha",
        parameters={"trough_window": 16, "amplitude_ratio_min": 0.02},
        dataset_bindings=datasets,
        factor_bindings=factors,
        universe_snapshot_id="universe-20260115",
    )
    assert changed["ok"] is False
    assert changed["status"] == "oos_invalidated"
    view = build_oos_view_record(
        manifest, result_sha256="result-sha", viewed_at="2026-08-16T17:00:00+08:00"
    )
    assert view["status"] == "viewed_no_longer_unseen"
    print("[fujing-v7-universe-oos-gates] passed")


if __name__ == "__main__":
    main()
