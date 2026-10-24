"""Batch research orchestration backed by runtime persistence."""

from __future__ import annotations
from data_platform.maintenance_transaction import guarded_research

from datetime import datetime, timezone
from typing import Protocol

from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
from domain.backtest.models import (
    BacktestResultSummary,
    BacktestRunRequest,
    BatchBacktestRunRequest,
    BatchBacktestRunSummary,
)


class SingleRunBacktestService(Protocol):
    """Minimal protocol required by the batch orchestrator."""

    def run_once(self, request: BacktestRunRequest) -> BacktestResultSummary:
        ...


class BatchResearchService:
    """Run a batch of backtests and persist one experiment summary."""

    def __init__(
        self,
        single_run_service: SingleRunBacktestService,
        runtime_store: SqliteRuntimeStore,
    ) -> None:
        self._single_run_service = single_run_service
        self._runtime_store = runtime_store

    @guarded_research
    def run_batch(self, request: BatchBacktestRunRequest) -> BatchBacktestRunSummary:
        started_at = _utc_now()
        run_ids = [run.run_id for run in request.runs]
        self._runtime_store.upsert_research_run(
            run_id=request.experiment_id,
            strategy_name=request.profile,
            status="running",
            started_at=started_at,
            finished_at=None,
            parameters={
                "profile": request.profile,
                "request_count": len(request.runs),
                "success_count": 0,
                "failure_count": 0,
                "run_ids": run_ids,
                "failures": [],
            },
        )

        success_count = 0
        successful_run_ids: list[str] = []
        failures: list[dict[str, str]] = []
        for run in request.runs:
            try:
                result = self._single_run_service.run_once(run)
            except Exception as exc:
                failures.append(
                    {
                        "run_id": run.run_id,
                        "failure_type": "runtime_error",
                        "failure_stage": "run_once",
                        "failure_code": "BACKTEST_RUN_ONCE_RUNTIME_ERROR",
                        "failure_source": "single_run_service",
                        "error_message": str(exc),
                    }
                )
                continue
            if result.status.value == "completed":
                success_count += 1
                successful_run_ids.append(result.run_id)
            else:
                failures.append(
                    {
                        "run_id": result.run_id,
                        "failure_type": "unexpected_status",
                        "failure_stage": "result_status_check",
                        "failure_code": "BACKTEST_UNEXPECTED_RESULT_STATUS",
                        "failure_source": "result_summary",
                        "expected_status": "completed",
                        "result_status": result.status.value,
                        "status_transition": f"completed->{result.status.value}",
                        "error_message": f"unexpected status: {result.status.value}",
                    }
                )

        finished_at = _utc_now()
        failure_count = len(failures)
        status = _derive_batch_status(request_count=len(request.runs), success_count=success_count)
        self._runtime_store.upsert_research_run(
            run_id=request.experiment_id,
            strategy_name=request.profile,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            parameters={
                "profile": request.profile,
                "request_count": len(request.runs),
                "success_count": success_count,
                "failure_count": failure_count,
                "run_ids": run_ids,
                "failures": failures,
            },
        )
        return BatchBacktestRunSummary(
            experiment_id=request.experiment_id,
            profile=request.profile,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            request_count=len(request.runs),
            success_count=success_count,
            failure_count=failure_count,
            run_ids=run_ids,
            successful_run_ids=successful_run_ids,
            failures=failures,
        )



def _derive_batch_status(*, request_count: int, success_count: int) -> str:
    if request_count <= 0:
        return "empty"
    if success_count <= 0:
        return "failed"
    if success_count < request_count:
        return "partial_failed"
    return "completed"



def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
