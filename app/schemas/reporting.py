"""Reporting request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass

from domain.report.models import BatchExperimentSummaryModel, BacktestRunDetailModel


@dataclass(frozen=True, slots=True)
class RunDetailResponse:
    """Minimal response payload for one run-detail query."""

    detail: BacktestRunDetailModel


@dataclass(frozen=True, slots=True)
class BatchSummaryResponse:
    """Minimal response payload for one batch-summary query."""

    summary: BatchExperimentSummaryModel
