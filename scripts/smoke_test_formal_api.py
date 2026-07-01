"""Smoke test for the new formal API shell."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path



def _bootstrap() -> None:
    ensure_project_root_on_sys_path()



def main() -> None:
    _bootstrap()

    from app.main import AppServiceRegistry, SimpleApiApp, create_app
    from app.schemas.backtest import BacktestRunRequestPayload
    from app.schemas.market import MarketPriceHistoryQuery, MarketTradingCalendarQuery
    from app.services import BacktestService, MarketDataService, ReportingService
    from backtest_kernel import RqalphaRicequantGateway, RunSingleBacktest
    from config_center.providers.ricequant_config import RicequantConfig
    from data_platform import CachedMarketDataRepository, SqliteMetadataStore
    from reporting import BatchComparisonService, RunResultsReader

    database_path = Path("tmp") / "formal_api_smoke.sqlite3"
    market_service = MarketDataService(
        CachedMarketDataRepository(FakeMarketDataRepository(), SqliteMetadataStore(database_path))
    )
    backtest_service = BacktestService(
        RunSingleBacktest(
            RqalphaRicequantGateway(
                RicequantConfig(username="demo", password="demo"),
                runtime=FakeRqalphaRuntime(),
            )
        )
    )
    reporting_store = FakeReportingStore()
    reporting_service = ReportingService(
        RunResultsReader(reporting_store),
        BatchComparisonService(reporting_store),
    )
    app = create_app(
        AppServiceRegistry(
            market_data_service=market_service,
            backtest_service=backtest_service,
            reporting_service=reporting_service,
        )
    )
    if not isinstance(app, SimpleApiApp):
        raise SystemExit("formal API smoke test failed: expected fallback API shell")
    if len(app.routes) != 5:
        raise SystemExit("formal API smoke test failed: unexpected route count")

    routes = {route.name: route for route in app.routes}
    price_response = routes["market_price_history"].handler(
        MarketPriceHistoryQuery(
            symbol="000001.XSHE",
            start_date="2020-01-01",
            end_date="2020-01-02",
        )
    )
    if len(price_response.rows) != 2:
        raise SystemExit("formal API smoke test failed: price-history route returned no rows")

    calendar_response = routes["market_trading_calendar"].handler(
        MarketTradingCalendarQuery(
            start_date="2020-01-01",
            end_date="2020-01-02",
        )
    )
    if len(calendar_response.days) != 2:
        raise SystemExit("formal API smoke test failed: calendar route returned no days")

    backtest_response = routes["backtest_run_once"].handler(
        BacktestRunRequestPayload(
            run_id="api-smoke-run-001",
            strategy_name="moving_average_strategy",
            symbol="000001.XSHE",
            benchmark="000300.XSHG",
            start_date="2020-01-01",
            end_date="2020-12-31",
        )
    )
    if backtest_response.result.status.value != "completed":
        raise SystemExit("formal API smoke test failed: backtest route did not complete")

    run_detail_response = routes["reporting_run_detail"].handler("phase1-demo-run-001")
    if run_detail_response is None or not run_detail_response.detail.account_value_chart:
        raise SystemExit("formal API smoke test failed: run-detail route missing detail")

    batch_summary_response = routes["reporting_batch_summary"].handler("phase1-batch-001")
    if batch_summary_response is None or not batch_summary_response.summary.rows:
        raise SystemExit("formal API smoke test failed: batch-summary route missing rows")

    print("formal API smoke test passed")


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
            "run_id": str(payload.get("run_id") or "api-smoke-run"),
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
            "raw_result": {"engine": "formal-api-smoke"},
        }


class FakeReportingStore:
    def __init__(self) -> None:
        self._run = {
            "run_id": "phase1-demo-run-001",
            "strategy_name": "moving_average_strategy",
            "strategy_id": "ma_strategy_v1",
            "benchmark": "000300.XSHG",
            "universe": "000001.XSHE",
            "start_date": "2020-01-01",
            "end_date": "2020-12-31",
            "status": "completed",
            "created_at": "2020-01-01T09:30:00+08:00",
            "completed_at": "2020-12-31T15:00:00+08:00",
            "parameters": {"short_window": 5, "long_window": 20},
        }
        self._research_run = {
            "run_id": "phase1-batch-001",
            "strategy_name": "default_a_share",
            "status": "completed",
            "started_at": "2020-01-01T09:30:00+08:00",
            "finished_at": "2020-12-31T15:00:00+08:00",
            "parameters": {
                "profile": "default_a_share",
                "request_count": 1,
                "success_count": 1,
                "failure_count": 0,
                "run_ids": ["phase1-demo-run-001"],
                "failures": [],
            },
        }

    def fetch_backtest_run(self, run_id: str) -> Mapping[str, Any] | None:
        return self._run if run_id == self._run["run_id"] else None

    def fetch_backtest_metrics(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {"metric_name": "annualized_returns", "metric_value": 0.1234, "metric_text": None},
            {"metric_name": "total_returns", "metric_value": 0.2345, "metric_text": None},
            {"metric_name": "max_drawdown", "metric_value": -0.0567, "metric_text": None},
            {"metric_name": "sharpe", "metric_value": 1.89, "metric_text": None},
        ]

    def fetch_backtest_logs(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [{"recorded_at": "2020-01-01T09:31:00+08:00", "message": "ok"}]

    def fetch_backtest_trades(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "trade_time": "2020-02-03T10:00:00+08:00",
                "order_book_id": "000001.XSHE",
                "side": "BUY",
                "price": 10.2,
                "quantity": 100.0,
                "amount": 1020.0,
            }
        ]

    def fetch_backtest_positions(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "snapshot_time": "2020-02-03T15:00:00+08:00",
                "order_book_id": "000001.XSHE",
                "quantity": 100.0,
                "market_value": 1020.0,
                "notes": {},
            }
        ]

    def fetch_backtest_accounts(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "snapshot_time": "2020-02-03T15:00:00+08:00",
                "total_value": 1001020.0,
                "market_value": 1020.0,
                "cash": 1000000.0,
                "unit_net_value": 1.00102,
                "notes": {"account_type": "portfolio"},
            }
        ]

    def fetch_backtest_yearly_returns(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "year": "2020",
                "portfolio_return": 0.2345,
                "benchmark_return": 0.1567,
                "excess_return": 0.0778,
            }
        ]

    def fetch_research_run(self, run_id: str) -> Mapping[str, Any] | None:
        return self._research_run if run_id == self._research_run["run_id"] else None


if __name__ == "__main__":
    main()
