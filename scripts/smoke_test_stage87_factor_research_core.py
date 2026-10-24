"""Stage 87 deterministic smoke test for factor formulas and statistics."""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from _project_bootstrap import ensure_project_root_on_sys_path


def _assert_close(actual: float | None, expected: float, label: str) -> None:
    if actual is None or not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise SystemExit(f"stage87 core smoke failed: {label}: {actual!r} != {expected!r}")


def main() -> None:
    ensure_project_root_on_sys_path()

    from factor_lab.research_core import (
        average_ranks,
        build_factor_report,
        calculate_factor,
        canonical_hash,
        list_research_factor_definitions,
        preprocess_cross_section,
        spearman,
    )

    definitions = list_research_factor_definitions()
    expected_ids = {
        "close_to_close_return_1d",
        "momentum_20d",
        "momentum_60d",
        "volatility_20d",
        "close_to_ma20_bias",
        "amount_strength_20d",
        "winner_proxy_low_120d",
        "winner_proxy_high_120d",
        "winner_proxy_spread_120d",
        "causal_trough_event_16d",
        "amplitude_ratio_1d",
    }
    if {item["factor_id"] for item in definitions} != expected_ids:
        raise SystemExit("stage87 core smoke failed: P0 definition registry mismatch")
    if canonical_hash({"b": 2, "a": 1}) != canonical_hash({"a": 1, "b": 2}):
        raise SystemExit("stage87 core smoke failed: canonical hash is not stable")

    start = date(2026, 1, 1)
    bars = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "close": 100.0 + index,
            "amount": 1000.0 + index * 10.0,
        }
        for index in range(61)
    ]
    latest = bars[-1]["date"]
    _assert_close(
        calculate_factor("close_to_close_return_1d", bars)[latest],
        160.0 / 159.0 - 1.0,
        "one-day return",
    )
    _assert_close(
        calculate_factor("momentum_20d", bars)[latest],
        160.0 / 140.0 - 1.0,
        "20-day momentum",
    )
    _assert_close(
        calculate_factor("momentum_60d", bars)[latest],
        160.0 / 100.0 - 1.0,
        "60-day momentum",
    )
    expected_volatility = statistics.pstdev(
        (100.0 + index) / (99.0 + index) - 1.0 for index in range(41, 61)
    )
    _assert_close(
        calculate_factor("volatility_20d", bars)[latest],
        expected_volatility,
        "20-day volatility",
    )
    _assert_close(
        calculate_factor("close_to_ma20_bias", bars)[latest],
        160.0 / statistics.fmean(range(141, 161)) - 1.0,
        "MA20 bias",
    )
    _assert_close(
        calculate_factor("amount_strength_20d", bars)[latest],
        1600.0 / statistics.fmean(range(1410, 1610, 10)) - 1.0,
        "amount strength",
    )

    if average_ranks([1.0, 1.0, 3.0]) != [1.5, 1.5, 3.0]:
        raise SystemExit("stage87 core smoke failed: average tie ranks mismatch")
    _assert_close(spearman([1.0, 1.0, 3.0], [2.0, 2.0, 4.0]), 1.0, "tie Spearman")

    processed = preprocess_cross_section(
        {"000001": 1.0, "000002": 2.0, "000003": 10.0, "000004": 12.0},
        industries={"000001": "I1", "000002": "I1", "000003": "I2", "000004": "I2"},
        winsor_mad=3.0,
        industry_neutral=True,
        standardize=True,
        direction="negative",
    )
    if processed["status"] != "ready" or len(processed["steps"]) != 4:
        raise SystemExit("stage87 core smoke failed: preprocessing evidence mismatch")
    if any(
        not math.isclose(processed["aligned"][symbol], -value, abs_tol=1e-12)
        for symbol, value in processed["processed"].items()
    ):
        raise SystemExit("stage87 core smoke failed: negative direction alignment mismatch")

    observations: list[dict[str, object]] = []
    universe: dict[str, int] = {}
    for day in range(3):
        trade_date = f"2026-03-{day + 2:02d}"
        universe[trade_date] = 10
        for index in range(10):
            aligned = float(index)
            observations.append(
                {
                    "trade_date": trade_date,
                    "symbol": f"{index + 1:06d}",
                    "raw_value": aligned,
                    "processed_value": aligned,
                    "aligned_value": aligned,
                    "forward_returns": {"5": aligned * 0.001 + day * 0.0001},
                    "industry": "I1" if index < 5 else "I2",
                    "group_no": None,
                }
            )
    report = build_factor_report(
        observations=observations,
        universe_count_by_date=universe,
        horizons=[5],
        group_count=5,
        direction="positive",
        cost_rate=0.001,
    )
    _assert_close(report["coverage"]["average_factor_coverage"], 1.0, "factor coverage")
    _assert_close(report["ic"]["5"]["direction_aligned_rank_ic_mean"], 1.0, "aligned Rank IC")
    if report["execution_estimate"]["status"] != "estimate_only":
        raise SystemExit("stage87 core smoke failed: execution estimate semantics mismatch")
    if not report["group_analysis"]["nav"] or not report["industry_ic"]:
        raise SystemExit("stage87 core smoke failed: enhanced report sections missing")
    if any(row["group_no"] is None for row in observations):
        raise SystemExit("stage87 core smoke failed: group assignment was not persisted")

    print("stage87 factor research core smoke test passed")


if __name__ == "__main__":
    main()
