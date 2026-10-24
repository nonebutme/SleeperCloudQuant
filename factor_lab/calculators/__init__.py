"""Factor calculators."""

from .fujing_features import (
    AmplitudeRatio1dCalculator,
    CausalTroughEvent16dCalculator,
    WinnerProxyHigh120dCalculator,
    WinnerProxyLow120dCalculator,
    WinnerProxySpread120dCalculator,
)
from .price_factors import CloseToCloseReturnCalculator, CloseToMa2BiasCalculator

__all__ = [
    "AmplitudeRatio1dCalculator",
    "CausalTroughEvent16dCalculator",
    "CloseToCloseReturnCalculator",
    "CloseToMa2BiasCalculator",
    "WinnerProxyHigh120dCalculator",
    "WinnerProxyLow120dCalculator",
    "WinnerProxySpread120dCalculator",
]
