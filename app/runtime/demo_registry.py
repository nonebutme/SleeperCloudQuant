"""Demo composition helpers for the formal local API shell."""

from __future__ import annotations

import json

from collections.abc import Mapping, Sequence
import os
from pathlib import Path
from typing import Any

from app.main import AppServiceRegistry, SimpleApiApp, create_app
from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
from app.services import (
    AIAnalysisService,
    BacktestService,
    BacktestModeReportService,
    BatchResearchService,
    ConfigCenterService,
    DataCenterService,
    FactorResearchService,
    IndependentScreeningService,
    LLMProviderGateway,
    MarketDataService,
    MarketPanoramaService,
    PersistentBacktestService,
    ReportingService,
    SharedPortfolioService,
    SingleBacktestTaskService,
    StrategyService,
    StrategyDatasetService,
    StrategyDatasetResolver,
)
from backtest_kernel import LocalSQLiteBacktestRuntime, RqalphaPackageRuntime, RqalphaRicequantGateway, RunSingleBacktest
from config_center import UnifiedConfigManager
from config_center.providers.ricequant_config import RicequantConfig
from data_platform import AShareGovernanceStore, AShareSyncScheduler, ClassificationHistoryStore, DataCenterStore, MarketPanoramaStore, AShareMarketStore, AShareSQLiteRepository, CachedMarketDataRepository, ExternalMarketProviderRepository, LegacySQLiteMarketDataRepository, SqliteMetadataStore
from data_platform.providers.akshare_governance_provider import AkshareGovernanceProvider
from factor_lab import FactorDefinition, FactorValue, SqliteFactorStore
from reporting import BatchComparisonService, RunResultsReader


