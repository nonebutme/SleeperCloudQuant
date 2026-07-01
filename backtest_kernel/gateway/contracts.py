"""Core backtest execution contracts for phase-1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    """Normalized single-run backtest request."""

    run_id: str
    strategy_name: str
    start_date: str
    end_date: str
    benchmark: str
    initial_cash: float
    frequency: str = "1d"
    strategy_callbacks: Mapping[str, Callable[..., Any]] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    extra_config: Mapping[str, Any] = field(default_factory=dict)
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Normalized single-run backtest result."""

    run_id: str
    strategy_name: str
    status: str
    start_date: str
    end_date: str
    benchmark: str
    metrics: Mapping[str, Any] = field(default_factory=dict)
    raw_result: Mapping[str, Any] = field(default_factory=dict)


class BacktestGateway(ABC):
    """Abstract gateway for one phase-1 backtest engine."""

    @abstractmethod
    def run_backtest(self, request: BacktestRequest) -> BacktestResult:
        """Execute one normalized backtest request."""
