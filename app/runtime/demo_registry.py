"""Demo composition helpers for the formal local API shell."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.main import AppServiceRegistry, SimpleApiApp, create_app
from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
from app.services import (
    BacktestService,
    MarketDataService,
    PersistentBacktestService,
    ReportingService,
)
from backtest_kernel import RqalphaRicequantGateway, RunSingleBacktest
from config_center.providers.ricequant_config import RicequantConfig
from data_platform import CachedMarketDataRepository, SqliteMetadataStore
from reporting import BatchComparisonService, RunResultsReader



def build_demo_service_registry() -> AppServiceRegistry:
    database_path = Path("tmp") / "formal_http_demo.sqlite3"
    market_service = MarketDataService(
        CachedMarketDataRepository(FakeMarketDataRepository(), SqliteMetadataStore(database_path))
    )
    runtime_store = SqliteRuntimeStore(database_path)
    runtime_store.ensure_schema()
    _seed_demo_reporting_data(runtime_store)

    base_backtest_service = BacktestService(
        RunSingleBacktest(
            RqalphaRicequantGateway(
                RicequantConfig(username="demo", password="demo"),
                runtime=FakeRqalphaRuntime(),
            )
        )
    )
    backtest_service = PersistentBacktestService(base_backtest_service, runtime_store)
    reporting_service = ReportingService(
        RunResultsReader(runtime_store),
        BatchComparisonService(runtime_store),
    )
    return AppServiceRegistry(
        market_data_service=market_service,
        backtest_service=backtest_service,
        reporting_service=reporting_service,
    )



def build_demo_app() -> SimpleApiApp:
    return create_app(build_demo_service_registry())


class FakeMarketDataRepository:
    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "date": "2020-01-01",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 1000.0,
            },
            {
                "date": "2020-01-02",
                "open": 10.2,
                "high": 10.8,
                "low": 10.1,
                "close": 10.7,
                "volume": 1200.0,
            },
        ]

    def fetch_index_components(
        self,
        index_code: str,
        date: str | None = None,
    ) -> Sequence[str]:
        return ["000001.XSHE", "600000.XSHG"]

    def fetch_financial_indicators(
        self,
        symbol: str,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return []

    def fetch_trading_calendar(self, start_date: str, end_date: str) -> Sequence[str]:
        return [start_date, end_date]


class FakeRqalphaRuntime:
    def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "run_id": str(payload.get("run_id") or "demo-run"),
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
            "raw_result": {"engine": "formal-http-demo"},
        }



def _seed_demo_reporting_data(runtime_store: SqliteRuntimeStore) -> None:
    runtime_store.upsert_backtest_run(
        run_id="phase1-demo-run-001",
        strategy_name="moving_average_strategy",
        strategy_id="ma_strategy_v1",
        status="completed",
        benchmark="000300.XSHG",
        universe="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-12-31",
        created_at="2020-01-01T09:30:00+08:00",
        completed_at="2020-12-31T15:00:00+08:00",
        parameters={"short_window": 5, "long_window": 20},
        extra_config={},
        raw_result={"seeded": True},
        error_message=None,
    )
    runtime_store.replace_backtest_metrics(
        run_id="phase1-demo-run-001",
        metrics={
            "annualized_returns": 0.1234,
            "total_returns": 0.2345,
            "max_drawdown": -0.0567,
            "sharpe": 1.89,
        },
    )
    runtime_store.replace_backtest_logs(
        run_id="phase1-demo-run-001",
        rows=[
            {
                "recorded_at": "2020-01-01T09:31:00+08:00",
                "level": "INFO",
                "stage": "seed",
                "message": "ok",
            }
        ],
    )
    runtime_store.replace_backtest_trades(
        run_id="phase1-demo-run-001",
        rows=[
            {
                "trade_time": "2020-02-03T10:00:00+08:00",
                "order_book_id": "000001.XSHE",
                "side": "BUY",
                "price": 10.2,
                "quantity": 100.0,
                "amount": 1020.0,
            }
        ],
    )
    runtime_store.replace_backtest_positions(
        run_id="phase1-demo-run-001",
        rows=[
            {
                "snapshot_time": "2020-02-03T15:00:00+08:00",
                "order_book_id": "000001.XSHE",
                "quantity": 100.0,
                "market_value": 1020.0,
                "notes": {},
            }
        ],
    )
    runtime_store.replace_backtest_accounts(
        run_id="phase1-demo-run-001",
        rows=[
            {
                "snapshot_time": "2020-02-03T15:00:00+08:00",
                "total_value": 1001020.0,
                "market_value": 1020.0,
                "cash": 1000000.0,
                "unit_net_value": 1.00102,
                "notes": {"account_type": "portfolio"},
            }
        ],
    )
    runtime_store.replace_backtest_yearly_returns(
        run_id="phase1-demo-run-001",
        rows=[
            {
                "year": "2020",
                "portfolio_return": 0.2345,
                "benchmark_return": 0.1567,
                "excess_return": 0.0778,
            }
        ],
    )
    runtime_store.upsert_research_run(
        run_id="phase1-batch-001",
        strategy_name="default_a_share",
        status="completed",
        started_at="2020-01-01T09:30:00+08:00",
        finished_at="2020-12-31T15:00:00+08:00",
        parameters={
            "profile": "default_a_share",
            "request_count": 1,
            "success_count": 1,
            "failure_count": 0,
            "run_ids": ["phase1-demo-run-001"],
            "failures": [],
        },
    )
