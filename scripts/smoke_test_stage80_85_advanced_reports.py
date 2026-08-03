"""Acceptance smoke tests for report stages 80 through 85."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    root = ensure_project_root_on_sys_path()
    from app.services.backtest_advanced_analysis import build_advanced_analysis
    from app.services.cross_section_context import (
        build_industry_analysis,
        build_raw_factor_comparison,
        build_signal_market_regimes,
        index_industry_intervals,
        industry_cross_section,
    )
    from backtest_kernel.strategy_execution import execute_strategy_evidence

    bars = [
        {"date": f"2026-01-{index + 1:02d}", "close": 10 + index, "high": 11 + index, "low": 9 + index}
        for index in range(5)
    ]
    source = """
def generate_target_weights(bars, parameters):
    return [0.0, 0.0, 0.5, 0.5, 0.0]
def generate_signal_scores(bars, parameters):
    return [None, None, -0.2, 0.8, 0.1]
"""
    strategy = execute_strategy_evidence(source, bars, {})
    assert strategy["score_contract"] == "point_in_time_raw_score_v1"
    assert strategy["raw_scores"][3] == 0.8

    start = date(2025, 1, 1)
    accounts = []
    benchmark = []
    excess = []
    value = 1_000_000.0
    benchmark_value = 1.0
    for index in range(120):
        current = (start + timedelta(days=index)).isoformat()
        value *= 1.0 + (0.002 if index % 3 else -0.001)
        benchmark_value *= 1.0 + (0.0015 if index % 4 else -0.001)
        accounts.append({"snapshot_time": current, "total_value": value})
        benchmark.append({"date": current, "value": benchmark_value})
        excess.append({"date": current, "value": value / 1_000_000 / benchmark_value})
    trades = [
        {
            "trade_time": accounts[30]["snapshot_time"],
            "order_book_id": "000001.XSHE",
            "side": "BUY",
            "price": 10.1,
            "quantity": 10_000,
            "amount": 101_000,
            "notes": {"market_vwap": 10.0, "market_volume": 1_000_000},
        },
        {
            "trade_time": accounts[60]["snapshot_time"],
            "order_book_id": "000001.XSHE",
            "side": "SELL",
            "price": 10.4,
            "quantity": 10_000,
            "amount": 104_000,
            "notes": {"market_vwap": 10.5, "market_volume": 1_200_000},
        },
    ]
    advanced = build_advanced_analysis(
        account_rows=accounts,
        benchmark_curve=benchmark,
        excess_curve=excess,
        trades=trades,
        metrics={"total_returns": value / 1_000_000 - 1.0},
        raw_result={"signal_evidence": {"status": "ready", "signal_version": "v1"}, "price_bars": bars},
        extra_config={
            "rqalpha_local": {"commission_rate": 0.0003, "tax_rate": 0.001, "slippage_rate": 0.0005},
            "data_asset_trace": {"asset": {"data_version": "test-v1"}},
        },
    )
    assert advanced["monthly_return_heatmap"]["status"] == "ready"
    assert advanced["market_regimes"]["status"] == "ready"
    assert advanced["execution_quality"]["vwap_evidence_count"] == 2
    assert len(advanced["cost_capacity_stress"]["cost_matrix"]) == 9
    assert advanced["cost_capacity_stress"]["capacity"]["status"] == "ready"
    assert advanced["robustness"]["status"] == "ready"
    assert advanced["robustness"]["segments"][-1]["segment"] == "out_of_sample"
    assert advanced["report_governance"]["export_formats"] == ["pdf", "csv", "svg", "png"]
    assert "不构成投资建议" in advanced["report_governance"]["disclaimer"]

    observations = []
    for day in ("2026-01-01", "2026-01-02"):
        for index in range(5):
            observations.append(
                {
                    "date": day,
                    "raw_score": float(index),
                    "exposure": 1.0 if index >= 3 else 0.0,
                    "future_return": float(index) / 100,
                }
            )
    comparison = build_raw_factor_comparison(observations)
    assert comparison["status"] == "ready"
    assert comparison["raw_factor_ic_mean"] > comparison["exposure_ic_mean"]

    intervals = index_industry_intervals(
        [
            {"symbol": f"00000{index + 1}", "category": "行业A" if index < 3 else "行业B", "valid_from": "2025-01-01"}
            for index in range(5)
        ]
    )
    industry = industry_cross_section(
        date="2026-01-01",
        signals=[0, 1, 2, 3, 4],
        outcomes=[0, 1, 2, 4, 3],
        symbols=[f"00000{index + 1}" for index in range(5)],
        interval_index=intervals,
    )
    industry_report = build_industry_analysis(
        {key: [value, value * 0.9] for key, value in industry["industry_ic"].items()},
        [{"date": "2026-01-01", "ic": industry["neutral_ic"], "sample_size": 5}],
    )
    assert industry_report["status"] == "ready"

    ic_rows = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "ic": (-1) ** index * 0.01,
            "rank_ic": 0.02,
            "market_return": 0.004 if index < 25 else -0.004,
        }
        for index in range(45)
    ]
    regimes = build_signal_market_regimes(ic_rows, [])
    assert regimes["status"] == "ready"
    assert "preceding 20" in regimes["look_ahead_control"]

    ui = (Path(root) / "web" / "report-ui.js").read_text(encoding="utf-8")
    for token in ("monthlyHeatmap", "raw_factor_analysis", "cost_capacity_stress", "robustness"):
        assert token in ui
    print("stage80-85 advanced report smoke test passed")


if __name__ == "__main__":
    main()
