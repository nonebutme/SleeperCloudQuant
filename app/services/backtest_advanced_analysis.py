"""Versioned evidence builders for backtest report stages 80-85."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


def build_advanced_analysis(
    *,
    account_rows: Sequence[Mapping[str, Any]],
    benchmark_curve: Sequence[Mapping[str, Any]],
    excess_curve: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    raw_result: Mapping[str, Any],
    extra_config: Mapping[str, Any],
) -> dict[str, Any]:
    equity = _curve(account_rows, ("total_value", "unit_net_value", "value"))
    benchmark = _curve(benchmark_curve, ("value", "close", "unit_net_value"))
    excess = _curve(excess_curve, ("value", "unit_net_value", "excess_return"))
    monthly = _monthly_returns(equity)
    excess_drawdown = _drawdown_curve(excess)
    regimes = _market_regimes(equity, benchmark)
    execution = _execution_quality(trades)
    costs = _cost_capacity_stress(
        trades=trades,
        equity=equity,
        total_return=_number(metrics.get("total_returns"), metrics.get("total_return")),
        extra_config=extra_config,
    )
    robustness = _robustness(equity)
    signal = dict(raw_result.get("signal_evidence") or {})
    price_bars = [dict(row) for row in raw_result.get("price_bars") or [] if isinstance(row, Mapping)]
    return {
        "version": "stage80-85-evidence-v1",
        "signal_evidence": signal or {
            "status": "unavailable",
            "reason": "historical_run_did_not_persist_point_in_time_raw_scores",
            "version": "stage80-point-in-time-signal-v1",
        },
        "monthly_return_heatmap": monthly,
        "excess_drawdown_curve": excess_drawdown,
        "market_regimes": regimes,
        "execution_quality": execution,
        "cost_capacity_stress": costs,
        "robustness": robustness,
        "price_bars": price_bars,
        "parameter_sensitivity": {
            "status": "unavailable",
            "reason": "parameter_grid_experiment_not_bound_to_this_run",
            "required_evidence": "versioned_parameter_grid_with_identical_data_snapshot",
        },
        "report_governance": {
            "version": "stage85-report-productization-v1",
            "evidence_level": _evidence_level(equity, trades, benchmark),
            "task_version_bound": bool(extra_config),
            "data_version": _data_version(extra_config),
            "algorithm_version": signal.get("signal_version"),
            "disclaimer": "本报告仅用于本地量化研究，不构成投资建议、收益承诺或实盘交易指令。",
            "export_formats": ["pdf", "csv", "svg", "png"],
            "missing_values_are_not_zero": True,
        },
    }


def _curve(rows: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> list[tuple[str, float]]:
    result: list[tuple[str, float]] = []
    for row in rows:
        date = str(row.get("date") or row.get("snapshot_time") or row.get("trade_date") or "")[:10]
        value = next((_number(row.get(key)) for key in keys if _number(row.get(key)) is not None), None)
        if date and value is not None and value > 0:
            result.append((date, value))
    by_date = {date: value for date, value in result}
    return sorted(by_date.items())


def _monthly_returns(curve: Sequence[tuple[str, float]]) -> dict[str, Any]:
    buckets: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in curve:
        buckets[row[0][:7]].append(row)
    rows = []
    previous = curve[0][1] if curve else None
    for month, values in sorted(buckets.items()):
        end = values[-1][1]
        value = end / previous - 1.0 if previous else None
        rows.append({"month": month, "year": month[:4], "month_number": int(month[5:7]), "return": value})
        previous = end
    return {
        "status": "ready" if len(rows) >= 2 else "insufficient_sample",
        "rows": rows,
        "month_count": len(rows),
        "methodology": "month-end account value divided by previous month-end account value minus one",
    }


def _drawdown_curve(curve: Sequence[tuple[str, float]]) -> list[dict[str, Any]]:
    peak = None
    rows = []
    for date, value in curve:
        peak = value if peak is None else max(peak, value)
        rows.append({"date": date, "value": value / peak - 1.0 if peak else None})
    return rows


def _market_regimes(
    equity: Sequence[tuple[str, float]],
    benchmark: Sequence[tuple[str, float]],
) -> dict[str, Any]:
    if len(benchmark) < 22:
        return {
            "status": "unavailable",
            "reason": "at_least_22_aligned_benchmark_points_required",
            "rows": [],
            "look_ahead_control": "labels use trailing benchmark returns available before each observation",
        }
    equity_by_date = dict(equity)
    benchmark_returns = _returns(benchmark)
    labelled: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for index in range(20, len(benchmark_returns)):
        date, market_return = benchmark_returns[index]
        trailing = [value for _, value in benchmark_returns[index - 20:index]]
        trend = math.prod(1.0 + value for value in trailing) - 1.0
        volatility = statistics.pstdev(trailing)
        trend_label = "上涨" if trend > 0.03 else "下跌" if trend < -0.03 else "震荡"
        vol_label = "高波动" if volatility > statistics.median(
            [statistics.pstdev([v for _, v in benchmark_returns[max(0, cursor - 20):cursor]]) for cursor in range(20, index + 1)]
        ) else "低波动"
        previous_date = benchmark[index][0]
        if date not in equity_by_date or previous_date not in equity_by_date or not equity_by_date[previous_date]:
            continue
        portfolio_return = equity_by_date[date] / equity_by_date[previous_date] - 1.0
        labelled[f"{trend_label}/{vol_label}"].append((portfolio_return, market_return))
    rows = []
    for regime, values in sorted(labelled.items()):
        portfolio_values = [item[0] for item in values]
        market_values = [item[1] for item in values]
        rows.append({
            "regime": regime,
            "sample_size": len(values),
            "portfolio_return": math.prod(1.0 + value for value in portfolio_values) - 1.0,
            "benchmark_return": math.prod(1.0 + value for value in market_values) - 1.0,
            "excess_return": math.prod(1.0 + a - b for a, b in values) - 1.0,
            "win_rate": sum(value > 0 for value in portfolio_values) / len(portfolio_values),
        })
    return {
        "status": "ready" if rows else "insufficient_aligned_sample",
        "rows": rows,
        "look_ahead_control": "trend and volatility labels only use the prior 20 benchmark returns",
    }


def _execution_quality(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for trade in trades:
        notes = trade.get("notes") if isinstance(trade.get("notes"), Mapping) else {}
        price = _number(trade.get("price"))
        vwap = _number(notes.get("market_vwap"))
        side = str(trade.get("side") or "").upper()
        if price is None or vwap is None or vwap <= 0:
            continue
        signed = (price / vwap - 1.0) * (1.0 if side == "BUY" else -1.0)
        volume = _number(notes.get("market_volume"))
        quantity = _number(trade.get("quantity"))
        rows.append({
            "trade_time": trade.get("trade_time"),
            "symbol": trade.get("order_book_id"),
            "side": side,
            "execution_price": price,
            "market_vwap": vwap,
            "signed_deviation": signed,
            "participation_rate": quantity / volume if quantity is not None and volume else None,
        })
    deviations = [row["signed_deviation"] for row in rows]
    return {
        "status": "ready" if rows else "unavailable",
        "reason": None if rows else "trade_rows_do_not_contain_reconciled_market_vwap",
        "filled_trade_count": len(trades),
        "vwap_evidence_count": len(rows),
        "coverage_ratio": len(rows) / len(trades) if trades else None,
        "simulated_vwap_deviation": statistics.mean(deviations) if deviations else None,
        "rows": rows,
        "definition": "positive signed deviation means execution was worse than market VWAP",
    }


def _cost_capacity_stress(
    *,
    trades: Sequence[Mapping[str, Any]],
    equity: Sequence[tuple[str, float]],
    total_return: float | None,
    extra_config: Mapping[str, Any],
) -> dict[str, Any]:
    initial_capital = equity[0][1] if equity else None
    rqalpha = extra_config.get("rqalpha_local") if isinstance(extra_config.get("rqalpha_local"), Mapping) else {}
    commission_rate = abs(_number(rqalpha.get("commission_rate")) or 0.0)
    tax_rate = abs(_number(rqalpha.get("tax_rate")) or 0.0)
    slippage_rate = abs(_number(rqalpha.get("slippage_rate")) or 0.0)
    turnover = sum(abs(_number(row.get("amount")) or 0.0) for row in trades)
    cost_rows = []
    for commission_multiplier in (0.5, 1.0, 2.0):
        for slippage_multiplier in (0.5, 1.0, 2.0):
            analytical_cost = turnover * (
                commission_rate * commission_multiplier + tax_rate + slippage_rate * slippage_multiplier
            )
            cost_rows.append({
                "commission_multiplier": commission_multiplier,
                "slippage_multiplier": slippage_multiplier,
                "analytical_cost": analytical_cost,
                "analytical_return_after_cost": (
                    total_return - analytical_cost / initial_capital
                    if total_return is not None and initial_capital
                    else None
                ),
                "evidence_type": "analytical_stress_not_backtest_rerun",
            })
    participations = []
    for trade in trades:
        notes = trade.get("notes") if isinstance(trade.get("notes"), Mapping) else {}
        volume = _number(notes.get("market_volume"))
        quantity = _number(trade.get("quantity"))
        if volume and quantity is not None:
            participations.append(quantity / volume)
    capacity_rows = [
        {
            "capital_multiplier": multiplier,
            "projected_max_participation": max(participations) * multiplier if participations else None,
            "within_10pct_volume_limit": max(participations) * multiplier <= 0.10 if participations else None,
        }
        for multiplier in (1, 2, 5, 10)
    ]
    return {
        "status": "ready" if trades and initial_capital else "unavailable",
        "cost_matrix": cost_rows,
        "capacity": {
            "status": "ready" if participations else "unavailable",
            "reason": None if participations else "market_volume_not_persisted_with_trades",
            "maximum_observed_participation": max(participations) if participations else None,
            "scenarios": capacity_rows,
        },
        "extreme_unfilled_scenario": {
            "status": "defined",
            "rule": "orders projected above 10% daily volume are marked capacity constrained; returns are not fabricated",
        },
    }


def _robustness(curve: Sequence[tuple[str, float]]) -> dict[str, Any]:
    if len(curve) < 60:
        return {
            "status": "insufficient_sample",
            "reason": "at_least_60_account_points_required",
            "segments": [],
        }
    boundaries = [0, len(curve) * 6 // 10, len(curve) * 8 // 10, len(curve) - 1]
    labels = ["training", "validation", "out_of_sample"]
    segments = []
    for label, start, end in zip(labels, boundaries, boundaries[1:]):
        values = curve[start:end + 1]
        segments.append(_segment_metrics(label, values))
    window = max(20, len(curve) // 5)
    rolling = [
        _segment_metrics(f"window_{index + 1}", curve[start:start + window])
        for index, start in enumerate(range(0, len(curve) - window + 1, window))
    ]
    returns = [row["total_return"] for row in rolling if row.get("total_return") is not None]
    return {
        "status": "ready",
        "split": {"training": "60%", "validation": "20%", "out_of_sample": "20%"},
        "segments": segments,
        "walk_forward_windows": rolling,
        "stability": {
            "positive_window_ratio": sum(value > 0 for value in returns) / len(returns) if returns else None,
            "return_dispersion": statistics.pstdev(returns) if len(returns) > 1 else None,
        },
        "overfitting_warning": (
            "out_of_sample_underperforms_training"
            if segments[-1].get("annualized_return") is not None
            and segments[0].get("annualized_return") is not None
            and segments[-1]["annualized_return"] < segments[0]["annualized_return"]
            else None
        ),
        "multiple_testing": {
            "status": "not_applicable",
            "reason": "single_parameter_set; correction requires a bound parameter-grid experiment",
        },
    }


def _segment_metrics(label: str, curve: Sequence[tuple[str, float]]) -> dict[str, Any]:
    if len(curve) < 2 or not curve[0][1]:
        return {"segment": label, "status": "insufficient_sample"}
    total = curve[-1][1] / curve[0][1] - 1.0
    periods = len(curve) - 1
    annualized = (1.0 + total) ** (252.0 / periods) - 1.0 if total > -1 else -1.0
    returns = [value for _, value in _returns(curve)]
    volatility = statistics.pstdev(returns) * math.sqrt(252) if len(returns) > 1 else None
    sharpe = statistics.mean(returns) / statistics.pstdev(returns) * math.sqrt(252) if len(returns) > 1 and statistics.pstdev(returns) else None
    drawdown = _drawdown_curve(curve)
    return {
        "segment": label,
        "status": "ready",
        "start_date": curve[0][0],
        "end_date": curve[-1][0],
        "sample_size": len(curve),
        "total_return": total,
        "annualized_return": annualized,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": min((row["value"] for row in drawdown if row["value"] is not None), default=None),
    }


def _returns(curve: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
    return [
        (current[0], current[1] / previous[1] - 1.0)
        for previous, current in zip(curve, curve[1:])
        if previous[1]
    ]


def _evidence_level(
    equity: Sequence[tuple[str, float]],
    trades: Sequence[Mapping[str, Any]],
    benchmark: Sequence[tuple[str, float]],
) -> str:
    score = (2 if len(equity) >= 60 else 1 if len(equity) >= 2 else 0)
    score += 1 if trades else 0
    score += 1 if len(benchmark) >= 2 else 0
    return "high" if score >= 4 else "medium" if score >= 2 else "low"


def _data_version(extra_config: Mapping[str, Any]) -> Any:
    trace = extra_config.get("data_asset_trace") if isinstance(extra_config.get("data_asset_trace"), Mapping) else {}
    asset = trace.get("asset") if isinstance(trace.get("asset"), Mapping) else {}
    return asset.get("data_version")


def _number(*values: Any) -> float | None:
    for value in values:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    return None
