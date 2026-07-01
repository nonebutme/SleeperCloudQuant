"""Stable public exports for the backtest kernel package."""

from .adapters.rqalpha_ricequant_gateway import (
    RqalphaRicequantGateway,
    RqalphaRuntimeProtocol,
)
from .gateway.contracts import BacktestGateway, BacktestRequest, BacktestResult
from .use_cases.run_single_backtest import (
    RunSingleBacktest,
    RunSingleBacktestRequest,
)

__all__ = [
    "BacktestGateway",
    "BacktestRequest",
    "BacktestResult",
    "RqalphaRicequantGateway",
    "RqalphaRuntimeProtocol",
    "RunSingleBacktest",
    "RunSingleBacktestRequest",
]
