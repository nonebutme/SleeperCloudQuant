"""Evaluate Fujing V7 on the frozen pre-OOS development cohort.

This script reuses the governed dataset resolver, the exact inactive V7 source,
and the formal shared-cash portfolio simulator.  It must never read dates on or
after the sealed OOS boundary.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import statistics
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


DATA_VERSION_ID = "scq-20260810-045e17a46a731835"
COHORT_SIZE = 200
FETCH_START = "2015-01-05"
EVALUATION_START = "2016-01-04"
LAST_SIGNAL_DATE = "2024-11-29"
OUTCOME_CUTOFF = "2024-12-31"
OOS_START = "2025-01-01"
FACTORS = (
    "winner_proxy_low_120d",
    "winner_proxy_high_120d",
    "winner_proxy_spread_120d",
    "causal_trough_event_16d",
    "amplitude_ratio_1d",
)
SENSITIVITY = (
    ("default", {}),
    ("amplitude_0_010", {"amplitude_ratio_min": 0.010}),
    ("spread_0_200", {"winner_spread_min": 0.20}),
    ("low_0_150", {"winner_low_threshold": 0.15}),
    ("high_0_900", {"winner_high_threshold": 0.90}),
    ("trailing_0_900", {"trailing_stop": 0.90}),
    ("trailing_0_980", {"trailing_stop": 0.98}),
)
ENTRY_ABLATIONS = (
    ("amplitude_filter_neutralized", {"amplitude_ratio_min": 0.0}),
    ("spread_filter_neutralized", {"winner_spread_min": 0.0}),
    ("high_exclusion_neutralized", {"winner_high_threshold": 1.0}),
    ("low_requirement_neutralized", {"winner_low_threshold": 1.0}),
)
RISK_OVERLAYS = (
    ("portfolio_exposure_0_50", {"portfolio_exposure": 0.50}),
    ("max_positions_5", {"max_positions": 5}),
    ("max_positions_20", {"max_positions": 20}),
)


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.shared_portfolio_service import _performance_metrics, _run_shared_account
    from app.services.strategy_dataset_resolver import StrategyDatasetResolver
    from app.services.strategy_service import StrategyService
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.a_share_market_store import AShareMarketStore
    from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore

    market_path = Path("var/market/a_share_market.sqlite3")
    research_store = SqliteFactorResearchStore(Path("var/runtime/factor_research.sqlite3"))
    market = AShareMarketStore(market_path)
    governance = AShareGovernanceStore(market_path)
    source_path = Path("scripts/fujing_v2_v7_candidate.py")
    source = source_path.read_text(encoding="utf-8-sig")
    validation = StrategyService.validate_source(StrategyService.__new__(StrategyService), source)
    if not validation["ok"]:
        raise SystemExit(json.dumps(validation, ensure_ascii=False, indent=2))
    strategy_module = _load_strategy(source_path)
    v6_source_path = Path("scripts/fujing_v2_strategy.py")
    v6_source = v6_source_path.read_text(encoding="utf-8-sig")
    v6_validation = StrategyService.validate_source(
        StrategyService.__new__(StrategyService), v6_source,
    )
    if not v6_validation["ok"]:
        raise SystemExit(json.dumps(v6_validation, ensure_ascii=False, indent=2))
    v6_module = _load_strategy(v6_source_path)

    artifacts: dict[str, dict[str, Any]] = {}
    tasks: dict[str, dict[str, Any]] = {}
    for factor_id in FACTORS:
        task_id = (
            f"fujing-v7-development-cohort-{COHORT_SIZE}-{factor_id}-2015-2024-raw-v2"
        )
        task = research_store.get_task(task_id)
        if task.get("status") != "completed":
            raise SystemExit(f"development task is not completed: {task_id}")
        matches = [
            item for item in research_store.list_artifacts(factor_id=factor_id, limit=100)
            if str(item.get("source_task_id") or "") == task_id
        ]
        if len(matches) != 1 or matches[0].get("data_version_id") != DATA_VERSION_ID:
            raise SystemExit(f"exact development artifact unavailable: {factor_id}")
        artifacts[factor_id] = dict(matches[0])
        tasks[factor_id] = task
    symbols = list(tasks[FACTORS[0]]["snapshots"][0]["payload"]["symbols"])
    if len(symbols) != COHORT_SIZE:
        raise SystemExit(f"unexpected cohort size: {len(symbols)}")

    factor_bindings = {
        factor_id: str(artifacts[factor_id]["artifact_id"]) for factor_id in FACTORS
    }
    defaults = dict(validation["parameter_defaults"])
    resolver = StrategyDatasetResolver(
        governance, market_reader=market, factor_store=research_store,
    )
    frozen = resolver.freeze_parameters(
        source, {**defaults, "factor_artifacts": factor_bindings},
    )
    prepared_base: dict[str, dict[str, Any]] = {}
    eligibility_skips = 0
    dynamic_binding_starts: dict[str, str] = {}
    excluded: list[dict[str, str]] = []
    for symbol in symbols:
        bars = market.fetch_price_history(
            symbol, FETCH_START, OUTCOME_CUTOFF, adjustment="qfq",
        )
        for row in bars:
            row.setdefault("symbol", symbol)
        if len(bars) <= 200:
            excluded.append({
                "symbol": symbol,
                "reason": f"minimum_history_200_unavailable:{len(bars)}",
            })
            continue
        symbol_evaluation_start = max(EVALUATION_START, _date(bars[200]))
        dynamic_binding_starts[symbol] = symbol_evaluation_start
        try:
            resolved = resolver.resolve(
                source,
                bars,
                frozen,
                {
                    "evaluation_start_date": symbol_evaluation_start,
                    "evaluation_end_date": LAST_SIGNAL_DATE,
                    "data_version_id": DATA_VERSION_ID,
                },
            )
        except RuntimeError as error:
            raise RuntimeError(f"dataset binding failed for {symbol}: {error}") from error
        eligibility_skips += sum(
            int(item.get("decision_ineligible_rows") or 0)
            for item in resolved["evidence"]
            if item.get("dataset_id") == "factor_values"
        )
        rows = [
            row for row in resolved["bars"]
            if EVALUATION_START <= _date(row) <= OUTCOME_CUTOFF
        ]
        catalog = next(
            (
                (row.get("datasets") or {}).get("a_share_catalog")
                for row in rows
                if (row.get("datasets") or {}).get("a_share_catalog")
            ),
            {},
        )
        prepared_base[symbol] = {
            "rows": rows,
            "meta": {
                "name": str((catalog or {}).get("name") or ""),
                "rqalpha_symbol": str((catalog or {}).get("rqalpha_symbol") or symbol),
            },
            "dataset_evidence": resolved["evidence"],
        }

    benchmark_rows = governance.fetch_index_price_history(
        "000300.XSHG", EVALUATION_START, OUTCOME_CUTOFF,
    )
    config = {
        "initial_cash": 1_000_000.0,
        "parameters": {"execution_price": "open"},
        "max_positions": 10,
        "portfolio_exposure": 0.90,
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "tax_rate": 0.001,
        "slippage_rate": 0.0005,
        "adjustment": "qfq",
        "date_window": {"start_date": EVALUATION_START, "end_date": OUTCOME_CUTOFF},
        "rebalance_policy": "event_driven",
        "capacity_replacement_policy": "incumbent_priority",
        "max_single_position_weight": 0.15,
    }
    strategy = {
        "strategy_id": "fujing_v2_v7_inactive_candidate",
        "latest_version": 7,
        "source_sha256": validation["source_sha256"],
        "execution_contract": "next_trade_date_open",
    }
    shared_results: list[dict[str, Any]] = []
    default_prepared: dict[str, dict[str, Any]] | None = None
    default_raw: dict[str, Any] | None = None
    trailing_090_prepared: dict[str, dict[str, Any]] | None = None
    trailing_090_raw: dict[str, Any] | None = None
    for label, override in SENSITIVITY:
        parameters = {**defaults, **override}
        prepared = _with_signals(prepared_base, strategy_module, parameters)
        raw, metrics = _run_shared_account(
            prepared, config, strategy, excluded, benchmark_rows=benchmark_rows,
        )
        shared_results.append({
            "label": label,
            "parameters": {
                key: parameters[key] for key in (
                    "winner_low_threshold", "winner_high_threshold",
                    "winner_spread_min", "amplitude_ratio_min", "trailing_stop",
                )
            },
            "metrics": metrics,
            "yearly_returns": raw["yearly_returns"],
            "stability": _stability(raw["yearly_returns"]),
            "final_holdings": len(raw["final_holdings"]),
        })
        if label == "default":
            default_prepared = prepared
            default_raw = raw
        if label == "trailing_0_900":
            trailing_090_prepared = prepared
            trailing_090_raw = raw

    assert default_prepared is not None and default_raw is not None
    assert trailing_090_prepared is not None and trailing_090_raw is not None
    ablation_results = []
    for label, override in ENTRY_ABLATIONS:
        parameters = {**defaults, **override}
        prepared = _with_signals(prepared_base, strategy_module, parameters)
        raw, metrics = _run_shared_account(
            prepared, config, strategy, excluded, benchmark_rows=benchmark_rows,
        )
        ablation_results.append({
            "label": label,
            "neutralized_parameter": override,
            "entry_events": _entry_event_count(prepared),
            "metrics": metrics,
            "stability": _stability(raw["yearly_returns"]),
            "interpretation": "single-condition development ablation; not a candidate",
        })
    risk_overlay_results = []
    for label, override in RISK_OVERLAYS:
        overlay_config = {**config, **override}
        raw, metrics = _run_shared_account(
            default_prepared, overlay_config, strategy, excluded,
            benchmark_rows=benchmark_rows,
        )
        risk_overlay_results.append({
            "label": label,
            "config_override": override,
            "metrics": metrics,
            "stability": _stability(raw["yearly_returns"]),
            "interpretation": "account-risk development overlay; entry signals unchanged",
        })
    v6_defaults = dict(v6_validation["parameter_defaults"])
    v6_prepared = _with_signals(prepared_base, v6_module, v6_defaults)
    _, v6_metrics = _run_shared_account(
        v6_prepared, config, {
            **strategy,
            "strategy_id": "fujing_v2_v6_frozen_comparison",
            "latest_version": 6,
            "source_sha256": v6_validation["source_sha256"],
        }, excluded, benchmark_rows=benchmark_rows,
    )
    v6_v7_comparison = _compare_versions(
        v6_prepared, default_prepared, strategy_module,
        v6_metrics=v6_metrics,
        v7_metrics=shared_results[0]["metrics"],
        v6_source_sha256=v6_validation["source_sha256"],
        v7_source_sha256=validation["source_sha256"],
    )
    independent = []
    for symbol, payload in default_prepared.items():
        _, metrics = _run_shared_account(
            {symbol: payload},
            {**config, "max_positions": 1},
            strategy,
            excluded,
            benchmark_rows=benchmark_rows,
        )
        independent.append({"symbol": symbol, **metrics})
    independent_returns = [float(item["total_returns"]) for item in independent]
    traded = [item for item in independent if int(item.get("trade_fill_count") or 0) > 0]

    payload = {
        "status": "passed",
        "policy": "development_performance_not_parameter_selection_not_oos",
        "source_sha256": validation["source_sha256"],
        "data_version_id": DATA_VERSION_ID,
        "artifact_bindings": factor_bindings,
        "cohort_symbol_count": len(symbols),
        "performance_eligible_symbol_count": len(prepared_base),
        "minimum_history_exclusions": excluded,
        "cohort_symbols_sha256": hashlib.sha256(
            json.dumps(symbols, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "windows": {
            "fetch_start": FETCH_START,
            "evaluation_start": EVALUATION_START,
            "last_signal_date": LAST_SIGNAL_DATE,
            "outcome_cutoff": OUTCOME_CUTOFF,
            "sealed_oos": {"start_date": OOS_START, "status": "not_viewed"},
        },
        "execution_assumptions": config,
        "benchmark": {
            "symbol": "000300.XSHG",
            "row_count": len(benchmark_rows),
            "status": default_raw["benchmark_status"],
        },
        "factor_rows_skipped_as_point_in_time_ineligible_across_bindings": eligibility_skips,
        "dynamic_factor_binding_start": {
            "policy": "later_of_common_evaluation_start_or_symbol_201st_valid_bar",
            "earliest": min(dynamic_binding_starts.values()),
            "latest": max(dynamic_binding_starts.values()),
            "symbols_delayed_after_common_start": sum(
                value > EVALUATION_START for value in dynamic_binding_starts.values()
            ),
        },
        "sensitivity_robustness": {
            "configuration_count": len(shared_results),
            "positive_total_return_count": sum(
                float(item["metrics"]["total_returns"]) > 0 for item in shared_results
            ),
            "positive_excess_return_count": sum(
                float(item["metrics"].get("excess_return") or 0) > 0
                for item in shared_results
            ),
            "max_drawdown_better_than_minus_30pct_count": sum(
                float(item["metrics"]["max_drawdown"]) > -0.30 for item in shared_results
            ),
            "total_return_range": [
                min(float(item["metrics"]["total_returns"]) for item in shared_results),
                max(float(item["metrics"]["total_returns"]) for item in shared_results),
            ],
            "interpretation": "development sensitivity only; no automatic winner selection",
        },
        "v6_v7_same_input_comparison": v6_v7_comparison,
        "exit_path_diagnostics": {
            "default_trailing_0_95": _trade_path_diagnostics(
                default_raw["trades"], default_prepared,
            ),
            "trailing_0_90": _trade_path_diagnostics(
                trailing_090_raw["trades"], trailing_090_prepared,
            ),
        },
        "position_weight_diagnostics": {
            "default_trailing_0_95": _position_weight_diagnostics(
                default_raw["positions"], default_raw["accounts"],
            ),
            "trailing_0_90": _position_weight_diagnostics(
                trailing_090_raw["positions"], trailing_090_raw["accounts"],
            ),
        },
        "exposure_matched_benchmark": {
            "default_trailing_0_95": _exposure_matched_benchmark(
                default_raw["accounts"], default_raw["benchmark_curve"],
                float(config["initial_cash"]), _performance_metrics,
            ),
            "trailing_0_90": _exposure_matched_benchmark(
                trailing_090_raw["accounts"], trailing_090_raw["benchmark_curve"],
                float(config["initial_cash"]), _performance_metrics,
            ),
        },
        "top_n_selection_diagnostics": {
            "default_trailing_0_95": _selection_path_diagnostics(
                default_prepared, int(config["max_positions"]),
            ),
            "trailing_0_90": _selection_path_diagnostics(
                trailing_090_prepared, int(config["max_positions"]),
            ),
        },
        "entry_condition_ablation": ablation_results,
        "account_risk_overlays": risk_overlay_results,
        "shared_portfolio_sensitivity": shared_results,
        "independent_default_summary": {
            "symbol_count": len(independent),
            "symbols_with_fills": len(traded),
            "positive_return_symbols": sum(value > 0 for value in independent_returns),
            "return_distribution": _percentiles(independent_returns),
            "median_trade_fills": statistics.median(
                int(item.get("trade_fill_count") or 0) for item in independent
            ),
        },
        "limitations": [
            "the deterministic 200-symbol cohort is not the full point-in-time universe",
            "sensitivity configurations were declared before this performance run and are not an automatic winner selection",
            "the shared portfolio runtime approximates price limits and does not model order-book impact or partial fills",
            "sell causes are reconstructed from same-date strategy and portfolio targets; realized PnL by cause is accounting attribution, not independent round-trip economic contribution",
            "no dates on or after 2025-01-01 were read",
            "V7 remains inactive and thresholds remain unfrozen",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _load_strategy(path: Path):
    spec = importlib.util.spec_from_file_location("fujing_v2_v7_candidate_analysis", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load inactive candidate source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _with_signals(base, strategy_module, parameters):
    prepared = {}
    for symbol, payload in base.items():
        weights, scores = strategy_module._build_signal_series(payload["rows"], parameters)
        prepared[symbol] = {**payload, "weights": weights, "scores": scores}
    return prepared


def _entry_event_count(prepared) -> int:
    count = 0
    for payload in prepared.values():
        previous = 0.0
        for weight in payload["weights"]:
            current = float(weight)
            count += current > 0 and previous <= 0
            previous = current
    return count


def _trade_path_diagnostics(
    trades: list[dict[str, Any]],
    prepared: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    intended_weights = {
        (str(symbol), _date(row)): float(weight)
        for symbol, payload in prepared.items()
        for row, weight in zip(payload["rows"], payload["weights"])
    }
    quantities: dict[str, int] = {}
    opened: dict[str, date] = {}
    holding_days: list[float] = []
    realized: list[float] = []
    by_year: dict[str, dict[str, float | int]] = {}
    by_sell_cause: dict[str, dict[str, float | int]] = {}
    for trade in sorted(trades, key=lambda row: str(row.get("trade_time") or "")):
        symbol = str(trade.get("order_book_id") or "")
        trade_date = date.fromisoformat(str(trade.get("trade_time") or "")[:10])
        quantity = int(trade.get("quantity") or 0)
        previous = quantities.get(symbol, 0)
        if str(trade.get("side") or "").upper() == "BUY":
            if previous <= 0 and quantity > 0:
                opened[symbol] = trade_date
            quantities[symbol] = previous + quantity
            continue
        quantities[symbol] = max(0, previous - quantity)
        pnl = trade.get("pnl")
        if pnl is not None:
            value = float(pnl)
            realized.append(value)
            notes = trade.get("notes") or {}
            recorded_cause = str(notes.get("sell_cause") or "")
            intended_weight = intended_weights.get((symbol, trade_date.isoformat()))
            target_weight = float(notes.get("target_weight") or 0.0)
            if recorded_cause:
                cause = recorded_cause
            elif intended_weight is None:
                cause = "unavailable"
            elif intended_weight <= 0:
                cause = "strategy_target_zero"
            elif target_weight <= 0:
                cause = "portfolio_capacity_exclusion"
            else:
                cause = "target_weight_rebalance"
            cause_summary = by_sell_cause.setdefault(
                cause,
                {
                    "sell_fills": 0, "realized_pnl": 0.0,
                    "winning_fills": 0, "losing_fills": 0,
                },
            )
            cause_summary["sell_fills"] = int(cause_summary["sell_fills"]) + 1
            cause_summary["realized_pnl"] = (
                float(cause_summary["realized_pnl"]) + value
            )
            cause_summary["winning_fills"] = (
                int(cause_summary["winning_fills"]) + (value > 0)
            )
            cause_summary["losing_fills"] = (
                int(cause_summary["losing_fills"]) + (value < 0)
            )
            year = trade_date.isoformat()[:4]
            annual = by_year.setdefault(
                year, {"sell_fills": 0, "realized_pnl": 0.0, "winning_fills": 0},
            )
            annual["sell_fills"] = int(annual["sell_fills"]) + 1
            annual["realized_pnl"] = float(annual["realized_pnl"]) + value
            annual["winning_fills"] = int(annual["winning_fills"]) + (value > 0)
        if quantities[symbol] == 0 and symbol in opened:
            holding_days.append(float((trade_date - opened.pop(symbol)).days))
    losses = sorted(value for value in realized if value < 0)
    wins = [value for value in realized if value > 0]
    total_loss = abs(sum(losses))
    return {
        "closed_holding_episodes": len(holding_days),
        "holding_calendar_days": _percentiles(holding_days),
        "realized_sell_fills": len(realized),
        "winning_sell_fills": len(wins),
        "losing_sell_fills": len(losses),
        "realized_pnl_total": round(sum(realized), 4),
        "mean_win": round(statistics.mean(wins), 4) if wins else None,
        "mean_loss": round(statistics.mean(losses), 4) if losses else None,
        "worst_10_loss_share": round(abs(sum(losses[:10])) / total_loss, 6)
        if total_loss else None,
        "sell_cause_contract": {
            "strategy_target_zero": "strategy emitted zero target on the sell date",
            "portfolio_capacity_exclusion": "strategy target remained positive but Top-N portfolio selection assigned zero",
            "target_weight_rebalance": "strategy and portfolio targets remained positive but required a smaller position",
            "single_position_weight_cap": "prior-close weight breach triggered next-tradable-open trim to the configured cap",
        },
        "by_sell_cause": {
            cause: {
                **values,
                "realized_pnl": round(float(values["realized_pnl"]), 4),
            }
            for cause, values in sorted(by_sell_cause.items())
        },
        "by_exit_year": {
            year: {
                **values,
                "realized_pnl": round(float(values["realized_pnl"]), 4),
            }
            for year, values in sorted(by_year.items())
        },
    }


def _selection_path_diagnostics(
    prepared: dict[str, dict[str, Any]],
    max_positions: int,
) -> dict[str, Any]:
    by_date: dict[str, dict[str, tuple[float, float | None]]] = {}
    for symbol, payload in prepared.items():
        scores = payload.get("scores") or [None] * len(payload["rows"])
        for row, weight, score in zip(payload["rows"], payload["weights"], scores):
            trade_date = _date(row)
            if not trade_date or float(weight) <= 0:
                continue
            by_date.setdefault(trade_date, {})[str(symbol)] = (
                float(weight), float(score) if score is not None else None,
            )
    previous: set[str] = set()
    active_counts: list[float] = []
    selected_counts: list[float] = []
    consecutive_jaccards: list[float] = []
    run_lengths: dict[str, int] = {}
    completed_runs: list[float] = []
    selected_entries = 0
    selected_exits = 0
    capacity_displacements = 0
    strategy_target_zero_exits = 0
    dates_over_capacity = 0
    for trade_date in sorted(by_date):
        active = by_date[trade_date]
        selected = set(sorted(
            active,
            key=lambda symbol: (
                -(active[symbol][1] if active[symbol][1] is not None else active[symbol][0]),
                symbol,
            ),
        )[:max_positions])
        active_counts.append(float(len(active)))
        selected_counts.append(float(len(selected)))
        dates_over_capacity += len(active) > max_positions
        if previous:
            union = previous | selected
            consecutive_jaccards.append(
                len(previous & selected) / len(union) if union else 1.0
            )
        entries = selected - previous
        exits = previous - selected
        selected_entries += len(entries)
        selected_exits += len(exits)
        capacity_displacements += sum(symbol in active for symbol in exits)
        strategy_target_zero_exits += sum(symbol not in active for symbol in exits)
        for symbol in exits:
            completed_runs.append(float(run_lengths.pop(symbol, 0)))
        for symbol in selected:
            run_lengths[symbol] = run_lengths.get(symbol, 0) + 1
        previous = selected
    completed_runs.extend(float(value) for value in run_lengths.values())
    return {
        "trade_date_count": len(by_date),
        "max_positions": max_positions,
        "active_candidate_count": _percentiles(active_counts),
        "selected_position_count": _percentiles(selected_counts),
        "dates_over_capacity": dates_over_capacity,
        "dates_over_capacity_ratio": round(dates_over_capacity / len(by_date), 6)
        if by_date else None,
        "selected_entries": selected_entries,
        "selected_exits": selected_exits,
        "capacity_displacements": capacity_displacements,
        "strategy_target_zero_exits": strategy_target_zero_exits,
        "selection_run_trade_days": _percentiles(completed_runs),
        "consecutive_selection_jaccard": _percentiles(consecutive_jaccards),
        "interpretation": "signal-and-score selection path only; no execution or fill assumptions",
    }


def _position_weight_diagnostics(
    positions: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    weights_by_date: dict[str, list[float]] = {}
    for row in positions:
        snapshot_date = str(row.get("snapshot_time") or "")[:10]
        weight = float(row.get("weight") or 0.0)
        if snapshot_date and weight > 0:
            weights_by_date.setdefault(snapshot_date, []).append(weight)
    max_weights: list[float] = []
    gross_exposures: list[float] = []
    holding_counts: list[float] = []
    for row in accounts:
        snapshot_date = str(row.get("snapshot_time") or "")[:10]
        weights = weights_by_date.get(snapshot_date, [])
        max_weights.append(max(weights) if weights else 0.0)
        total_value = float(row.get("total_value") or 0.0)
        market_value = float(row.get("market_value") or 0.0)
        gross_exposures.append(market_value / total_value if total_value > 0 else 0.0)
        holding_counts.append(float(len(weights)))
    return {
        "account_date_count": len(accounts),
        "single_position_max_weight": _percentiles(max_weights),
        "gross_exposure": _percentiles(gross_exposures),
        "holding_count": _percentiles(holding_counts),
        "single_position_weight_breaches": {
            "above_10pct": sum(value > 0.10 for value in max_weights),
            "above_12pct": sum(value > 0.12 for value in max_weights),
            "above_15pct": sum(value > 0.15 for value in max_weights),
            "above_18pct": sum(value > 0.18 for value in max_weights),
            "above_20pct": sum(value > 0.20 for value in max_weights),
        },
        "maximum_observed_single_position_weight": round(max(max_weights), 8)
        if max_weights else None,
        "interpretation": "end-of-day account snapshots under event-driven fixed-slot entry sizing",
    }


def _exposure_matched_benchmark(
    accounts: list[dict[str, Any]],
    benchmark_curve: list[dict[str, Any]],
    initial_cash: float,
    performance_metrics,
) -> dict[str, Any]:
    if len(accounts) != len(benchmark_curve) or len(accounts) < 2:
        return {"status": "unavailable", "reason": "account_benchmark_alignment_failed"}
    matched_values = [initial_cash]
    exposures: list[float] = []
    matched_daily_returns: list[tuple[str, float]] = []
    portfolio_daily_returns: list[tuple[str, float]] = []
    benchmark_values = [float(row.get("value") or 0.0) for row in benchmark_curve]
    for index, account in enumerate(accounts):
        total_value = float(account.get("total_value") or 0.0)
        market_value = float(account.get("market_value") or 0.0)
        exposures.append(market_value / total_value if total_value > 0 else 0.0)
        if index == 0:
            continue
        previous_benchmark = benchmark_values[index - 1]
        benchmark_return = (
            benchmark_values[index] / previous_benchmark - 1.0
            if previous_benchmark > 0 else 0.0
        )
        prior_exposure = exposures[index - 1]
        matched_return = prior_exposure * benchmark_return
        matched_values.append(
            matched_values[-1] * (1.0 + matched_return)
        )
        trade_date = str(account.get("snapshot_time") or "")[:10]
        matched_daily_returns.append((trade_date, matched_return))
        previous_portfolio = float(accounts[index - 1].get("total_value") or 0.0)
        current_portfolio = float(account.get("total_value") or 0.0)
        portfolio_daily_returns.append((
            trade_date,
            current_portfolio / previous_portfolio - 1.0
            if previous_portfolio > 0 else 0.0,
        ))
    portfolio_final = float(accounts[-1].get("total_value") or initial_cash)
    matched_final = matched_values[-1]
    matched = performance_metrics(matched_values, risk_free_rate=0.0)
    portfolio_return = portfolio_final / initial_cash - 1.0
    matched_return = matched_final / initial_cash - 1.0
    return {
        "status": "ready",
        "contract": "prior_close_portfolio_exposure_times_next_benchmark_return_cash_return_zero",
        "average_gross_exposure": round(statistics.mean(exposures), 6),
        "median_gross_exposure": round(statistics.median(exposures), 6),
        "exposure_matched_benchmark": matched,
        "portfolio_total_return": round(portfolio_return, 6),
        "portfolio_excess_over_exposure_matched_benchmark": round(
            (1.0 + portfolio_return) / (1.0 + matched_return) - 1.0,
            6,
        ),
        "yearly_exposure_matched_comparison": _compound_return_comparison_by_year(
            portfolio_daily_returns, matched_daily_returns,
        ),
        "limitations": [
            "cash return is fixed at zero",
            "exposure matching controls market allocation only and does not estimate sector or style beta",
            "dynamic exposure is itself an outcome of the strategy",
        ],
    }


def _compound_return_comparison_by_year(
    portfolio_returns: list[tuple[str, float]],
    matched_returns: list[tuple[str, float]],
) -> list[dict[str, Any]]:
    portfolio_by_year: dict[str, list[float]] = {}
    matched_by_year: dict[str, list[float]] = {}
    for trade_date, value in portfolio_returns:
        portfolio_by_year.setdefault(trade_date[:4], []).append(value)
    for trade_date, value in matched_returns:
        matched_by_year.setdefault(trade_date[:4], []).append(value)
    rows = []
    for year in sorted(set(portfolio_by_year) & set(matched_by_year)):
        portfolio = _compound_returns(portfolio_by_year[year])
        matched = _compound_returns(matched_by_year[year])
        rows.append({
            "year": year,
            "portfolio_return": round(portfolio, 6),
            "exposure_matched_benchmark_return": round(matched, 6),
            "multiplicative_excess": round(
                (1.0 + portfolio) / (1.0 + matched) - 1.0,
                6,
            ),
        })
    return rows


def _compound_returns(values: list[float]) -> float:
    result = 1.0
    for value in values:
        result *= 1.0 + value
    return result - 1.0


def _date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("trade_date") or "")[:10]


def _percentiles(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "p05": None, "p25": None, "p50": None, "p75": None, "p95": None}
    ordered = sorted(values)
    def pick(fraction: float) -> float:
        return ordered[round((len(ordered) - 1) * fraction)]
    return {
        "count": len(ordered), "p05": pick(0.05), "p25": pick(0.25),
        "p50": pick(0.50), "p75": pick(0.75), "p95": pick(0.95),
    }


def _stability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [dict(row) for row in rows]
    blocks = (("2016-2018", 2016, 2018), ("2019-2021", 2019, 2021), ("2022-2024", 2022, 2024))
    return {
        "positive_year_count": sum(float(row["portfolio_return"]) > 0 for row in normalized),
        "benchmark_outperformance_year_count": sum(
            float(row["excess_return"]) > 0 for row in normalized
        ),
        "best_year": max(normalized, key=lambda row: float(row["portfolio_return"]))["year"],
        "worst_year": min(normalized, key=lambda row: float(row["portfolio_return"]))["year"],
        "three_year_blocks": [
            {
                "period": label,
                "portfolio_return": round(
                    _compound(
                        float(row["portfolio_return"])
                        for row in normalized
                        if start <= int(row["year"]) <= end
                    ),
                    6,
                ),
                "excess_return": round(
                    _compound(
                        float(row["portfolio_return"])
                        for row in normalized
                        if start <= int(row["year"]) <= end
                    )
                    - _compound(
                        float(row["benchmark_return"])
                        for row in normalized
                        if start <= int(row["year"]) <= end
                    ),
                    6,
                ),
            }
            for label, start, end in blocks
        ],
    }


def _compound(values) -> float:
    result = 1.0
    for value in values:
        result *= 1.0 + value
    return result - 1.0


def _compare_versions(
    v6_prepared,
    v7_prepared,
    v7_module,
    *,
    v6_metrics,
    v7_metrics,
    v6_source_sha256,
    v7_source_sha256,
) -> dict[str, Any]:
    v6_active: set[tuple[str, str]] = set()
    v7_active: set[tuple[str, str]] = set()
    v6_entries: set[tuple[str, str]] = set()
    v7_entries: set[tuple[str, str]] = set()
    v6_entries_by_year: Counter[str] = Counter()
    v7_entries_by_year: Counter[str] = Counter()
    v6_only_reasons: Counter[str] = Counter()
    for symbol in sorted(v6_prepared):
        rows = v6_prepared[symbol]["rows"]
        v6_weights = v6_prepared[symbol]["weights"]
        v7_weights = v7_prepared[symbol]["weights"]
        for index, row in enumerate(rows):
            trade_date = _date(row)
            key = (symbol, trade_date)
            if float(v6_weights[index]) > 0:
                v6_active.add(key)
            if float(v7_weights[index]) > 0:
                v7_active.add(key)
            v6_entry = float(v6_weights[index]) > 0 and (
                index == 0 or float(v6_weights[index - 1]) <= 0
            )
            v7_entry = float(v7_weights[index]) > 0 and (
                index == 0 or float(v7_weights[index - 1]) <= 0
            )
            if v6_entry:
                v6_entries.add(key)
                v6_entries_by_year[trade_date[:4]] += 1
            if v7_entry:
                v7_entries.add(key)
                v7_entries_by_year[trade_date[:4]] += 1
            if v6_entry and not v7_entry:
                if float(v7_weights[index]) > 0:
                    v6_only_reasons["v7_already_active"] += 1
                    continue
                signal_row = rows[max(0, index - 1)]
                if not v7_module._is_allowed_security(signal_row):
                    v6_only_reasons["point_in_time_universe_exclusion"] += 1
                    continue
                factors = (signal_row.get("datasets") or {}).get("factor_values") or {}
                if any(not isinstance(factors.get(factor_id), dict) for factor_id in FACTORS):
                    v6_only_reasons["governed_factor_unavailable"] += 1
                    continue
                v6_only_reasons["formula_or_threshold_semantic_delta"] += 1
    active_union = v6_active | v7_active
    entry_union = v6_entries | v7_entries
    return {
        "policy": "same_rows_same_dates_same_execution_development_only",
        "source_sha256": {"v6": v6_source_sha256, "v7": v7_source_sha256},
        "active_position_rows": {
            "v6": len(v6_active),
            "v7": len(v7_active),
            "overlap": len(v6_active & v7_active),
            "jaccard": round(len(v6_active & v7_active) / len(active_union), 6)
            if active_union else None,
        },
        "entry_events": {
            "v6": len(v6_entries),
            "v7": len(v7_entries),
            "same_symbol_same_date": len(v6_entries & v7_entries),
            "jaccard": round(len(v6_entries & v7_entries) / len(entry_union), 6)
            if entry_union else None,
            "v6_only_reason_counts": dict(sorted(v6_only_reasons.items())),
            "v6_by_year": dict(sorted(v6_entries_by_year.items())),
            "v7_by_year": dict(sorted(v7_entries_by_year.items())),
        },
        "shared_portfolio_metrics": {
            "v6": v6_metrics,
            "v7": v7_metrics,
        },
        "interpretation_boundary": [
            "V6 is executed against the V7 governed point-in-time input rows for comparability",
            "differences combine frozen V6 inline formulas with V7 governed artifacts and semantic corrections",
            "this is not an OOS result and does not select a preferred parameter set",
        ],
    }


if __name__ == "__main__":
    main()
