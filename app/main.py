"""Minimal application factory for the formal local-quant service shell."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.api import (
    RouteDefinition,
    build_ai_routes,
    build_backtest_routes,
    build_config_routes,
    build_data_center_routes,
    build_factor_routes,
    build_market_routes,
    build_reporting_routes,
)
from app.api.strategy_datasets import build_strategy_dataset_routes
from app.services.strategy_dataset_service import StrategyDatasetService
from app.services import (
    AIAnalysisService,
    BacktestService,
    BacktestModeReportService,
    BatchResearchService,
    ConfigCenterService,
    DataCenterService,
    FactorResearchService,
    IndependentScreeningService,
    MarketDataService,
    PersistentBacktestService,
    ReportingService,
    SharedPortfolioService,
    SingleBacktestTaskService,
    StrategyService,
)


@dataclass(frozen=True, slots=True)
class AppServiceRegistry:
    """Injected application services for the minimal API shell."""

    market_data_service: MarketDataService
    factor_research_service: FactorResearchService
    backtest_service: BacktestService | PersistentBacktestService
    batch_research_service: BatchResearchService
    reporting_service: ReportingService
    strategy_service: StrategyService
    independent_screening_service: IndependentScreeningService
    shared_portfolio_service: SharedPortfolioService
    single_backtest_task_service: SingleBacktestTaskService | None = None
    backtest_mode_report_service: BacktestModeReportService | None = None
    ai_analysis_service: AIAnalysisService | None = None
    config_center_service: ConfigCenterService | None = None
    data_center_service: DataCenterService | None = None
    strategy_dataset_service: StrategyDatasetService | None = None


@dataclass
class SimpleApiApp:
    """Fallback API app used when FastAPI is not installed."""

    title: str
    routes: list[RouteDefinition] = field(default_factory=list)


def create_app(services: AppServiceRegistry) -> SimpleApiApp:
    """Create the minimal local API shell from injected services."""

    routes = [
        *build_market_routes(services.market_data_service),
        *build_factor_routes(services.factor_research_service),
        *build_backtest_routes(
            services.backtest_service,
            services.batch_research_service,
            services.strategy_service,
            services.independent_screening_service,
            services.shared_portfolio_service,
            services.single_backtest_task_service,
        ),
        *build_reporting_routes(services.reporting_service, services.backtest_mode_report_service),
    ]
    if services.ai_analysis_service is not None:
        routes.extend(build_ai_routes(services.ai_analysis_service))
    if services.data_center_service is not None:
        routes.extend(build_data_center_routes(services.data_center_service))
    if services.config_center_service is not None:
        routes.extend(build_config_routes(services.config_center_service))
    if services.strategy_dataset_service is not None:
        routes.extend(build_strategy_dataset_routes(services.strategy_dataset_service))
    return SimpleApiApp(title="SleeperCloudQuant Formal API", routes=routes)
