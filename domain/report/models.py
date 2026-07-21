"""Minimal reporting-domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BacktestRunDetailModel:
    """Minimal service-facing run-detail model."""

    run_id: str
    strategy_name: str
    status: str
    benchmark: str | None
    start_date: str | None
    end_date: str | None
    strategy_id: str | None = None
    extra_config: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    account_value_chart: list[dict[str, Any]] = field(default_factory=list)
    trade_activity_chart: list[dict[str, Any]] = field(default_factory=list)
    position_exposure_chart: list[dict[str, Any]] = field(default_factory=list)
    yearly_return_chart: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BatchExperimentRowModel:
    """Minimal row model for batch summaries."""

    rank: int
    run_id: str
    strategy_name: str
    strategy_id: str
    symbol: str | None
    annualized_returns: float | None
    total_returns: float | None
    max_drawdown: float | None
    sharpe: float | None
    status: str
    error_message: str | None


@dataclass(frozen=True, slots=True)
class BatchExperimentSummaryModel:
    """Minimal batch summary model exposed by the service layer."""

    experiment_id: str
    profile: str
    status: str
    started_at: str
    finished_at: str | None
    request_count: int
    success_count: int
    failure_count: int
    rows: list[BatchExperimentRowModel] = field(default_factory=list)
    yearly_rows: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    failure_type_counts: dict[str, int] = field(default_factory=dict)
    failure_stage_counts: dict[str, int] = field(default_factory=dict)
    failure_code_counts: dict[str, int] = field(default_factory=dict)

