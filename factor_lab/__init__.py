"""Minimal factor-lab package."""

from .calculators import (
    AmplitudeRatio1dCalculator,
    CausalTroughEvent16dCalculator,
    CloseToCloseReturnCalculator,
    CloseToMa2BiasCalculator,
    WinnerProxyHigh120dCalculator,
    WinnerProxyLow120dCalculator,
    WinnerProxySpread120dCalculator,
)
from .models import (
    FactorDefinition,
    FactorPoolRunResult,
    FactorRankingResult,
    FactorRunResult,
    FactorValue,
)
from .registry import FactorRegistry
from .storage import SqliteFactorStore

__all__ = [
    "AmplitudeRatio1dCalculator",
    "CausalTroughEvent16dCalculator",
    "CloseToCloseReturnCalculator",
    "CloseToMa2BiasCalculator",
    "FactorDefinition",
    "FactorPoolRunResult",
    "FactorRankingResult",
    "FactorRegistry",
    "FactorRunResult",
    "FactorValue",
    "SqliteFactorStore",
    "WinnerProxyHigh120dCalculator",
    "WinnerProxyLow120dCalculator",
    "WinnerProxySpread120dCalculator",
]
