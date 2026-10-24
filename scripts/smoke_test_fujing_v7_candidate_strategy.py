"""Golden checks for the inactive Fujing V7 candidate source."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.strategy_causality_gate import verify_strategy_prefix_stability
    from app.services.strategy_research_preflight import validate_strategy_research_contract
    from app.services.strategy_service import StrategyService
    from backtest_kernel.strategy_execution import execute_strategy_evidence

    source = Path("scripts/fujing_v2_v7_candidate.py").read_text(encoding="utf-8-sig")
    namespace: dict[str, object] = {}
    exec(compile(source, "fujing_v2_v7_candidate.py", "exec"), namespace)
    assert namespace["PORTFOLIO_EXECUTION_CONTRACT"] == {
        "rebalance_policy": "event_driven",
        "capacity_replacement_policy": "incumbent_priority",
        "event_driven_slot_weight_policy": "portfolio_exposure_divided_by_max_positions",
        "max_single_position_weight": 0.15,
        "position_cap_trigger": "prior_close_snapshot_next_tradable_open_trim_to_cap",
        "position_cap_released_cash": "retain_as_cash",
    }
    validation = StrategyService.validate_source(StrategyService.__new__(StrategyService), source)
    assert validation["ok"], validation
    assert validate_strategy_research_contract(source)["ok"]
    bars = _bars("000001.XSHE", risk_warning=False)
    evidence = execute_strategy_evidence(source, bars, {})
    assert evidence["weights"][199] == 0.0
    assert evidence["weights"][200] == 1.0
    assert evidence["raw_scores"][200] > 0.0
    causality = verify_strategy_prefix_stability(
        source,
        bars,
        {},
        executor=execute_strategy_evidence,
        checkpoints=(200, 202, 204),
    )
    assert causality["ok"], causality

    excluded = _bars("920001.XBSE", risk_warning=None)
    excluded_evidence = execute_strategy_evidence(source, excluded, {})
    assert not any(excluded_evidence["weights"])
    star_special = _bars("689009.XSHG", risk_warning=False)
    star_special_evidence = execute_strategy_evidence(source, star_special, {})
    assert not any(star_special_evidence["weights"])
    print("[fujing-v7-candidate-strategy] passed")


def _bars(symbol: str, *, risk_warning: bool | None) -> list[dict]:
    start = date(2025, 1, 1)
    rows: list[dict] = []
    for index in range(205):
        trade_date = (start + timedelta(days=index)).isoformat()
        factor_rows = {
            "winner_proxy_low_120d": _factor("winner_proxy_low_120d", 0.05),
            "winner_proxy_high_120d": _factor("winner_proxy_high_120d", 0.50),
            "winner_proxy_spread_120d": _factor("winner_proxy_spread_120d", 0.40),
            "causal_trough_event_16d": _factor(
                "causal_trough_event_16d", 1.0 if index == 199 else 0.0,
            ),
            "amplitude_ratio_1d": _factor("amplitude_ratio_1d", 0.01),
        }
        row = {
            "symbol": symbol,
            "date": trade_date,
            "trade_date": trade_date,
            "open": 10.0,
            "high": 10.2,
            "low": 9.9,
            "close": 10.0,
            "volume": 1000.0 + index,
        }
        row["datasets"] = {
            "a_share_daily": dict(row),
            "a_share_catalog": {
                "symbol": symbol,
                "listing_status": "listed",
                "risk_warning": risk_warning,
                "valid_from": "2020-01-01",
                "available_at": "2020-01-01",
            },
            "trade_calendar": {"trade_date": trade_date, "is_open": True},
            "trading_status": {"trade_date": trade_date, "is_tradable": True},
            "factor_values": factor_rows,
        }
        rows.append(row)
    return rows


def _factor(factor_id: str, value: float) -> dict:
    return {
        "factor_id": factor_id,
        "artifact_id": f"artifact-{factor_id}",
        "value": value,
        "aligned_value": value,
    }


if __name__ == "__main__":
    main()
