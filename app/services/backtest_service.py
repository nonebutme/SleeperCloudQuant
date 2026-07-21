"""Service-layer facade for formal backtest execution."""

from __future__ import annotations

from collections.abc import Mapping

from backtest_kernel import RunSingleBacktest, RunSingleBacktestRequest
from domain.backtest.models import BacktestResultSummary, BacktestRunRequest
from domain.common.enums import BacktestRunStatus


class BacktestService:
    """Wrap the formal backtest use case with stable application models."""

    def __init__(self, use_case: RunSingleBacktest) -> None:
        self._use_case = use_case

    def run_once(self, request: BacktestRunRequest) -> BacktestResultSummary:
        summary, _ = self.run_once_with_raw_result(request)
        return summary

    def run_once_with_raw_result(
        self,
        request: BacktestRunRequest,
    ) -> tuple[BacktestResultSummary, Mapping[str, object]]:
        result = self._use_case.execute(
            RunSingleBacktestRequest(
                run_id=request.run_id,
                strategy_name=request.strategy_name,
                symbol=request.symbol,
                benchmark=request.benchmark,
                start_date=request.start_date,
                end_date=request.end_date,
                initial_cash=request.initial_cash,
                frequency=request.frequency,
                parameters=request.parameters,
                extra_config=request.extra_config,
            )
        )
        return (
            BacktestResultSummary(
                run_id=result.run_id,
                strategy_name=result.strategy_name,
                status=BacktestRunStatus(str(result.status)),
                start_date=result.start_date,
                end_date=result.end_date,
                benchmark=result.benchmark,
                metrics=dict(result.metrics),
            ),
            dict(result.raw_result),
        )