def build_demo_service_registry() -> AppServiceRegistry:
    database_path = Path("tmp") / "formal_http_demo.sqlite3"
    upstream_market_repository = _build_market_repository()
    canonical_a_share_repository = AShareMarketStore(_resolve_a_share_canonical_database_path())
    governance_repository = AShareGovernanceStore(_resolve_a_share_canonical_database_path())
    governance_repository.ensure_schema()
    a_share_scheduler = AShareSyncScheduler(
        _resolve_a_share_canonical_database_path(),
        market_store=canonical_a_share_repository,
        governance_store=governance_repository,
        provider=AkshareGovernanceProvider(
            proxy_url=os.environ.get("SCQ_AKSHARE_PROXY"),
            retry_count=int(os.environ.get("SCQ_A_SHARE_SCHEDULER_PROVIDER_RETRIES", "2")),
        ),
        requests_per_minute=int(os.environ.get("SCQ_A_SHARE_SCHEDULER_RPM", "60")),
        max_workers=int(os.environ.get("SCQ_A_SHARE_SCHEDULER_WORKERS", "4")),
        retry_count=int(os.environ.get("SCQ_A_SHARE_SCHEDULER_RETRIES", "3")),
    )
    a_share_scheduler.ensure_schema()
    # Stage B freezes business sync as manual-only. Recovery remains enabled,
    # but the web runtime never creates a daily task or changes the default version.
    current_schedule = a_share_scheduler.get_status()
    a_share_scheduler.configure(
        enabled=False,
        run_time=str(current_schedule.get("run_time") or "18:15"),
        timezone_name="Asia/Shanghai",
        adjustments=("raw", "qfq", "hfq"),
    )
    a_share_scheduler.recover_interrupted_jobs()
    a_share_repository = (
        canonical_a_share_repository
        if canonical_a_share_repository.has_daily_data()
        else AShareSQLiteRepository(_resolve_a_share_database_path())
    )
    backtest_market_repository = canonical_a_share_repository if canonical_a_share_repository.has_daily_data() else upstream_market_repository
    panorama_service = MarketPanoramaService(
        MarketPanoramaStore(Path("var/runtime/market_panorama.sqlite3")),
        market_database=_resolve_a_share_canonical_database_path(),
        classification_database=Path("var/runtime/a_share_classification_history.sqlite3"),
        max_workers=int(os.environ.get("SCQ_PANORAMA_WORKERS", "4")),
    )
    market_service = MarketDataService(        CachedMarketDataRepository(upstream_market_repository, SqliteMetadataStore(database_path)),
        a_share_repository=a_share_repository,
        governance_repository=governance_repository,
        panorama_service=panorama_service,
    )
    factor_store = SqliteFactorStore(database_path)
    factor_service = FactorResearchService(
        market_service,
        factor_store,
    )
    factor_service.run_factor_for_symbols(
        factor_id="close_to_close_return_1d",
        symbols=["000001.XSHE", "600000.XSHG"],
        start_date="2020-01-01",
        end_date="2020-01-02",
    )
    factor_service.run_factor_for_symbols(
        factor_id="close_to_ma2_bias",
        symbols=["000001.XSHE", "600000.XSHG"],
        start_date="2020-01-01",
        end_date="2020-01-02",
    )
    _seed_tie_rank_factor(factor_store)
    runtime_store = SqliteRuntimeStore(database_path)
    runtime_store.ensure_schema()
    _seed_demo_reporting_data(runtime_store)
    strategy_service = StrategyService()
    strategy_dataset_resolver = StrategyDatasetResolver(governance_repository, canonical_a_share_repository)

    base_backtest_service = BacktestService(
        RunSingleBacktest(
            RqalphaRicequantGateway(
                RicequantConfig(username="demo", password="demo"),
                runtime=RqalphaPackageRuntime(
                    LocalSQLiteBacktestRuntime(
                        backtest_market_repository,
                        strategy_resolver=strategy_service.resolve_version,
                        dataset_resolver=strategy_dataset_resolver.resolve,
                    )
                ),
            )
        )
    )
    backtest_service = PersistentBacktestService(base_backtest_service, runtime_store, market_service)
    batch_research_service = BatchResearchService(backtest_service, runtime_store)
    classification_store = ClassificationHistoryStore()
    independent_screening_service = IndependentScreeningService(
        backtest_service,
        market_service,
        strategy_service,
        runtime_store,
        classification_store=classification_store,
        dataset_resolver=strategy_dataset_resolver.resolve,
    )
    single_backtest_task_service = SingleBacktestTaskService(backtest_service)
    shared_portfolio_service = SharedPortfolioService(
        market_service,
        strategy_service,
        runtime_store,
        dataset_resolver=strategy_dataset_resolver.resolve,
    )
    reporting_service = ReportingService(
        RunResultsReader(runtime_store),
        BatchComparisonService(runtime_store),
        snapshot_store=runtime_store,
    )
    backtest_mode_report_service = BacktestModeReportService(
        reporting_service,
        independent_screening_service,
        shared_portfolio_service,
        runtime_store,
        classification_store,
    )
    ai_analysis_service = AIAnalysisService(market_service, factor_service, workflow_store=runtime_store, llm_provider=LLMProviderGateway())
    config_center_service = ConfigCenterService(
        UnifiedConfigManager(),
        a_share_scheduler=a_share_scheduler,
    )
    data_center_store = DataCenterStore(_resolve_a_share_canonical_database_path())
    data_center_service = DataCenterService(
        DataCenterStore(_resolve_a_share_canonical_database_path()),
        a_share_scheduler,
        governance_repository,
        panorama_service=panorama_service,
    )
    strategy_dataset_service = StrategyDatasetService(data_center_store, strategy_dataset_resolver)
    return AppServiceRegistry(
        market_data_service=market_service,
        factor_research_service=factor_service,
        backtest_service=backtest_service,
        batch_research_service=batch_research_service,
        reporting_service=reporting_service,
        strategy_service=strategy_service,
        independent_screening_service=independent_screening_service,
        shared_portfolio_service=shared_portfolio_service,
        single_backtest_task_service=single_backtest_task_service,
        backtest_mode_report_service=backtest_mode_report_service,
        ai_analysis_service=ai_analysis_service,
        config_center_service=config_center_service,
        data_center_service=data_center_service,
        strategy_dataset_service=strategy_dataset_service,
    )



def _build_market_repository():
    market_config = _load_market_provider_config()
    external_repository = ExternalMarketProviderRepository(
        base_url=market_config.get("base_url"),
        provider_name=market_config.get("provider_name"),
        timeout_seconds=market_config.get("timeout_seconds"),
        enabled=market_config.get("enabled"),
        endpoint_spec=market_config.get("endpoint_spec"),
    )
    legacy_path = _resolve_legacy_market_database_path()
    fallback = FakeMarketDataRepository()
    if legacy_path is not None:
        legacy_repository = LegacySQLiteMarketDataRepository(legacy_path)
        if legacy_repository.is_available():
            fallback = FallbackMarketDataRepository(legacy_repository, fallback)
    return FallbackMarketDataRepository(external_repository, fallback, prefer_primary_when_available=True)



