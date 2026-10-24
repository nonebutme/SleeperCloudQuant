"""Governed scalar feature calculators for the Fujing v7 candidate.

The WINNER family is an OHLCV proxy. It must never be presented as native
chip-distribution data. All rolling features require a complete historical
window and only use rows at or before the output trade date.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from domain.market.models import Bar
from factor_lab.models import FactorDefinition, FactorValue


WINNER_WINDOW = 120
TROUGH_WINDOW = 16

FUJING_FEATURE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "factor_id": "winner_proxy_low_120d",
        "name": "WINNER 低价获利比例代理（120 日）",
        "formula": "volume_weighted_share(OHLC4 <= low_t, window=120)",
        "description": "最近 120 日成交量加权 OHLC4 典型价不高于当日最低价的比例；不是原生筹码分布。",
        "input_fields": ["open", "high", "low", "close", "volume"],
        "minimum_history": 120,
        "direction": "neutral",
        "parameters": {"window": 120, "proxy": True, "native_winner": False},
    },
    {
        "factor_id": "winner_proxy_high_120d",
        "name": "WINNER 高价获利比例代理（120 日）",
        "formula": "volume_weighted_share(OHLC4 <= high_t, window=120)",
        "description": "最近 120 日成交量加权 OHLC4 典型价不高于当日最高价的比例；不是原生筹码分布。",
        "input_fields": ["open", "high", "low", "close", "volume"],
        "minimum_history": 120,
        "direction": "neutral",
        "parameters": {"window": 120, "proxy": True, "native_winner": False},
    },
    {
        "factor_id": "winner_proxy_spread_120d",
        "name": "WINNER 高低价比例差代理（120 日）",
        "formula": "abs(winner_proxy_high_120d - winner_proxy_low_120d)",
        "description": "当日最高价与最低价对应的 120 日 WINNER 代理比例之差；不是原生筹码分布。",
        "input_fields": ["open", "high", "low", "close", "volume"],
        "minimum_history": 120,
        "direction": "neutral",
        "parameters": {"window": 120, "proxy": True, "native_winner": False},
    },
    {
        "factor_id": "causal_trough_event_16d",
        "name": "16 日因果低点事件",
        "formula": "low_t <= min(low_{t-15}...low_t)",
        "description": "当日最低价达到当前及过去共 16 个交易日最低位时取 1，否则取 0。",
        "input_fields": ["low"],
        "minimum_history": 16,
        "direction": "neutral",
        "parameters": {"window": 16, "causal": True},
    },
    {
        "factor_id": "amplitude_ratio_1d",
        "name": "日内振幅比例（昨收口径）",
        "formula": "(high_t - low_t) / close_t-1",
        "description": "当日最高价与最低价之差除以前一交易日收盘价，替代固定金额振幅。",
        "input_fields": ["high", "low", "close"],
        "minimum_history": 2,
        "direction": "neutral",
        "parameters": {"denominator": "previous_close", "causal": True},
    },
)


def calculate_fujing_feature(
    factor_id: str,
    bars: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    """Calculate one governed scalar feature over ascending OHLCV rows."""

    normalized = str(factor_id or "").strip().lower()
    supported = {item["factor_id"] for item in FUJING_FEATURE_DEFINITIONS}
    if normalized not in supported:
        raise ValueError(f"unsupported Fujing feature: {factor_id}")
    ordered = sorted(
        (dict(row) for row in bars if row.get("date") or row.get("trade_date")),
        key=lambda row: str(row.get("date") or row.get("trade_date")),
    )
    values: dict[str, float] = {}
    for index, row in enumerate(ordered):
        value = _value_at(normalized, ordered, index)
        if value is not None and math.isfinite(value):
            values[str(row.get("date") or row.get("trade_date"))[:10]] = value
    return values


def _value_at(factor_id: str, bars: Sequence[Mapping[str, Any]], index: int) -> float | None:
    if factor_id == "amplitude_ratio_1d":
        if index < 1:
            return None
        high = _finite(bars[index].get("high"))
        low = _finite(bars[index].get("low"))
        previous_close = _finite(bars[index - 1].get("close"))
        if high is None or low is None or previous_close is None or previous_close <= 0 or high < low:
            return None
        return (high - low) / previous_close

    if factor_id == "causal_trough_event_16d":
        if index < TROUGH_WINDOW - 1:
            return None
        lows = [_finite(item.get("low")) for item in bars[index - TROUGH_WINDOW + 1 : index + 1]]
        if any(item is None for item in lows):
            return None
        current = lows[-1]
        return 1.0 if current is not None and current <= min(float(item) for item in lows if item is not None) else 0.0

    if index < WINNER_WINDOW - 1:
        return None
    window = bars[index - WINNER_WINDOW + 1 : index + 1]
    typical_prices: list[float] = []
    volumes: list[float] = []
    for item in window:
        fields = [_finite(item.get(name)) for name in ("open", "high", "low", "close")]
        volume = _finite(item.get("volume"))
        if any(field is None for field in fields) or volume is None or volume < 0:
            return None
        typical_prices.append(sum(float(field) for field in fields if field is not None) / 4.0)
        volumes.append(volume)
    total_volume = sum(volumes)
    if total_volume <= 0:
        return None
    current_low = _finite(bars[index].get("low"))
    current_high = _finite(bars[index].get("high"))
    if current_low is None or current_high is None or current_high < current_low:
        return None
    low_ratio = sum(volume for price, volume in zip(typical_prices, volumes) if price <= current_low) / total_volume
    high_ratio = sum(volume for price, volume in zip(typical_prices, volumes) if price <= current_high) / total_volume
    if factor_id == "winner_proxy_low_120d":
        return low_ratio
    if factor_id == "winner_proxy_high_120d":
        return high_ratio
    return abs(high_ratio - low_ratio)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class _FujingFeatureCalculator:
    factor_id = ""

    def definition(self) -> FactorDefinition:
        metadata = next(item for item in FUJING_FEATURE_DEFINITIONS if item["factor_id"] == self.factor_id)
        return FactorDefinition(
            factor_id=self.factor_id,
            name=str(metadata["name"]),
            parameters={
                **dict(metadata["parameters"]),
                "input_fields": list(metadata["input_fields"]),
                "minimum_history": int(metadata["minimum_history"]),
                "formula": str(metadata["formula"]),
                "description": str(metadata["description"]),
            },
        )

    def calculate(self, *, symbol: str, bars: Sequence[Bar]) -> list[FactorValue]:
        mappings = [
            {
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
        return [
            FactorValue(factor_id=self.factor_id, symbol=symbol, trade_date=trade_date, value=value)
            for trade_date, value in calculate_fujing_feature(self.factor_id, mappings).items()
        ]


class WinnerProxyLow120dCalculator(_FujingFeatureCalculator):
    factor_id = "winner_proxy_low_120d"


class WinnerProxyHigh120dCalculator(_FujingFeatureCalculator):
    factor_id = "winner_proxy_high_120d"


class WinnerProxySpread120dCalculator(_FujingFeatureCalculator):
    factor_id = "winner_proxy_spread_120d"


class CausalTroughEvent16dCalculator(_FujingFeatureCalculator):
    factor_id = "causal_trough_event_16d"


class AmplitudeRatio1dCalculator(_FujingFeatureCalculator):
    factor_id = "amplitude_ratio_1d"
