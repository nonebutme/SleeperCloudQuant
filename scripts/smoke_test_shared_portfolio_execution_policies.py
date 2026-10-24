"""Verify event-driven rebalancing and incumbent-priority capacity semantics."""

from __future__ import annotations

from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


DATES = ("2020-01-02", "2020-01-03", "2020-01-06")


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.shared_portfolio_service import (
        _declared_portfolio_execution_contract,
        _run_shared_account,
    )

    candidate_source = Path("scripts/fujing_v2_v7_candidate.py").read_text(
        encoding="utf-8-sig"
    )
    assert _declared_portfolio_execution_contract(candidate_source) == {
        "rebalance_policy": "event_driven",
        "capacity_replacement_policy": "incumbent_priority",
        "event_driven_slot_weight_policy": "portfolio_exposure_divided_by_max_positions",
        "max_single_position_weight": 0.15,
        "position_cap_trigger": "prior_close_snapshot_next_tradable_open_trim_to_cap",
        "position_cap_released_cash": "retain_as_cash",
    }

    prepared = {
        "A": _payload("A", (10.0, 10.5, 10.7), (1.0, 1.0, 1.0), (2.0, 2.0, 2.0)),
        "B": _payload("B", (10.0, 9.5, 9.7), (1.0, 1.0, 1.0), (1.0, 1.0, 1.0)),
        "C": _payload("C", (10.0, 10.1, 10.2), (0.0, 1.0, 1.0), (0.0, 3.0, 3.0)),
    }
    base_config = {
        "initial_cash": 1_000_000.0,
        "parameters": {"execution_price": "open"},
        "max_positions": 2,
        "portfolio_exposure": 0.90,
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "tax_rate": 0.001,
        "slippage_rate": 0.0005,
        "adjustment": "raw",
        "date_window": {"start_date": DATES[0], "end_date": DATES[-1]},
    }
    strategy = {
        "strategy_id": "execution-policy-smoke",
        "latest_version": 1,
        "source_sha256": "smoke",
        "execution_contract": "next_trade_date_open",
    }
    event_raw, _ = _run_shared_account(
        prepared,
        {
            **base_config,
            "rebalance_policy": "event_driven",
            "capacity_replacement_policy": "incumbent_priority",
        },
        strategy,
        [],
    )
    event_trades = event_raw["trades"]
    if len(event_trades) != 2 or any(row["side"] != "BUY" for row in event_trades):
        raise SystemExit(
            f"event-driven incumbent policy traded without a membership event: {event_trades}"
        )
    if {row["order_book_id"] for row in event_trades} != {"A", "B"}:
        raise SystemExit("incumbent-priority policy replaced a valid incumbent")
    event_rules = event_raw["execution_rules"]
    if event_rules.get("rebalance_policy") != "event_driven":
        raise SystemExit("event-driven policy evidence is missing")
    if event_rules.get("capacity_replacement_policy") != "incumbent_priority":
        raise SystemExit("incumbent-priority policy evidence is missing")

    legacy_raw, _ = _run_shared_account(
        prepared,
        {
            **base_config,
            "rebalance_policy": "daily_equal_weight",
            "capacity_replacement_policy": "force_top_n",
        },
        strategy,
        [],
    )
    later_trades = [
        row for row in legacy_raw["trades"]
        if str(row["trade_time"])[:10] > DATES[0]
    ]
    if not any(row["side"] == "SELL" and row["order_book_id"] == "B" for row in later_trades):
        raise SystemExit("legacy force-Top-N behavior did not replace the lower-ranked incumbent")
    if not any(row["side"] == "BUY" and row["order_book_id"] == "C" for row in later_trades):
        raise SystemExit("legacy force-Top-N behavior did not admit the challenger")

    cap_prepared = {
        "A": _payload("A", (10.0, 20.0, 20.0), (1.0, 1.0, 1.0), (2.0, 2.0, 2.0)),
        "B": _payload("B", (10.0, 10.0, 10.0), (1.0, 1.0, 1.0), (1.0, 1.0, 1.0)),
    }
    cap_raw, cap_metrics = _run_shared_account(
        cap_prepared,
        {
            **base_config,
            "max_positions": 10,
            "rebalance_policy": "event_driven",
            "capacity_replacement_policy": "incumbent_priority",
            "max_single_position_weight": 0.15,
        },
        strategy,
        [],
    )
    cap_sells = [row for row in cap_raw["trades"] if row["side"] == "SELL"]
    if len(cap_sells) != 1 or str(cap_sells[0]["trade_time"])[:10] != DATES[2]:
        raise SystemExit(f"position cap was not executed on the next trade date: {cap_sells}")
    if (cap_sells[0].get("notes") or {}).get("sell_cause") != "single_position_weight_cap":
        raise SystemExit("position cap sell cause evidence is missing")
    if int(cap_metrics.get("executed_position_cap_trim_count") or 0) != 1:
        raise SystemExit("position cap execution metric is missing")
    if any(row["side"] == "BUY" and str(row["trade_time"])[:10] == DATES[2] for row in cap_raw["trades"]):
        raise SystemExit("position cap released cash was redistributed")
    print("shared portfolio execution policy smoke test passed")


def _payload(symbol: str, closes, weights, scores):
    return {
        "meta": {"name": symbol, "rqalpha_symbol": symbol},
        "rows": [
            {
                "date": trade_date,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1_000_000,
            }
            for trade_date, close in zip(DATES, closes)
        ],
        "weights": list(weights),
        "scores": list(scores),
        "dataset_evidence": [],
    }


if __name__ == "__main__":
    main()
