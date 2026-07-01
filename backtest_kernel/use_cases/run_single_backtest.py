"""Minimal single-backtest orchestration for phase-1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backtest_kernel.gateway.contracts import (
    BacktestGateway,
    BacktestRequest,
    BacktestResult,
)


@dataclass(frozen=True, slots=True)
class RunSingleBacktestRequest:
    """Application-level request for one backtest run."""

    run_id: str
    strategy_name: str
    symbol: str
    benchmark: str
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000
    frequency: str = "1d"
    parameters: dict[str, Any] = field(default_factory=dict)
    extra_config: dict[str, Any] = field(default_factory=dict)


class RunSingleBacktest:
    """Minimal orchestration use case for one backtest run."""

    def __init__(self, gateway: BacktestGateway) -> None:
        self._gateway = gateway

    def execute(self, request: RunSingleBacktestRequest) -> BacktestResult:
        """Build a normalized gateway request and execute it."""

        normalized_request = BacktestRequest(
            run_id=request.run_id,
            strategy_name=request.strategy_name,
            start_date=request.start_date,
            end_date=request.end_date,
            benchmark=request.benchmark,
            initial_cash=request.initial_cash,
            frequency=request.frequency,
            parameters={
                "symbol": request.symbol,
                **request.parameters,
            },
            extra_config=request.extra_config,
        )
        return self._gateway.run_backtest(normalized_request)