def _load_market_provider_config() -> dict[str, object]:
    draft_path = Path("var/runtime/config_runtime_draft.json")
    if not draft_path.is_file():
        return {"enabled": False, "provider_name": "open-http-market-provider", "base_url": "", "timeout_seconds": 8}
    try:
        raw = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "provider_name": "open-http-market-provider", "base_url": "", "timeout_seconds": 8}
    settings = raw.get("settings") if isinstance(raw, dict) else {}
    market_provider = settings.get("market_provider") if isinstance(settings, dict) else {}
    if not isinstance(market_provider, dict):
        return {"enabled": False, "provider_name": "open-http-market-provider", "base_url": "", "timeout_seconds": 8}
    return {
        "enabled": bool(market_provider.get("enabled", False)),
        "provider_name": str(market_provider.get("provider_name") or "open-http-market-provider"),
        "base_url": str(market_provider.get("base_url") or ""),
        "timeout_seconds": market_provider.get("timeout_seconds", 8),
        "endpoint_spec": market_provider.get("endpoint_spec", {}),
    }

def _env_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
def _resolve_legacy_market_database_path() -> Path | None:
    configured = os.environ.get("SCQ_LEGACY_MARKET_DB_PATH")
    if configured:
        return Path(configured)
    candidate = (
        Path(__file__).resolve().parents[3]
        / "SleeperCloudQuant-old"
        / "SleeperCloudQuant"
        / "data"
        / "app_cache.db"
    )
    return candidate if candidate.is_file() else None

def _resolve_a_share_canonical_database_path() -> Path:
    configured = os.environ.get("SCQ_A_SHARE_CANONICAL_DB_PATH")
    return Path(configured) if configured else Path("var/market/a_share_market.sqlite3")


def _resolve_a_share_database_path() -> Path:
    configured = os.environ.get("SCQ_A_SHARE_DB_PATH")
    if configured:
        return Path(configured)
    return (
        Path(__file__).resolve().parents[3]
        / "SleeperCloudQuant-old"
        / "PyDB"
        / "StockMarket"
        / "stock_database"
        / "data"
        / "stockmarket.db"
    )


def build_demo_app() -> SimpleApiApp:
    return create_app(build_demo_service_registry())



