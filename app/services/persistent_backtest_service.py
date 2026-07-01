"""Persistence-aware backtest execution service."""

from __future__ import annotations

from datetime import datetime, timezone

from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
from domain.backtest.models import BacktestResultSummary, BacktestRunRequest

from .backtest_service import BacktestService


class PersistentBacktestService:
    """Execute one backtest and persist runtime/task metadata into SQLite."""

    def __init__(
        self,
        backtest_service: BacktestService,
        runtime_store: SqliteRuntimeStore,
    ) -> None:
        self._backtest_service = backtest_service
        self._runtime_store = runtime_store

    def run_once(self, request: BacktestRunRequest) -> BacktestResultSummary:
        started_at = _utc_now()
        self._runtime_store.upsert_backtest_run(
            run_id=request.run_id,
            strategy_name=request.strategy_name,
            strategy_id=None,
            status="running",
            benchmark=request.benchmark,
            universe=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            created_at=started_at,
            completed_at=None,
            parameters=request.parameters,
            extra_config=request.extra_config,
            raw_result={},
            error_message=None,
        )
        try:
            result = self._backtest_service.run_once(request)
        except Exception as exc:
            self._runtime_store.upsert_backtest_run(
                run_id=request.run_id,
                strategy_name=request.strategy_name,
                strategy_id=None,
                status="failed",
                benchmark=request.benchmark,
                universe=request.symbol,
                start_date=request.start_date,
                end_date=request.end_date,
                created_at=started_at,
                completed_at=_utc_now(),
                parameters=request.parameters,
                extra_config=request.extra_config,
                raw_result={},
                error_message=str(exc),
            )
            self._runtime_store.replace_backtest_metrics(run_id=request.run_id, metrics={})
            raise

        self._runtime_store.upsert_backtest_run(
            run_id=request.run_id,
            strategy_name=result.strategy_name,
            strategy_id=None,
            status=result.status.value,
            benchmark=result.benchmark,
            universe=request.symbol,
            start_date=result.start_date,
            end_date=result.end_date,
            created_at=started_at,
            completed_at=_utc_now(),
            parameters=request.parameters,
            extra_config=request.extra_config,
            raw_result={},
            error_message=None,
        )
        self._runtime_store.replace_backtest_metrics(
            run_id=request.run_id,
            metrics=result.metrics,
        )
        self._runtime_store.replace_backtest_logs(run_id=request.run_id, rows=[])
        self._runtime_store.replace_backtest_trades(run_id=request.run_id, rows=[])
        self._runtime_store.replace_backtest_positions(run_id=request.run_id, rows=[])
        self._runtime_store.replace_backtest_accounts(run_id=request.run_id, rows=[])
        self._runtime_store.replace_backtest_yearly_returns(run_id=request.run_id, rows=[])
        return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
