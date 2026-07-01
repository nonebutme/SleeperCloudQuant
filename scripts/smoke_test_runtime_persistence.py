"""Smoke test for runtime-task and reporting persistence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.services import BacktestService, ReportingService
    from app.services.persistent_backtest_service import PersistentBacktestService
    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from backtest_kernel import RqalphaRicequantGateway, RunSingleBacktest
    from config_center.providers.ricequant_config import RicequantConfig
    from domain.backtest import BacktestRunRequest
    from reporting import BatchComparisonService, RunResultsReader

    database_path = Path("tmp") / "formal_runtime_persistence.sqlite3"
    runtime_store = SqliteRuntimeStore(database_path)
    runtime_store.ensure_schema()

    base_backtest_service = BacktestService(
        RunSingleBacktest(
            RqalphaRicequantGateway(
                RicequantConfig(username="demo", password="demo"),
                runtime=FakeRqalphaRuntime(),
            )
        )
    )
    persistent_service = PersistentBacktestService(base_backtest_service, runtime_store)
    result = persistent_service.run_once(
        BacktestRunRequest(
            run_id="runtime-persist-run-001",
            strategy_name="moving_average_strategy",
            symbol="000001.XSHE",
            benchmark="000300.XSHG",
            start_date="2020-01-01",
            end_date="2020-12-31",
        )
    )
    if result.status.value != "completed":
        raise SystemExit("runtime persistence smoke test failed: persisted run not completed")

    runtime_store.upsert_research_run(
        run_id="runtime-batch-001",
        strategy_name="default_a_share",
        status="completed",
        started_at="2020-01-01T09:30:00+08:00",
        finished_at="2020-12-31T15:00:00+08:00",
        parameters={
            "profile": "default_a_share",
            "request_count": 1,
            "success_count": 1,
            "failure_count": 0,
            "run_ids": ["runtime-persist-run-001"],
            "failures": [],
        },
    )

    reporting_service = ReportingService(
        RunResultsReader(runtime_store),
        BatchComparisonService(runtime_store),
    )
    detail = reporting_service.get_run_detail("runtime-persist-run-001")
    if detail is None or detail.metrics.get("annualized_returns") is None:
        raise SystemExit("runtime persistence smoke test failed: persisted detail missing")
    batch_summary = reporting_service.get_batch_summary("runtime-batch-001")
    if batch_summary is None or not batch_summary.rows:
        raise SystemExit("runtime persistence smoke test failed: persisted batch missing")

    print("runtime persistence smoke test passed")


class FakeRqalphaRuntime:
    """Deterministic runtime for persistence validation."""

    def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "run_id": str(payload.get("run_id") or "runtime-persist-run"),
            "strategy_name": str(payload.get("strategy_name") or "unknown_strategy"),
            "status": "completed",
            "start_date": str(payload.get("start_date") or "2020-01-01"),
            "end_date": str(payload.get("end_date") or "2020-12-31"),
            "benchmark": str(payload.get("benchmark") or "000300.XSHG"),
            "metrics": {
                "annualized_returns": 0.1234,
                "total_returns": 0.2345,
                "max_drawdown": -0.0567,
                "sharpe": 1.89,
            },
            "raw_result": {"engine": "runtime-persistence-smoke"},
        }


if __name__ == "__main__":
    main()
