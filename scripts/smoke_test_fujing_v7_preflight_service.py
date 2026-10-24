"""Smoke check for the unified Fujing V7 fail-closed preflight facade."""

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.fujing_v7_preflight_service import run_fujing_v7_preflight
from backtest_kernel.strategy_execution import execute_strategy_evidence


SOURCE = '''
DATASET_REQUIREMENTS = ["a_share_daily"]
DATASET_CONTRACTS = [
    {"dataset_id": "a_share_daily", "required_fields": ["open", "high", "low", "close", "volume"],
     "minimum_history": 2, "adjustment": "qfq", "coverage_mode": "same_trade_date"},
]
def generate_target_weights(bars, parameters):
    return [1.0 if index >= 2 else 0.0 for index in range(len(bars))]
'''


def main() -> None:
    bars = []
    for day in range(1, 9):
        date = f"2026-01-{day:02d}"
        bar = {
            "symbol": "000001.XSHE", "date": date, "trade_date": date,
            "open": day, "high": day + 0.2, "low": day - 0.2,
            "close": day + 0.1, "volume": 1000 + day,
        }
        bar["datasets"] = {"a_share_daily": dict(bar)}
        bars.append(bar)
    universe = [{
        "symbol": "000001.XSHE", "name": "平安银行", "market": "SZ",
        "listing_status": "listed", "risk_warning": False,
        "valid_from": "2020-01-01", "valid_to": None,
        "available_at": "2020-01-01T08:00:00+08:00",
    }, {
        "symbol": "920001.XBSE", "name": "结构排除样本", "market": "BSE",
        "listing_status": "listed", "risk_warning": None,
        "valid_from": "2025-01-01", "valid_to": None,
        "available_at": "2025-01-01T08:00:00+08:00",
    }]
    result = run_fujing_v7_preflight(
        source_code=SOURCE,
        bars=bars,
        parameters={},
        evaluation_start_date="2026-01-03",
        evaluation_end_date="2026-01-08",
        universe_rows=universe,
        universe_as_of_date="2026-01-03",
        executor=execute_strategy_evidence,
    )
    assert result["ok"] is True, result
    assert result["failed_gates"] == []
    excluded = result["gates"]["point_in_time_universe"]["excluded"]
    assert excluded[0]["symbol"] == "920001.XBSE"
    assert excluded[0]["exclusion_reason"] == "structural_symbol_scope"
    blocked = run_fujing_v7_preflight(
        source_code=SOURCE,
        bars=bars[1:],
        parameters={},
        evaluation_start_date="2026-01-03",
        evaluation_end_date="2026-01-08",
        universe_rows=universe,
        universe_as_of_date="2026-01-03",
        executor=execute_strategy_evidence,
    )
    assert blocked["ok"] is False
    assert "research_window" in blocked["failed_gates"]
    print("[fujing-v7-preflight-service] passed")


if __name__ == "__main__":
    main()
