"""Service-layer facade for formal reporting reads."""

from __future__ import annotations

from domain.report.models import (
    BatchExperimentRowModel,
    BatchExperimentSummaryModel,
    BacktestRunDetailModel,
)
from reporting import BatchComparisonService, RunResultsReader


class ReportingService:
    """Expose reporting reads through stable application models."""

    def __init__(
        self,
        results_reader: RunResultsReader,
        batch_comparison_service: BatchComparisonService,
    ) -> None:
        self._results_reader = results_reader
        self._batch_comparison_service = batch_comparison_service

    def get_run_detail(self, run_id: str) -> BacktestRunDetailModel | None:
        detail = self._results_reader.get_run_detail(run_id)
        if detail is None:
            return None
        run = dict(detail.run)
        return BacktestRunDetailModel(
            run_id=str(run.get("run_id") or run_id),
            strategy_name=str(run.get("strategy_name") or "--"),
            status=str(run.get("status") or "--"),
            benchmark=None if run.get("benchmark") is None else str(run.get("benchmark")),
            start_date=None if run.get("start_date") is None else str(run.get("start_date")),
            end_date=None if run.get("end_date") is None else str(run.get("end_date")),
            metrics=dict(detail.metrics),
            account_value_chart=[
                dict(item) for item in self._results_reader.build_account_value_chart(detail)
            ],
            trade_activity_chart=[
                dict(item) for item in self._results_reader.build_trade_activity_chart(detail)
            ],
            position_exposure_chart=[
                dict(item)
                for item in self._results_reader.build_position_exposure_chart(detail)
            ],
            yearly_return_chart=[
                dict(item) for item in self._results_reader.build_yearly_return_chart(detail)
            ],
        )

    def get_batch_summary(self, experiment_id: str) -> BatchExperimentSummaryModel | None:
        summary = self._batch_comparison_service.summarize_experiment(experiment_id)
        if summary is None:
            return None
        return BatchExperimentSummaryModel(
            experiment_id=summary.experiment_id,
            profile=summary.profile,
            status=summary.status,
            started_at=summary.started_at,
            finished_at=summary.finished_at,
            request_count=summary.request_count,
            success_count=summary.success_count,
            failure_count=summary.failure_count,
            rows=[
                BatchExperimentRowModel(
                    rank=row.rank,
                    run_id=row.run_id,
                    strategy_name=row.strategy_name,
                    strategy_id=row.strategy_id,
                    symbol=row.symbol,
                    annualized_returns=row.annualized_returns,
                    total_returns=row.total_returns,
                    max_drawdown=row.max_drawdown,
                    sharpe=row.sharpe,
                    status=row.status,
                    error_message=row.error_message,
                )
                for row in summary.rows
            ],
            yearly_rows=[dict(item) for item in summary.yearly_rows],
            failures=[dict(item) for item in summary.failures],
        )
