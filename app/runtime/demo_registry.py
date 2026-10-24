"""Demo composition helpers for the formal local API shell."""

from __future__ import annotations

import json

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from hashlib import sha256
import os
from pathlib import Path
from typing import Any

from app.main import AppServiceRegistry, SimpleApiApp, create_app
from app.runtime.database_paths import backtest_runtime_database_path
from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
from app.services import (
    AIAnalysisService,
    BacktestService,
    BacktestModeReportService,
    BatchResearchService,
    ConfigCenterService,
    DataCenterService,
    FactorAnalysisService,
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
from data_platform import AShareGovernanceStore, AShareSyncScheduler, ClassificationHistoryStore, DataCenterStore, MarketPanoramaStore, AShareMarketStore, AShareSQLiteRepository, CachedMarketDataRepository, LegacySQLiteMarketDataRepository, SqliteMetadataStore
from data_platform.providers.akshare_governance_provider import AkshareGovernanceProvider
from factor_lab import FactorDefinition, FactorValue, SqliteFactorStore
from factor_lab.storage import SqliteFactorResearchStore
from reporting import BatchComparisonService, RunResultsReader


_DEMO_GOVERNED_MARKET_SOURCE = "scq_demo_governed_seed_v1"
_DEMO_GOVERNED_QUALITY_REPORT_ID = "scq-demo-governed-market-v1-quality"
_DEMO_GOVERNED_START_DATE = "2020-01-01"
_DEMO_GOVERNED_END_DATE = "2020-12-31"
_DEMO_GOVERNED_SYMBOLS = (
    ("000001.XSHE", "平安银行", 10.0),
    ("000002.XSHE", "万科A", 12.0),
    ("600000.XSHG", "浦发银行", 8.0),
)


def build_demo_service_registry() -> AppServiceRegistry:
    database_path = backtest_runtime_database_path()
    upstream_market_repository = _build_market_repository()
    canonical_a_share_repository = AShareMarketStore(_resolve_a_share_canonical_database_path())
    governance_repository = AShareGovernanceStore(_resolve_a_share_canonical_database_path())
    governance_repository.ensure_schema()
    demo_seed_enabled = os.environ.get("SCQ_ENABLE_DEMO_SEED") == "1"
    if demo_seed_enabled:
        _seed_demo_governed_market_data(
            canonical_a_share_repository,
            governance_repository,
        )
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
    market_service = MarketDataService(
        CachedMarketDataRepository(upstream_market_repository, SqliteMetadataStore(database_path)),
        a_share_repository=a_share_repository,
        governance_repository=governance_repository,
        panorama_service=panorama_service,
    )
    factor_store = SqliteFactorStore(database_path)
    factor_service = FactorResearchService(
        market_service,
        factor_store,
    )
    if demo_seed_enabled:
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
    if demo_seed_enabled:
        _seed_demo_reporting_data(runtime_store)
    strategy_service = StrategyService()
    data_center_store = DataCenterStore(_resolve_a_share_canonical_database_path())
    data_center_store.ensure_schema()
    factor_research_store = SqliteFactorResearchStore(
        Path("var/runtime/factor_research.sqlite3"), index_store=data_center_store
    )
    from app.services.indicator_service import IndicatorService
    indicator_service = IndicatorService(_resolve_a_share_canonical_database_path())
    strategy_dataset_resolver = StrategyDatasetResolver(
        governance_repository, canonical_a_share_repository, factor_research_store, indicator_service
    )

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
    factor_analysis_service = FactorAnalysisService(
        market_database_path=_resolve_a_share_canonical_database_path(),
        research_store=factor_research_store,
        classification_store=classification_store,
    )
    indicator_service.factors = factor_analysis_service
    independent_screening_service = IndependentScreeningService(
        backtest_service,
        market_service,
        strategy_service,
        runtime_store,
        classification_store=classification_store,
        dataset_resolver=strategy_dataset_resolver.resolve,
    )
    single_backtest_task_service = SingleBacktestTaskService(
        backtest_service, market_data_service=market_service,
        strategy_service=strategy_service, dataset_resolver=strategy_dataset_resolver.resolve,
    )
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
    data_center_service = DataCenterService(
        DataCenterStore(_resolve_a_share_canonical_database_path()),
        a_share_scheduler,
        governance_repository,
        panorama_service=panorama_service,
        trading_status_remediation_dir=Path(
            "var/runtime/trading_status_remediation"
        ),
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
        factor_analysis_service=factor_analysis_service,
        indicator_service=indicator_service,
    )



def _build_market_repository():
    legacy_path = _resolve_legacy_market_database_path()
    fallback = FakeMarketDataRepository()
    if legacy_path is not None:
        legacy_repository = LegacySQLiteMarketDataRepository(legacy_path)
        if legacy_repository.is_available():
            fallback = FallbackMarketDataRepository(legacy_repository, fallback)
    return fallback

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



def _seed_demo_governed_market_data(
    market_store: AShareMarketStore,
    governance_store: AShareGovernanceStore,
) -> dict[str, Any]:
    """Publish a deterministic governed fixture only for explicit demo runtimes."""

    if os.environ.get("SCQ_ENABLE_DEMO_SEED") != "1":
        return {"status": "disabled"}

    market_store.ensure_schema()
    governance_store.ensure_schema()
    rows = _build_demo_governed_market_rows()
    member = _demo_governed_market_member(rows)
    current = governance_store.fetch_current_published_data_version()
    if current.get("status") != "not_found":
        if not _is_demo_governed_version(current, member):
            return {
                "status": "skipped_existing_governed_version",
                "data_version_id": current.get("data_version_id"),
            }
        if not _demo_governed_physical_rows_match(market_store, member):
            raise RuntimeError(
                "demo governed market seed does not match its published physical rows"
            )
        return {
            "status": "already_ready",
            "data_version_id": current.get("data_version_id"),
        }

    if market_store.has_daily_data():
        raise RuntimeError(
            "demo governed market seed refuses to label an existing ungoverned market database"
        )

    market_store.upsert_symbols(
        {
            "symbol": symbol,
            "name": name,
            "listing_status": "current",
            "source": _DEMO_GOVERNED_MARKET_SOURCE,
        }
        for symbol, name, _ in _DEMO_GOVERNED_SYMBOLS
    )
    market_store.upsert_daily_prices(
        rows,
        adjustment="raw",
        source=_DEMO_GOVERNED_MARKET_SOURCE,
    )
    governance_store.save_quality_report(
        quality_report_id=_DEMO_GOVERNED_QUALITY_REPORT_ID,
        rule_version="demo-governed-market-v1",
        status="passed",
        payload={
            "scope": "explicit_demo_fixture_only",
            "source": _DEMO_GOVERNED_MARKET_SOURCE,
            "dataset": "market_daily_prices",
            "adjustment": "raw",
            "symbols": [item[0] for item in _DEMO_GOVERNED_SYMBOLS],
            "row_count": len(rows),
            "min_date": _DEMO_GOVERNED_START_DATE,
            "max_date": _DEMO_GOVERNED_END_DATE,
            "content_hash": member["content_hash"],
            "checks": {
                "ohlc_valid": True,
                "volume_non_negative": True,
                "duplicate_primary_keys": 0,
                "deterministic_fixture": True,
            },
        },
    )
    published = governance_store.publish_data_version(
        as_of_trade_date=_DEMO_GOVERNED_END_DATE,
        quality_report_id=_DEMO_GOVERNED_QUALITY_REPORT_ID,
        members=[member],
        notes="Explicit demo-only governed OHLCV fixture; never sourced from a formal database.",
    )
    if not _demo_governed_physical_rows_match(market_store, member):
        raise RuntimeError("demo governed market seed physical verification failed")
    return {
        "status": "published",
        "data_version_id": published.get("data_version_id"),
    }


def _build_demo_governed_market_rows() -> list[dict[str, Any]]:
    start = date.fromisoformat(_DEMO_GOVERNED_START_DATE)
    end = date.fromisoformat(_DEMO_GOVERNED_END_DATE)
    trading_days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            trading_days.append(current)
        current += timedelta(days=1)

    wave = (-0.025, -0.012, 0.0, 0.018, 0.035, 0.012, -0.01, -0.032, -0.008, 0.022)
    rows: list[dict[str, Any]] = []
    for symbol_index, (symbol, _, base_price) in enumerate(_DEMO_GOVERNED_SYMBOLS):
        previous_close = base_price
        for index, trade_day in enumerate(trading_days):
            drift = index * 0.00015
            close = round(base_price * (1.0 + drift + wave[(index + symbol_index) % len(wave)]), 4)
            open_price = round(previous_close, 4)
            high = round(max(open_price, close) * 1.008, 4)
            low = round(min(open_price, close) * 0.992, 4)
            volume = float(1_000_000 + symbol_index * 100_000 + index * 1_000)
            change_amount = round(close - previous_close, 4)
            change_pct = round(change_amount / previous_close * 100.0, 6) if previous_close else 0.0
            rows.append(
                {
                    "symbol": symbol,
                    "date": trade_day.isoformat(),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "amount": round(close * volume, 2),
                    "amplitude": round((high - low) / previous_close * 100.0, 6),
                    "change_pct": change_pct,
                    "change_amount": change_amount,
                    "turnover_rate": round(0.5 + (index % 10) * 0.05, 4),
                }
            )
            previous_close = close
    return rows


def _demo_governed_market_member(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    serialized = json.dumps(
        {"schema": "demo-governed-ohlcv-v1", "rows": list(rows)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "dataset": "market_daily_prices",
        "adjustment": "raw",
        "symbol_scope": "demo:" + ",".join(item[0] for item in _DEMO_GOVERNED_SYMBOLS),
        "row_count": len(rows),
        "symbol_count": len(_DEMO_GOVERNED_SYMBOLS),
        "min_date": _DEMO_GOVERNED_START_DATE,
        "max_date": _DEMO_GOVERNED_END_DATE,
        "source": _DEMO_GOVERNED_MARKET_SOURCE,
        "sync_run_ref": "explicit-demo-seed-v1",
        "content_hash": sha256(serialized.encode("utf-8")).hexdigest(),
        "quality_status": "passed",
        "details": {
            "fixture": True,
            "demo_only": True,
            "physical_adjustment": "raw",
        },
    }


def _is_demo_governed_version(
    version: Mapping[str, Any],
    member: Mapping[str, Any],
) -> bool:
    raw_member = next(
        (
            item
            for item in version.get("members") or []
            if item.get("dataset") == "market_daily_prices"
            and item.get("adjustment") == "raw"
        ),
        None,
    )
    return bool(
        version.get("quality_report_id") == _DEMO_GOVERNED_QUALITY_REPORT_ID
        and raw_member
        and raw_member.get("source") == _DEMO_GOVERNED_MARKET_SOURCE
        and raw_member.get("content_hash") == member.get("content_hash")
        and int(raw_member.get("row_count") or 0) == int(member.get("row_count") or 0)
    )


def _demo_governed_physical_rows_match(
    market_store: AShareMarketStore,
    member: Mapping[str, Any],
) -> bool:
    overview = market_store.get_overview()
    raw = dict((overview.get("adjustments") or {}).get("raw") or {})
    if (
        int(raw.get("row_count") or 0) != int(member.get("row_count") or 0)
        or int(raw.get("symbol_count") or 0) != int(member.get("symbol_count") or 0)
        or raw.get("min_date") != member.get("min_date")
        or raw.get("max_date") != member.get("max_date")
    ):
        return False
    expected_per_symbol = int(member.get("row_count") or 0) // len(_DEMO_GOVERNED_SYMBOLS)
    physical_rows: list[dict[str, Any]] = []
    for symbol, _, _ in _DEMO_GOVERNED_SYMBOLS:
        page = market_store.fetch_daily_prices(
            symbol=symbol,
            adjustment="raw",
            start_date=_DEMO_GOVERNED_START_DATE,
            end_date=_DEMO_GOVERNED_END_DATE,
            limit=2000,
        )
        if int(page.get("total") or 0) != expected_per_symbol:
            return False
        page_rows = list(page.get("rows") or [])
        if any(row.get("source") != _DEMO_GOVERNED_MARKET_SOURCE for row in page_rows):
            return False
        for row in reversed(page_rows):
            physical_rows.append(
                {
                    "symbol": symbol,
                    "date": row.get("date"),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                    "amplitude": row.get("amplitude"),
                    "change_pct": row.get("change_pct"),
                    "change_amount": row.get("change_amount"),
                    "turnover_rate": row.get("turnover_rate"),
                }
            )
    physical_member = _demo_governed_market_member(physical_rows)
    return physical_member.get("content_hash") == member.get("content_hash")



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
