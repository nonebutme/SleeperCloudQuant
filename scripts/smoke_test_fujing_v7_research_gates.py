"""Smoke checks for the Fujing V7 field, warm-up and causality gates."""

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.strategy_causality_gate import verify_strategy_prefix_stability
from app.services.strategy_research_preflight import (
    parse_strategy_dataset_contracts,
    require_strategy_runtime_adjustment,
    validate_prepared_research_window,
    validate_strategy_research_contract,
)
from backtest_kernel.strategy_execution import execute_strategy_evidence


CONTRACT_SOURCE = '''
DATASET_REQUIREMENTS = [
    "a_share_daily", "a_share_catalog", "trade_calendar",
    "trading_status", "corporate_actions",
]
DATASET_CONTRACTS = [
    {"dataset_id": "a_share_daily", "required_fields": ["open", "high", "low", "close", "volume"],
     "minimum_history": 3, "adjustment": "qfq", "coverage_mode": "same_trade_date"},
    {"dataset_id": "a_share_catalog", "required_fields": ["symbol", "name", "listing_status"],
     "coverage_mode": "as_of_trade_date"},
    {"dataset_id": "trade_calendar", "required_fields": ["trade_date", "is_open"],
     "coverage_mode": "same_trade_date"},
    {"dataset_id": "trading_status", "required_fields": ["trade_date", "is_tradable"],
     "coverage_mode": "same_trade_date"},
    {"dataset_id": "corporate_actions", "required_fields": ["event_date", "available_at"],
     "coverage_mode": "event_stream"},
]
def generate_target_weights(bars, parameters):
    return [1.0 if index >= 2 else 0.0 for index in range(len(bars))]
'''


NON_CAUSAL_SOURCE = '''
def generate_target_weights(bars, parameters):
    final_close = float(bars[-1]["close"])
    return [1.0 if float(bar["close"]) < final_close else 0.0 for bar in bars]
'''


def _bars() -> list[dict]:
    rows = []
    for day in range(1, 9):
        date = f"2026-01-{day:02d}"
        base = {
            "symbol": "000001.XSHE", "trade_date": date, "date": date,
            "open": float(day), "high": float(day) + 0.2,
            "low": float(day) - 0.2, "close": float(day), "volume": 1000.0,
        }
        base["datasets"] = {
            "a_share_daily": dict(base),
            "a_share_catalog": {"symbol": "000001.XSHE", "name": "示例", "listing_status": "listed"},
            "trade_calendar": {"trade_date": date, "is_open": True},
            "trading_status": {"trade_date": date, "is_tradable": True},
            "corporate_actions": [],
        }
        rows.append(base)
    return rows


def main() -> None:
    contract = validate_strategy_research_contract(CONTRACT_SOURCE)
    assert contract["ok"] is True, contract
    adjustment = require_strategy_runtime_adjustment(CONTRACT_SOURCE, "qfq")
    assert adjustment and adjustment["status"] == "matched"
    try:
        require_strategy_runtime_adjustment(CONTRACT_SOURCE, "raw")
    except ValueError as error:
        assert "strategy_adjustment_mismatch" in str(error)
    else:
        raise AssertionError("strict qfq strategy must reject raw runtime bars")
    contracts = parse_strategy_dataset_contracts(CONTRACT_SOURCE)
    prepared = validate_prepared_research_window(
        _bars(),
        evaluation_start_date="2026-01-04",
        evaluation_end_date="2026-01-08",
        contracts=contracts,
    )
    assert prepared["ok"] is True, prepared
    assert prepared["warmup"]["row_count"] == 3
    incomplete = _bars()
    incomplete[4]["datasets"]["trading_status"] = None
    rejected = validate_prepared_research_window(
        incomplete,
        evaluation_start_date="2026-01-04",
        evaluation_end_date="2026-01-08",
        contracts=contracts,
    )
    assert rejected["ok"] is False
    assert any(item["code"] == "dataset_common_coverage_incomplete" for item in rejected["issues"])

    unknown = _bars()
    unknown[4]["datasets"]["trading_status"] = {
        "trade_date": unknown[4]["date"], "is_tradable": None,
    }
    rejected_unknown = validate_prepared_research_window(
        unknown,
        evaluation_start_date="2026-01-04",
        evaluation_end_date="2026-01-08",
        contracts=contracts,
    )
    assert any(
        item["code"] == "trading_status_value_incomplete"
        for item in rejected_unknown["issues"]
    )

    conflict = _bars()
    conflict[4]["datasets"]["trading_status"] = {
        "trade_date": conflict[4]["date"], "is_tradable": False,
    }
    rejected_conflict = validate_prepared_research_window(
        conflict,
        evaluation_start_date="2026-01-04",
        evaluation_end_date="2026-01-08",
        contracts=contracts,
    )
    assert any(
        item["code"] == "trading_status_price_conflict"
        for item in rejected_conflict["issues"]
    )

    causal = verify_strategy_prefix_stability(
        CONTRACT_SOURCE,
        _bars(),
        {},
        executor=execute_strategy_evidence,
        checkpoints=(3, 5, 7),
    )
    assert causal["ok"] is True, causal
    non_causal = verify_strategy_prefix_stability(
        NON_CAUSAL_SOURCE,
        _bars(),
        {},
        executor=execute_strategy_evidence,
        checkpoints=(3, 5, 7),
    )
    assert non_causal["ok"] is False
    assert any(item["code"] == "future_data_changes_past_weight" for item in non_causal["issues"])
    print("[fujing-v7-research-gates] passed")


if __name__ == "__main__":
    main()
