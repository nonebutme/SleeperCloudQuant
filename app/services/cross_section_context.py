"""Point-in-time industry and market-regime analysis helpers."""

from __future__ import annotations

import math
import statistics
from typing import Any


def build_raw_factor_comparison(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare point-in-time raw scores with post-sizing portfolio exposure."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in observations:
        date = str(row.get("date") or "")[:10]
        if date and all(row.get(key) is not None for key in ("raw_score", "exposure", "future_return")):
            grouped.setdefault(date, []).append(row)
    raw_ic: list[float] = []
    exposure_ic: list[float] = []
    coverage: list[float] = []
    for rows in grouped.values():
        scores = [float(row["raw_score"]) for row in rows]
        exposures = [float(row["exposure"]) for row in rows]
        outcomes = [float(row["future_return"]) for row in rows]
        raw_value = _pearson(scores, outcomes)
        exposure_value = _pearson(exposures, outcomes)
        if raw_value is not None:
            raw_ic.append(raw_value)
        if exposure_value is not None:
            exposure_ic.append(exposure_value)
        coverage.append(sum(row.get("raw_score") is not None for row in rows) / len(rows))
    raw_mean = statistics.mean(raw_ic) if raw_ic else None
    exposure_mean = statistics.mean(exposure_ic) if exposure_ic else None
    return {
        "status": "ready" if raw_ic else "insufficient_cross_section",
        "raw_factor_ic_mean": raw_mean,
        "raw_factor_icir": _icir(raw_ic),
        "exposure_ic_mean": exposure_mean,
        "exposure_icir": _icir(exposure_ic),
        "conversion_loss": abs(raw_mean) - abs(exposure_mean) if raw_mean is not None and exposure_mean is not None else None,
        "raw_period_count": len(raw_ic),
        "exposure_period_count": len(exposure_ic),
        "coverage_ratio": statistics.mean(coverage) if coverage else None,
        "methodology": "raw score and post-sizing exposure are separately correlated with next-period return",
    }

def index_industry_intervals(rows: Any) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows or []:
        symbol = str(row.get("symbol") or "").split(".", 1)[0].zfill(6)
        result.setdefault(symbol, []).append(dict(row))
    return result


def industry_cross_section(
    *,
    date: str,
    signals: list[float],
    outcomes: list[float],
    symbols: list[str],
    interval_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    grouped: dict[str, list[int]] = {}
    for index, symbol in enumerate(symbols):
        code = str(symbol or "").split(".", 1)[0].zfill(6)
        industry = _industry_as_of(interval_index.get(code, []), date)
        if industry:
            grouped.setdefault(industry, []).append(index)
    industry_ic: dict[str, float] = {}
    neutral_signals: list[float] = []
    neutral_outcomes: list[float] = []
    for industry, indices in grouped.items():
        local_signals = [float(signals[index]) for index in indices]
        local_outcomes = [float(outcomes[index]) for index in indices]
        value = _pearson(local_signals, local_outcomes)
        if value is not None:
            industry_ic[industry] = value
        if len(indices) >= 2:
            signal_mean = statistics.mean(local_signals)
            outcome_mean = statistics.mean(local_outcomes)
            neutral_signals.extend(value - signal_mean for value in local_signals)
            neutral_outcomes.extend(value - outcome_mean for value in local_outcomes)
    return {
        "industry_ic": industry_ic,
        "neutral_ic": _pearson(neutral_signals, neutral_outcomes),
        "neutral_sample_size": len(neutral_signals),
    }


def build_industry_analysis(
    industry_daily: dict[str, list[float]],
    neutral_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    neutral_values = [float(row["ic"]) for row in neutral_rows]
    rows = [
        {
            "industry": industry,
            "ic_mean": statistics.mean(values),
            "icir": _icir(values),
            "period_count": len(values),
        }
        for industry, values in sorted(industry_daily.items())
    ]
    return {
        "status": "ready" if rows or neutral_values else "unavailable",
        "reason": None if rows or neutral_values else "historical_industry_classification_coverage_missing",
        "industry_rows": rows,
        "neutral_ic_mean": statistics.mean(neutral_values) if neutral_values else None,
        "neutral_icir": _icir(neutral_values),
        "neutral_period_count": len(neutral_values),
        "neutral_series": neutral_rows,
        "methodology": "within-industry IC and cross-section IC after point-in-time industry demeaning",
    }


def build_signal_market_regimes(
    ic_rows: list[dict[str, Any]],
    layered_daily: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(ic_rows) < 22:
        return {"status": "unavailable", "reason": "at_least_22_market_cross_sections_required", "rows": []}
    layer_by_date = {str(row["date"]): row for row in layered_daily}
    market_returns = [float(row.get("market_return") or 0.0) for row in ic_rows]
    buckets: dict[str, list[dict[str, Any]]] = {}
    historical_volatility: list[float] = []
    for index in range(20, len(ic_rows)):
        trailing = market_returns[index - 20 : index]
        trend = math.prod(1.0 + value for value in trailing) - 1.0
        volatility = statistics.pstdev(trailing)
        threshold = statistics.median(historical_volatility) if historical_volatility else volatility
        historical_volatility.append(volatility)
        trend_label = "上涨" if trend > 0.03 else "下跌" if trend < -0.03 else "震荡"
        label = f"{trend_label}/{'高波动' if volatility > threshold else '低波动'}"
        buckets.setdefault(label, []).append(ic_rows[index])
    rows = []
    for regime, values in sorted(buckets.items()):
        dates = {str(row["date"]) for row in values}
        long_short = [float(layer_by_date[date]["long_short"]) for date in dates if date in layer_by_date]
        rows.append(
            {
                "regime": regime,
                "sample_size": len(values),
                "ic_mean": statistics.mean(float(row["ic"]) for row in values),
                "rank_ic_mean": statistics.mean(float(row["rank_ic"]) for row in values),
                "ic_positive_ratio": sum(float(row["ic"]) > 0 for row in values) / len(values),
                "long_short_return": math.prod(1.0 + value for value in long_short) - 1.0 if long_short else None,
            }
        )
    return {
        "status": "ready" if rows else "unavailable",
        "rows": rows,
        "look_ahead_control": "each label uses only the preceding 20 cross-sectional market returns",
    }


def _industry_as_of(intervals: list[dict[str, Any]], date: str) -> str | None:
    candidates = [
        row
        for row in intervals
        if str(row.get("valid_from") or "")[:10] <= date
        and (not row.get("valid_to") or str(row.get("valid_to"))[:10] >= date)
    ]
    if not candidates:
        return None
    latest = max(str(row.get("valid_from") or "")[:10] for row in candidates)
    labels = sorted(
        str(row.get("category") or "")
        for row in candidates
        if str(row.get("valid_from") or "")[:10] == latest
    )
    return labels[0] if labels else None


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3 or max(left) == min(left) or max(right) == min(right):
        return None
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left)
        * sum((b - right_mean) ** 2 for b in right)
    )
    return numerator / denominator if denominator else None


def _icir(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    deviation = statistics.stdev(values)
    return statistics.mean(values) / deviation * math.sqrt(252) if deviation else None
