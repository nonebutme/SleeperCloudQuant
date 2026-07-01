"""Backtest request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.backtest.models import BacktestResultSummary


@dataclass(frozen=True, slots=True)
class BacktestRunRequestPayload:
    """Minimal request payload for one backtest submission."""

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
class BacktestRunResponsePayload:
    """Minimal response payload for one backtest submission."""

    result: BacktestResultSummary
