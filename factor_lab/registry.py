"""Minimal in-memory factor registry."""

from __future__ import annotations

from collections.abc import Mapping

from factor_lab.calculators import (
    AmplitudeRatio1dCalculator,
    CausalTroughEvent16dCalculator,
    CloseToCloseReturnCalculator,
    CloseToMa2BiasCalculator,
    WinnerProxyHigh120dCalculator,
    WinnerProxyLow120dCalculator,
    WinnerProxySpread120dCalculator,
)
from factor_lab.models import FactorDefinition


class FactorRegistry:
    """Register and resolve the minimal built-in factor calculators."""

    def __init__(self) -> None:
        calculators = [
            CloseToCloseReturnCalculator(),
            CloseToMa2BiasCalculator(),
            WinnerProxyLow120dCalculator(),
            WinnerProxyHigh120dCalculator(),
            WinnerProxySpread120dCalculator(),
            CausalTroughEvent16dCalculator(),
            AmplitudeRatio1dCalculator(),
        ]
        self._calculators = {calculator.factor_id: calculator for calculator in calculators}

    def get(self, factor_id: str):
        normalized = _normalize_factor_id(factor_id)
        calculator = self._calculators.get(normalized)
        if calculator is None:
            raise ValueError(f"unsupported factor_id: {factor_id}")
        return calculator

    def definitions(self) -> list[FactorDefinition]:
        return [calculator.definition() for calculator in self._calculators.values()]

    def mapping(self) -> Mapping[str, object]:
        return dict(self._calculators)


def _normalize_factor_id(factor_id: str) -> str:
    return str(factor_id).strip().lower()