class FallbackMarketDataRepository:
    def __init__(self, primary, fallback, *, prefer_primary_when_available: bool = False) -> None:
        self._primary = primary
        self._fallback = fallback
        self._prefer_primary_when_available = prefer_primary_when_available
        self._last_source_trace: dict[str, Any] = {}

    def get_source_trace(self) -> dict[str, Any]:
        return {
            "repository": type(self).__name__,
            "prefer_primary_when_available": self._prefer_primary_when_available,
            "primary": self._repository_status(self._primary),
            "fallback": self._repository_status(self._fallback),
            "last_call": dict(self._last_source_trace),
        }

    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        primary_rows, primary_error = self._read_primary(
            lambda: list(self._primary.fetch_price_history(symbol, start_date=start_date, end_date=end_date))
        )
        fallback_rows = list(self._fallback.fetch_price_history(symbol, start_date=start_date, end_date=end_date))
        selected_rows, selected_source, reason = self._select_rows(primary_rows, fallback_rows, primary_error)
        self._record_source_trace(
            dataset="price_history",
            selected_source=selected_source,
            reason=reason,
            primary_row_count=len(primary_rows),
            fallback_row_count=len(fallback_rows),
            primary_error=primary_error,
        )
        return selected_rows

    def fetch_index_components(
        self,
        index_code: str,
        date: str | None = None,
    ) -> Sequence[str]:
        primary_rows, primary_error = self._read_primary(lambda: list(self._primary.fetch_index_components(index_code, date=date)))
        if primary_rows:
            self._record_source_trace("index_components", "primary", "primary_available", len(primary_rows), 0, primary_error)
            return primary_rows
        fallback_rows = list(self._fallback.fetch_index_components(index_code, date=date))
        self._record_source_trace("index_components", "fallback", "primary_error" if primary_error else "primary_empty", len(primary_rows), len(fallback_rows), primary_error)
        return fallback_rows

    def fetch_financial_indicators(
        self,
        symbol: str,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        primary_rows, primary_error = self._read_primary(lambda: list(self._primary.fetch_financial_indicators(symbol, report_date=report_date)))
        if primary_rows:
            self._record_source_trace("financial_indicators", "primary", "primary_available", len(primary_rows), 0, primary_error)
            return primary_rows
        fallback_rows = list(self._fallback.fetch_financial_indicators(symbol, report_date=report_date))
        self._record_source_trace("financial_indicators", "fallback", "primary_error" if primary_error else "primary_empty", len(primary_rows), len(fallback_rows), primary_error)
        return fallback_rows

    def fetch_trading_calendar(self, start_date: str, end_date: str) -> Sequence[str]:
        primary_rows, primary_error = self._read_primary(lambda: list(self._primary.fetch_trading_calendar(start_date, end_date)))
        fallback_rows = list(self._fallback.fetch_trading_calendar(start_date, end_date))
        selected_rows, selected_source, reason = self._select_rows(primary_rows, fallback_rows, primary_error)
        self._record_source_trace(
            dataset="trading_calendar",
            selected_source=selected_source,
            reason=reason,
            primary_row_count=len(primary_rows),
            fallback_row_count=len(fallback_rows),
            primary_error=primary_error,
        )
        return selected_rows

    def _read_primary(self, loader) -> tuple[list[Any], str | None]:
        try:
            return list(loader()), None
        except Exception as error:  # pragma: no cover - fallback safety net for user-configured providers.
            return [], f"{type(error).__name__}: {error}"

    def _select_rows(self, primary_rows: list[Any], fallback_rows: list[Any], primary_error: str | None) -> tuple[list[Any], str, str]:
        if self._prefer_primary_when_available and primary_rows:
            return primary_rows, "primary", "primary_available"
        if primary_error:
            return fallback_rows, "fallback", "primary_error"
        if len(primary_rows) >= len(fallback_rows) and primary_rows:
            return primary_rows, "primary", "primary_has_more_or_equal_rows"
        return fallback_rows, "fallback", "fallback_longer" if fallback_rows else "primary_empty"

    def _record_source_trace(
        self,
        dataset: str,
        selected_source: str,
        reason: str,
        primary_row_count: int,
        fallback_row_count: int,
        primary_error: str | None = None,
    ) -> None:
        self._last_source_trace = {
            "dataset": dataset,
            "selected_source": selected_source,
            "reason": reason,
            "primary_row_count": primary_row_count,
            "fallback_row_count": fallback_row_count,
            "primary_error": primary_error,
        }

    def _repository_status(self, repository) -> dict[str, Any]:
        if hasattr(repository, "provider_status"):
            return dict(repository.provider_status())
        if hasattr(repository, "get_source_trace"):
            return dict(repository.get_source_trace())
        return {"repository": type(repository).__name__}
class FakeMarketDataRepository:
    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        if symbol == "600000.XSHG":
            return [
                {
                    "date": "2020-01-01",
                    "open": 8.0,
                    "high": 8.4,
                    "low": 7.9,
                    "close": 8.0,
                    "volume": 2000.0,
                },
                {
                    "date": "2020-01-02",
                    "open": 8.0,
                    "high": 8.8,
                    "low": 8.0,
                    "close": 8.8,
                    "volume": 2500.0,
                },
            ]
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
        if index_code != "000300.XSHG":
            return []
        if date == "2020-01-01":
            return ["000001.XSHE"]
        if date == "2020-01-03":
            return ["600000.XSHG"]
        return ["000001.XSHE", "600000.XSHG"]

    def fetch_financial_indicators(
        self,
        symbol: str,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return []

    def fetch_trading_calendar(self, start_date: str, end_date: str) -> Sequence[str]:
        return ["2020-01-01", "2020-01-02", "2020-01-03"]


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
            "raw_result": {
                "engine": "formal-http-demo",
                "logs": [
                    {
                        "recorded_at": "2020-01-03T09:35:00+08:00",
                        "level": "INFO",
                        "stage": "runtime",
                        "message": "demo runtime completed",
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



def _seed_tie_rank_factor(factor_store: SqliteFactorStore) -> None:
    factor_store.save_factor_values(
        definition=FactorDefinition(factor_id="tie_rank_factor", name="Tie Rank Factor"),
        symbol="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-01-02",
        rows=[FactorValue(factor_id="tie_rank_factor", symbol="000001.XSHE", trade_date="2020-01-02", value=1.0)],
    )
    factor_store.save_factor_values(
        definition=FactorDefinition(factor_id="tie_rank_factor", name="Tie Rank Factor"),
        symbol="600000.XSHG",
        start_date="2020-01-01",
        end_date="2020-01-02",
        rows=[FactorValue(factor_id="tie_rank_factor", symbol="600000.XSHG", trade_date="2020-01-02", value=1.0)],
    )
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
