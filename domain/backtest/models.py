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
    strategy_id: str | None = None
    strategy_version: str | None = None


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


@dataclass(frozen=True, slots=True)
class BatchBacktestRunRequest:
    """Service-facing request model for one batch backtest experiment."""

    experiment_id: str
    profile: str = "custom_batch"
    runs: list[BacktestRunRequest] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BatchBacktestRunSummary:
    """Minimal batch execution summary returned by the service layer."""

    experiment_id: str
    profile: str
    status: str
    started_at: str
    finished_at: str | None
    request_count: int
    success_count: int
    failure_count: int
    run_ids: list[str] = field(default_factory=list)
    successful_run_ids: list[str] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

