"""Smoke test for runtime-task and reporting persistence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path



def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from app.services import BacktestService, BatchResearchService, PersistentBacktestService, ReportingService
    from backtest_kernel import RqalphaRicequantGateway, RunSingleBacktest
    from config_center.providers.ricequant_config import RicequantConfig
    from domain.backtest import BacktestRunRequest, BatchBacktestRunRequest
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
    batch_service = BatchResearchService(persistent_service, runtime_store)

    single_result = persistent_service.run_once(
        BacktestRunRequest(
            run_id="runtime-persist-run-001",
            strategy_name="moving_average_strategy",
            symbol="000001.XSHE",
            benchmark="000300.XSHG",
            start_date="2020-01-01",
            end_date="2020-12-31",
        )
    )
    if single_result.status.value != "completed":
        raise SystemExit("runtime persistence smoke test failed: persisted run not completed")

    batch_result = batch_service.run_batch(
        BatchBacktestRunRequest(
            experiment_id="runtime-batch-001",
            profile="default_a_share",
            runs=[
                BacktestRunRequest(
                    run_id="runtime-persist-run-002",
                    strategy_name="moving_average_strategy",
                    symbol="000001.XSHE",
                    benchmark="000300.XSHG",
                    start_date="2020-01-01",
                    end_date="2020-12-31",
                )
            ],
        )
    )
    if batch_result.status != "completed":
        raise SystemExit("runtime persistence smoke test failed: persisted batch not completed")

    reader = RunResultsReader(runtime_store)
    reader_detail = reader.get_run_detail("runtime-persist-run-001")
    if reader_detail is None or not reader_detail.logs or not reader_detail.trades:
        raise SystemExit("runtime persistence smoke test failed: raw persisted detail missing")
    if not reader_detail.positions or not reader_detail.accounts or not reader_detail.yearly_returns:
        raise SystemExit("runtime persistence smoke test failed: raw runtime snapshots missing")

    reporting_service = ReportingService(
        reader,
        BatchComparisonService(runtime_store),
    )
    detail = reporting_service.get_run_detail("runtime-persist-run-001")
    if detail is None or detail.metrics.get("annualized_returns") is None:
        raise SystemExit("runtime persistence smoke test failed: persisted detail missing")
    if not detail.trade_activity_chart or not detail.account_value_chart:
        raise SystemExit("runtime persistence smoke test failed: reporting charts missing")
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
            "raw_result": {
                "engine": "runtime-persistence-smoke",
                "logs": [
                    {
                        "recorded_at": "2020-01-03T09:35:00+08:00",
                        "level": "INFO",
                        "stage": "runtime",
                        "message": "runtime persistence smoke completed",
                    }
                ],
                "trades": [
                    {
                        "trade_time": "2020-02-03T10:00:00+08:00",
                        "order_book_id": "000001.XSHE",
                        "side": "BUY",
                        "price": 10.2,
                        "quantity": 100.0,
                        "amount": 1020.0,
                    }
                ],
                "positions": [
                    {
                        "snapshot_time": "2020-02-03T15:00:00+08:00",
                        "order_book_id": "000001.XSHE",
                        "quantity": 100.0,
                        "market_value": 1020.0,
                        "notes": {"source": "runtime"},
                    }
                ],
                "accounts": [
                    {
                        "snapshot_time": "2020-02-03T15:00:00+08:00",
                        "total_value": 1001020.0,
                        "market_value": 1020.0,
                        "cash": 1000000.0,
                        "unit_net_value": 1.00102,
                        "notes": {"account_type": "portfolio"},
                    }
                ],
                "yearly_returns": [
                    {
                        "year": "2020",
                        "portfolio_return": 0.2345,
                        "benchmark_return": 0.1567,
                        "excess_return": 0.0778,
                    }
                ],
            },
        }


if __name__ == "__main__":
    main()
