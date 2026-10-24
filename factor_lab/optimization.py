"""Deterministic optimization over one immutable factor artifact."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Mapping, Sequence


def optimize_fixed_artifact(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_field: str = "aligned_value",
    forward_horizons: Sequence[int] = (5,),
    group_counts: Sequence[int] = (3, 5, 10),
    one_side_rates: Sequence[float] = (0.0,),
    min_cross_section_size: int = 5,
) -> dict[str, Any]:
    """Compare governed long-short candidates without changing artifact values."""

    if value_field not in {"aligned_value", "value"}:
        raise ValueError("value_field must be aligned_value or value")
    horizons = sorted({int(item) for item in forward_horizons})
    groups = sorted({int(item) for item in group_counts})
    rates = sorted({float(item) for item in one_side_rates})
    if not horizons or any(item <= 0 for item in horizons):
        raise ValueError("forward_horizons must contain positive integers")
    if not groups or any(item < 2 or item > 20 for item in groups):
        raise ValueError("group_counts must be between 2 and 20")
    if not rates or any(item < 0 or item > 0.05 for item in rates):
        raise ValueError("one_side_rates must be between 0 and 0.05")
    minimum = max(2, int(min_cross_section_size))

    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        score = _finite(raw.get(value_field))
        if score is None:
            continue
        returns = raw.get("forward_returns")
        if not isinstance(returns, Mapping):
            continue
        by_date[str(raw.get("trade_date") or "")].append(
            {
                "symbol": str(raw.get("symbol") or ""),
                "score": score,
                "forward_returns": dict(returns),
            }
        )

    candidates: list[dict[str, Any]] = []
    for horizon in horizons:
        for group_count in groups:
            for rate in rates:
                candidate = _evaluate_candidate(
                    by_date,
                    horizon=horizon,
                    group_count=group_count,
                    one_side_rate=rate,
                    min_cross_section_size=max(minimum, group_count),
                )
                if candidate is not None:
                    candidates.append(candidate)
    if not candidates:
        raise ValueError("artifact has no comparable forward-return observations")

    ranked = sorted(
        candidates,
        key=lambda item: (
            -float(item["objective_value"]),
            -int(item["sample_date_count"]),
            int(item["forward_horizon"]),
            int(item["group_count"]),
            float(item["one_side_rate"]),
        ),
    )
    return {
        "status": "ready",
        "objective": "mean_net_top_bottom_return",
        "value_field": value_field,
        "candidate_count": len(ranked),
        "best_candidate": ranked[0],
        "candidates": ranked,
        "semantics": {
            "ranking": "higher_value_is_better",
            "gross_return": "top_group_mean_forward_return_minus_bottom_group_mean_forward_return",
            "turnover": "top_and_bottom_membership_change_sum",
            "cost": "turnover_times_one_side_rate",
            "scope": "historical_factor_research_estimate_only",
        },
    }


def _evaluate_candidate(
    by_date: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    horizon: int,
    group_count: int,
    one_side_rate: float,
    min_cross_section_size: int,
) -> dict[str, Any] | None:
    series: list[dict[str, Any]] = []
    previous_top: set[str] | None = None
    previous_bottom: set[str] | None = None
    for trade_date, raw_rows in sorted(by_date.items()):
        usable = []
        for row in raw_rows:
            value = _finite(dict(row.get("forward_returns") or {}).get(str(horizon)))
            if value is not None:
                usable.append({**dict(row), "forward_return": value})
        if len(usable) < min_cross_section_size:
            continue
        ranked = sorted(usable, key=lambda row: (float(row["score"]), str(row["symbol"])))
        bucket_size = max(1, len(ranked) // group_count)
        bottom_rows = ranked[:bucket_size]
        top_rows = ranked[-bucket_size:]
        top = {str(row["symbol"]) for row in top_rows}
        bottom = {str(row["symbol"]) for row in bottom_rows}
        turnover = 0.0
        if previous_top is not None and previous_bottom is not None:
            turnover = (
                1.0 - len(previous_top & top) / max(1, len(previous_top))
                + 1.0 - len(previous_bottom & bottom) / max(1, len(previous_bottom))
            )
        gross = statistics.fmean(float(row["forward_return"]) for row in top_rows) - statistics.fmean(
            float(row["forward_return"]) for row in bottom_rows
        )
        cost = turnover * one_side_rate
        series.append(
            {
                "trade_date": trade_date,
                "sample_count": len(ranked),
                "bucket_size": bucket_size,
                "gross_return": gross,
                "turnover": turnover,
                "estimated_cost": cost,
                "net_return": gross - cost,
            }
        )
        previous_top = top
        previous_bottom = bottom
    if not series:
        return None
    net = [float(item["net_return"]) for item in series]
    gross = [float(item["gross_return"]) for item in series]
    nav = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in net:
        nav *= 1.0 + value
        peak = max(peak, nav)
        max_drawdown = min(max_drawdown, nav / peak - 1.0)
    mean_net = statistics.fmean(net)
    volatility = statistics.pstdev(net) if len(net) > 1 else 0.0
    return {
        "forward_horizon": horizon,
        "group_count": group_count,
        "one_side_rate": one_side_rate,
        "sample_date_count": len(series),
        "mean_gross_return": statistics.fmean(gross),
        "mean_net_return": mean_net,
        "objective_value": mean_net,
        "net_return_volatility": volatility,
        "net_return_t_like": (
            mean_net / (volatility / math.sqrt(len(net))) if volatility > 0 else None
        ),
        "final_nav": nav,
        "max_drawdown": max_drawdown,
        "series": series,
    }


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
