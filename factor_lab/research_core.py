"""Deterministic factor-research calculations without I/O dependencies."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

from .calculators.fujing_features import (
    FUJING_FEATURE_DEFINITIONS,
    calculate_fujing_feature,
)
from .expression_factor import calculate_expression_factor


_FACTOR_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "factor_id": "close_to_close_return_1d",
        "factor_version": "v1",
        "name": "1 日收益",
        "category": "动量",
        "formula": "close_t / close_t-1 - 1",
        "description": "最近一个交易日的收盘到收盘收益。",
        "input_fields": ["close"],
        "minimum_history": 2,
        "direction": "positive",
        "stage": "87.1",
        "parameters": {},
    },
    {
        "factor_id": "momentum_20d",
        "factor_version": "v1",
        "name": "20 日动量",
        "category": "动量",
        "formula": "close_t / close_t-20 - 1",
        "description": "当前收盘相对 20 个交易日前收盘的累计变化。",
        "input_fields": ["close"],
        "minimum_history": 21,
        "direction": "positive",
        "stage": "87.1",
        "parameters": {"window": 20},
    },
    {
        "factor_id": "momentum_60d",
        "factor_version": "v1",
        "name": "60 日动量",
        "category": "动量",
        "formula": "close_t / close_t-60 - 1",
        "description": "当前收盘相对 60 个交易日前收盘的累计变化。",
        "input_fields": ["close"],
        "minimum_history": 61,
        "direction": "positive",
        "stage": "87.1",
        "parameters": {"window": 60},
    },
    {
        "factor_id": "volatility_20d",
        "factor_version": "v1",
        "name": "20 日波动率",
        "category": "风险",
        "formula": "pstdev(return_1d[t-19:t])",
        "description": "最近 20 个交易日的一日收益总体标准差。",
        "input_fields": ["close"],
        "minimum_history": 21,
        "direction": "negative",
        "stage": "87.1",
        "parameters": {"window": 20},
    },
    {
        "factor_id": "close_to_ma20_bias",
        "factor_version": "v1",
        "name": "MA20 乖离",
        "category": "技术",
        "formula": "close_t / mean(close_t...close_t-19) - 1",
        "description": "收盘价相对 20 日简单移动平均的偏离。",
        "input_fields": ["close"],
        "minimum_history": 20,
        "direction": "positive",
        "stage": "87.1",
        "parameters": {"window": 20},
    },
    {
        "factor_id": "amount_strength_20d",
        "factor_version": "v1",
        "name": "20 日成交额强度",
        "category": "量价",
        "formula": "amount_t / mean(amount_t...amount_t-19) - 1",
        "description": "当日成交额相对 20 日平均成交额的强度。",
        "input_fields": ["amount"],
        "minimum_history": 20,
        "direction": "positive",
        "stage": "87.1",
        "parameters": {"window": 20},
    },
)

_FACTOR_DEFINITIONS = _FACTOR_DEFINITIONS + tuple(
    {
        **dict(item),
        "factor_version": "v1",
        "category": "拂经 V7 候选特征",
        "stage": "fujing-v7-candidate",
    }
    for item in FUJING_FEATURE_DEFINITIONS
)


def list_research_factor_definitions() -> list[dict[str, Any]]:
    return [
        {**dict(item), "definition_type": "builtin", "status": "published"}
        for item in _FACTOR_DEFINITIONS
    ]


def require_research_factor(factor_id: str) -> dict[str, Any]:
    normalized = str(factor_id or "").strip().lower()
    for definition in _FACTOR_DEFINITIONS:
        if definition["factor_id"] == normalized:
            return dict(definition)
    raise ValueError(f"unsupported factor_id: {factor_id}")


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def calculate_factor(
    factor_id: str,
    bars: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    """Calculate one P0 factor over ascending per-symbol bars."""

    factor_id = str(factor_id or "").strip().lower()
    definition = require_research_factor(factor_id)
    if factor_id in {item["factor_id"] for item in FUJING_FEATURE_DEFINITIONS}:
        return calculate_fujing_feature(factor_id, bars)
    ordered = sorted(
        (dict(row) for row in bars if row.get("date") or row.get("trade_date")),
        key=lambda row: str(row.get("date") or row.get("trade_date")),
    )
    closes = [_finite_or_none(row.get("close")) for row in ordered]
    amounts = [_finite_or_none(row.get("amount")) for row in ordered]
    one_day_returns: list[float | None] = [None]
    for index in range(1, len(closes)):
        current = closes[index]
        previous = closes[index - 1]
        one_day_returns.append(
            current / previous - 1.0
            if current is not None and previous not in {None, 0.0}
            else None
        )

    values: dict[str, float] = {}
    for index, row in enumerate(ordered):
        value: float | None = None
        if factor_id == "close_to_close_return_1d":
            value = one_day_returns[index]
        elif factor_id in {"momentum_20d", "momentum_60d"}:
            window = int(definition["parameters"]["window"])
            if index >= window and closes[index] is not None and closes[index - window] not in {None, 0.0}:
                value = float(closes[index]) / float(closes[index - window]) - 1.0
        elif factor_id == "volatility_20d":
            if index >= 20:
                window_values = one_day_returns[index - 19 : index + 1]
                if len(window_values) == 20 and all(item is not None for item in window_values):
                    value = statistics.pstdev(float(item) for item in window_values if item is not None)
        elif factor_id == "close_to_ma20_bias":
            if index >= 19:
                window_values = closes[index - 19 : index + 1]
                if all(item is not None for item in window_values):
                    moving_average = statistics.fmean(float(item) for item in window_values if item is not None)
                    if moving_average != 0 and closes[index] is not None:
                        value = float(closes[index]) / moving_average - 1.0
        elif factor_id == "amount_strength_20d":
            if index >= 19:
                window_values = amounts[index - 19 : index + 1]
                if all(item is not None for item in window_values):
                    moving_average = statistics.fmean(float(item) for item in window_values if item is not None)
                    if moving_average != 0 and amounts[index] is not None:
                        value = float(amounts[index]) / moving_average - 1.0
        if value is not None and math.isfinite(value):
            values[str(row.get("date") or row.get("trade_date"))[:10]] = value
    return values


def calculate_factor_definition(
    definition: Mapping[str, Any], bars: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    """Calculate a frozen built-in or governed expression definition."""

    if definition.get("definition_type") == "indicator":
        from data_platform.indicators import calculate_indicator_factor
        return calculate_indicator_factor(definition, bars)

    if str(definition.get("definition_type") or "builtin") == "expression":
        return calculate_expression_factor(str(definition.get("expression") or ""), bars)
    return calculate_factor(str(definition.get("factor_id") or ""), bars)

def preprocess_cross_section(
    values: Mapping[str, float],
    *,
    industries: Mapping[str, str] | None = None,
    winsor_mad: float = 3.0,
    industry_neutral: bool = False,
    standardize: bool = True,
    direction: str = "positive",
) -> dict[str, Any]:
    finite = {
        str(symbol): float(value)
        for symbol, value in values.items()
        if _finite_or_none(value) is not None
    }
    steps: list[dict[str, Any]] = [
        _step("finite_filter", len(values), len(finite), {})
    ]
    winsorized = dict(finite)
    if winsorized and winsor_mad > 0:
        median = statistics.median(winsorized.values())
        mad = statistics.median(abs(value - median) for value in winsorized.values())
        if mad > 0:
            lower = median - winsor_mad * mad
            upper = median + winsor_mad * mad
            winsorized = {
                symbol: min(upper, max(lower, value))
                for symbol, value in winsorized.items()
            }
        steps.append(
            _step(
                "mad_winsorize",
                len(finite),
                len(winsorized),
                {"threshold": winsor_mad, "median": median, "mad": mad},
            )
        )

    neutralized = dict(winsorized)
    missing_industry: list[str] = []
    if industry_neutral:
        industry_map = dict(industries or {})
        grouped: dict[str, list[float]] = defaultdict(list)
        for symbol, value in neutralized.items():
            industry = str(industry_map.get(symbol) or "")
            if industry:
                grouped[industry].append(value)
            else:
                missing_industry.append(symbol)
        means = {key: statistics.fmean(items) for key, items in grouped.items() if items}
        neutralized = {
            symbol: value - means[str(industry_map[symbol])]
            for symbol, value in neutralized.items()
            if str(industry_map.get(symbol) or "") in means
        }
        steps.append(
            _step(
                "industry_neutralize",
                len(winsorized),
                len(neutralized),
                {"missing_industry_count": len(missing_industry), "industry_count": len(means)},
            )
        )

    processed = dict(neutralized)
    unavailable_reason: str | None = None
    if standardize and processed:
        mean_value = statistics.fmean(processed.values())
        std_value = statistics.pstdev(processed.values())
        if std_value == 0:
            unavailable_reason = "cross_section_standard_deviation_is_zero"
            processed = {}
        else:
            processed = {
                symbol: (value - mean_value) / std_value
                for symbol, value in processed.items()
            }
        steps.append(
            _step(
                "zscore",
                len(neutralized),
                len(processed),
                {"mean": mean_value, "std": std_value},
            )
        )
    sign = -1.0 if str(direction).lower() == "negative" else 1.0
    aligned = {symbol: value * sign for symbol, value in processed.items()}
    return {
        "status": "ready" if processed else "unavailable",
        "reason": unavailable_reason,
        "processed": processed,
        "aligned": aligned,
        "steps": steps,
        "missing_industry_symbols": missing_industry,
        "content_hash": canonical_hash(
            {"processed": processed, "direction": direction, "steps": steps}
        ),
    }


def build_factor_report(
    *,
    observations: Sequence[Mapping[str, Any]] = (),
    universe_count_by_date: Mapping[str, int],
    horizons: Sequence[int],
    group_count: int,
    direction: str,
    cost_rate: float = 0.0,
    observation_batches: Iterable[
        tuple[str, Sequence[Mapping[str, Any]]]
    ] | None = None,
    distribution_summary: Mapping[str, Any] | None = None,
    industry_ic_summary: Sequence[Mapping[str, Any]] | None = None,
    observation_count: int | None = None,
) -> dict[str, Any]:
    """Build coverage, IC, group, industry and execution-estimate evidence."""

    ordered: list[dict[str, Any]] | None = None
    if observation_batches is None:
        ordered = sorted(
            (
                row if isinstance(row, dict) else dict(row)
                for row in observations
            ),
            key=lambda row: (str(row["trade_date"]), str(row["symbol"])),
        )
        by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in ordered:
            by_date[str(row["trade_date"])].append(row)
        batches: Iterable[tuple[str, Sequence[Mapping[str, Any]]]] = sorted(
            by_date.items()
        )
    else:
        batches = observation_batches
    primary_horizon = int(horizons[0])
    coverage_series: list[dict[str, Any]] = []
    ic_series: dict[int, list[dict[str, Any]]] = {int(h): [] for h in horizons}
    industry_pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    group_series: list[dict[str, Any]] = []
    group_unavailable_series: list[dict[str, Any]] = []
    previous_groups: dict[int, set[str]] = {}
    persistence: list[dict[str, Any]] = []
    previous_aligned: dict[str, float] | None = None
    all_processed: list[float] = []
    final_ranked: list[dict[str, Any]] = []

    streamed_count = 0
    for trade_date, source_rows in batches:
        rows = [row if isinstance(row, dict) else dict(row) for row in source_rows]
        streamed_count += len(rows)
        universe_count = int(universe_count_by_date.get(trade_date) or 0)
        factor_rows = [
            row for row in rows
            if _finite_or_none(row.get("processed_value")) is not None
        ]
        if distribution_summary is None:
            all_processed.extend(float(row["processed_value"]) for row in factor_rows)
        outcome_rows = [
            row for row in factor_rows
            if _forward_value(row, primary_horizon) is not None
        ]
        coverage_series.append(
            {
                "trade_date": trade_date,
                "universe_count": universe_count,
                "factor_count": len(factor_rows),
                "outcome_count": len(outcome_rows),
                "factor_coverage": _ratio(len(factor_rows), universe_count),
                "outcome_coverage": _ratio(len(outcome_rows), len(factor_rows)),
            }
        )

        for horizon in horizons:
            pairs = [
                (
                    float(row["processed_value"]),
                    float(_forward_value(row, int(horizon))),
                    float(row.get("aligned_value", row["processed_value"])),
                )
                for row in factor_rows
                if _forward_value(row, int(horizon)) is not None
            ]
            raw_ic = pearson([item[0] for item in pairs], [item[1] for item in pairs])
            raw_rank_ic = spearman([item[0] for item in pairs], [item[1] for item in pairs])
            aligned_rank_ic = spearman([item[2] for item in pairs], [item[1] for item in pairs])
            ic_series[int(horizon)].append(
                {
                    "trade_date": trade_date,
                    "sample_count": len(pairs),
                    "ic": raw_ic,
                    "rank_ic": raw_rank_ic,
                    "direction_aligned_rank_ic": aligned_rank_ic,
                }
            )

        aligned_map = {
            str(row["symbol"]): float(row.get("aligned_value", row["processed_value"]))
            for row in factor_rows
        }
        if previous_aligned is not None:
            common = sorted(set(previous_aligned) & set(aligned_map))
            persistence.append(
                {
                    "trade_date": trade_date,
                    "sample_count": len(common),
                    "rank_correlation": spearman(
                        [previous_aligned[symbol] for symbol in common],
                        [aligned_map[symbol] for symbol in common],
                    ),
                }
            )
        previous_aligned = aligned_map

        if len(outcome_rows) >= group_count:
            ranked = sorted(
                outcome_rows,
                key=lambda row: (float(row.get("aligned_value", row["processed_value"])), str(row["symbol"])),
            )
            buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for index, row in enumerate(ranked):
                bucket = min(group_count, index * group_count // len(ranked) + 1)
                buckets[bucket].append(row)
                row["group_no"] = bucket
            group_returns = {
                bucket: statistics.fmean(
                    float(_forward_value(row, primary_horizon))
                    for row in bucket_rows
                )
                for bucket, bucket_rows in buckets.items()
            }
            turnovers: dict[int, float | None] = {}
            for bucket, bucket_rows in buckets.items():
                members = {str(row["symbol"]) for row in bucket_rows}
                previous = previous_groups.get(bucket)
                turnovers[bucket] = (
                    None
                    if previous is None
                    else 1.0 - len(previous & members) / max(1, len(previous))
                )
                previous_groups[bucket] = members
            top_turnover = turnovers.get(group_count)
            bottom_turnover = turnovers.get(1)
            gross = group_returns.get(group_count, 0.0) - group_returns.get(1, 0.0)
            estimated_cost = (
                (top_turnover or 0.0) + (bottom_turnover or 0.0)
            ) * max(0.0, float(cost_rate))
            turnover_cost_units = (top_turnover or 0.0) + (bottom_turnover or 0.0)
            group_series.append(
                {
                    "trade_date": trade_date,
                    "returns": {str(key): value for key, value in sorted(group_returns.items())},
                    "turnover": {str(key): value for key, value in sorted(turnovers.items())},
                    "top_bottom_gross_return": gross,
                    "estimated_cost": estimated_cost,
                    "turnover_cost_units": turnover_cost_units,
                    "top_bottom_net_return_estimate": gross - estimated_cost,
                }
            )
            final_ranked = ranked
        else:
            group_unavailable_series.append(
                {
                    "trade_date": trade_date,
                    "sample_count": len(outcome_rows),
                    "required_count": group_count,
                    "reason": "sample_count_below_group_count",
                }
            )

        if industry_ic_summary is None:
            for row in outcome_rows:
                industry = str(row.get("industry") or "")
                if industry:
                    industry_pairs[industry].append(
                        (
                            float(row.get("aligned_value", row["processed_value"])),
                            float(_forward_value(row, primary_horizon)),
                        )
                    )

    ic_payload: dict[str, Any] = {}
    for horizon, series in ic_series.items():
        raw_values = [float(row["ic"]) for row in series if row["ic"] is not None]
        rank_values = [float(row["rank_ic"]) for row in series if row["rank_ic"] is not None]
        aligned_values = [
            float(row["direction_aligned_rank_ic"])
            for row in series
            if row["direction_aligned_rank_ic"] is not None
        ]
        ic_payload[str(horizon)] = {
            "series": series,
            "ic_mean": _mean_or_none(raw_values),
            "rank_ic_mean": _mean_or_none(rank_values),
            "direction_aligned_rank_ic_mean": _mean_or_none(aligned_values),
            "icir": _safe_div(_mean_or_none(raw_values), _population_std_or_none(raw_values)),
            "rank_ic_t_value": _t_value(rank_values),
            "rank_ic_hac_t_value": _newey_west_t_value(rank_values),
            "positive_aligned_rank_ic_ratio": (
                _ratio(sum(value > 0 for value in aligned_values), len(aligned_values))
            ),
            "abs_rank_ic_above_0_02_ratio": (
                _ratio(sum(abs(value) > 0.02 for value in rank_values), len(rank_values))
            ),
            "rolling_22": _rolling_mean(series, "direction_aligned_rank_ic", 22, 10),
        }

    industry_ic = (
        [dict(item) for item in industry_ic_summary]
        if industry_ic_summary is not None
        else [
            {
                "industry": industry,
                "sample_count": len(pairs),
                "rank_ic": spearman(
                    [item[0] for item in pairs],
                    [item[1] for item in pairs],
                ),
            }
            for industry, pairs in sorted(industry_pairs.items())
        ]
    )
    nav = 1.0
    peak = 1.0
    max_drawdown = 0.0
    nav_series: list[dict[str, Any]] = []
    for item in group_series:
        net_return = float(item["top_bottom_net_return_estimate"])
        nav *= 1.0 + net_return
        peak = max(peak, nav)
        drawdown = nav / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)
        nav_series.append({"trade_date": item["trade_date"], "nav": nav, "drawdown": drawdown})

    latest_top = [
        {
            "symbol": str(row["symbol"]),
            "trade_date": str(row["trade_date"]),
            "factor_value": row.get("raw_value"),
            "processed_value": row.get("processed_value"),
            "industry": row.get("industry"),
            "group_no": row.get("group_no"),
        }
        for row in reversed(final_ranked[-20:])
    ]
    latest_bottom = [
        {
            "symbol": str(row["symbol"]),
            "trade_date": str(row["trade_date"]),
            "factor_value": row.get("raw_value"),
            "processed_value": row.get("processed_value"),
            "industry": row.get("industry"),
            "group_no": row.get("group_no"),
        }
        for row in final_ranked[:20]
    ]
    group_return_means = {
        str(group): _mean_or_none([
            float(item["returns"][str(group)])
            for item in group_series if str(group) in item.get("returns", {})
        ])
        for group in range(1, group_count + 1)
    }
    monotonic_values = [
        group_return_means[str(group)] for group in range(1, group_count + 1)
    ]
    monotonicity = (
        spearman(
            [float(group) for group in range(1, group_count + 1)],
            [float(value) for value in monotonic_values],
        )
        if all(value is not None for value in monotonic_values) else None
    )
    gross_return = sum(float(row["top_bottom_gross_return"]) for row in group_series)
    turnover_cost_units = sum(float(row.get("turnover_cost_units") or 0.0) for row in group_series)
    base_rate = max(0.0, float(cost_rate))
    return {
        "coverage": {
            "series": coverage_series,
            "average_factor_coverage": _mean_or_none(
                [row["factor_coverage"] for row in coverage_series if row["factor_coverage"] is not None]
            ),
            "average_outcome_coverage": _mean_or_none(
                [row["outcome_coverage"] for row in coverage_series if row["outcome_coverage"] is not None]
            ),
        },
        "distribution": (
            dict(distribution_summary)
            if distribution_summary is not None
            else distribution(all_processed)
        ),
        "ic": ic_payload,
        "annual_stability": _annual_ic_stability(ic_series),
        "market_regime_stability": {
            "status": "unavailable",
            "reason": "market_regime_labels_not_frozen_in_research_context",
        },
        "decay": [
            {
                "horizon": horizon,
                "rank_ic_mean": ic_payload[str(horizon)]["rank_ic_mean"],
                "direction_aligned_rank_ic_mean": ic_payload[str(horizon)]["direction_aligned_rank_ic_mean"],
            }
            for horizon in horizons
        ],
        "group_analysis": {
            "group_count": group_count,
            "primary_horizon": primary_horizon,
            "series": group_series,
            "unavailable_series": group_unavailable_series,
            "nav": nav_series,
            "final_nav": nav,
            "max_drawdown": max_drawdown if nav_series else None,
            "average_group_returns": group_return_means,
            "group_return_monotonicity": monotonicity,
        },
        "industry_ic": industry_ic,
        "signal_persistence": persistence,
        "execution_estimate": {
            "status": "estimate_only",
            "method": "symmetric_top_bottom_membership_turnover",
            "one_side_cost_rate": base_rate,
            "gross_return": gross_return,
            "estimated_cost": sum(float(row["estimated_cost"]) for row in group_series),
            "net_return_estimate": sum(float(row["top_bottom_net_return_estimate"]) for row in group_series),
            "cost_stress": [
                {
                    "one_side_cost_rate": rate,
                    "estimated_cost": turnover_cost_units * rate,
                    "net_return_estimate": gross_return - turnover_cost_units * rate,
                }
                for rate in sorted({base_rate, base_rate * 2.0})
            ],
        },
        "latest_stocks": {"top": latest_top, "bottom": latest_bottom},
        "direction": direction,
        "observation_count": (
            int(observation_count)
            if observation_count is not None
            else (len(ordered) if ordered is not None else streamed_count)
        ),
    }


def distribution(values: Iterable[float]) -> dict[str, Any]:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return {"status": "unavailable", "reason": "no_finite_values", "count": 0}
    return {
        "status": "ready",
        "count": len(ordered),
        "mean": statistics.fmean(ordered),
        "std": statistics.pstdev(ordered),
        "min": ordered[0],
        "p01": percentile(ordered, 0.01),
        "p05": percentile(ordered, 0.05),
        "p25": percentile(ordered, 0.25),
        "median": percentile(ordered, 0.5),
        "p75": percentile(ordered, 0.75),
        "p95": percentile(ordered, 0.95),
        "p99": percentile(ordered, 0.99),
        "max": ordered[-1],
    }


def _annual_ic_stability(
    ic_series: Mapping[int, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for horizon, series in sorted(ic_series.items()):
        by_year: dict[str, list[float]] = defaultdict(list)
        for item in series:
            value = _finite_or_none(item.get("direction_aligned_rank_ic"))
            if value is not None:
                by_year[str(item.get("trade_date") or "")[:4]].append(value)
        for year, values in sorted(by_year.items()):
            result.append({
                "year": year,
                "horizon": horizon,
                "period_count": len(values),
                "direction_aligned_rank_ic_mean": _mean_or_none(values),
                "positive_ratio": _ratio(sum(value > 0 for value in values), len(values)),
                "hac_t_value": _newey_west_t_value(values),
            })
    return result


def percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = min(1.0, max(0.0, float(fraction))) * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    pairs = [
        (float(a), float(b))
        for a, b in zip(left, right, strict=False)
        if math.isfinite(float(a)) and math.isfinite(float(b))
    ]
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs, strict=True)
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - x_mean) ** 2 for x in xs)
        * sum((y - y_mean) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else None


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    return pearson(average_ranks(left), average_ranks(right))


def average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(float(value) for value in values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(indexed)
    start = 0
    while start < len(indexed):
        end = start + 1
        while end < len(indexed) and indexed[end][1] == indexed[start][1]:
            end += 1
        average = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[indexed[position][0]] = average
        start = end
    return ranks


def _step(name: str, before: int, after: int, parameters: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "before_count": before,
        "after_count": after,
        "excluded_count": max(0, before - after),
        "parameters": dict(parameters),
    }


def _forward_value(row: Mapping[str, Any], horizon: int) -> float | None:
    values = row.get("forward_returns") or {}
    value = values.get(str(horizon)) if isinstance(values, Mapping) else None
    return _finite_or_none(value)


def _finite_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized if math.isfinite(normalized) else None


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator) / float(denominator) if denominator else None


def _mean_or_none(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _population_std_or_none(values: Sequence[float]) -> float | None:
    return statistics.pstdev(values) if len(values) >= 2 else None


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    return numerator / denominator if numerator is not None and denominator not in {None, 0.0} else None


def _t_value(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    std = statistics.stdev(values)
    return statistics.fmean(values) / (std / math.sqrt(len(values))) if std else None


def _newey_west_t_value(values: Sequence[float], lag: int | None = None) -> float | None:
    """HAC t-value for a serially correlated IC mean (Bartlett kernel)."""

    clean = [float(value) for value in values if math.isfinite(float(value))]
    count = len(clean)
    if count < 3:
        return None
    mean = statistics.fmean(clean)
    centered = [value - mean for value in clean]
    selected_lag = min(count - 1, max(0, int(lag if lag is not None else count ** 0.25)))
    long_run_variance = sum(value * value for value in centered) / count
    for offset in range(1, selected_lag + 1):
        covariance = sum(
            centered[index] * centered[index - offset]
            for index in range(offset, count)
        ) / count
        weight = 1.0 - offset / (selected_lag + 1.0)
        long_run_variance += 2.0 * weight * covariance
    if long_run_variance <= 0:
        return None
    return mean / math.sqrt(long_run_variance / count)


def _rolling_mean(
    series: Sequence[Mapping[str, Any]],
    field: str,
    window: int,
    minimum: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    values: list[float] = []
    for item in series:
        value = _finite_or_none(item.get(field))
        if value is not None:
            values.append(value)
        recent = values[-window:]
        result.append(
            {
                "trade_date": item.get("trade_date"),
                "value": statistics.fmean(recent) if len(recent) >= minimum else None,
                "sample_count": len(recent),
            }
        )
    return result
