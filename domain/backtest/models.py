"""Minimal backtest-domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.common.enums import BacktestRunStatus


@dataclass(frozen=True, slots=True)
class BacktestRunRequest:
    """Service-facing request model for one backtest run."""

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


@dataclass(frozen=True, slots=True)
class BacktestResultSummary:
    """Minimal backtest result summary returned by the service layer."""

    run_id: str
    strategy_name: str
    status: BacktestRunStatus
    start_date: str
    end_date: str
    benchmark: str
    metrics: dict[str, Any] = field(default_factory=dict)
