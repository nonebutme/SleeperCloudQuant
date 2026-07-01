"""Minimal application factory for the formal local-quant service shell."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.api import RouteDefinition, build_backtest_routes, build_market_routes, build_reporting_routes
from app.services import BacktestService, MarketDataService, ReportingService


@dataclass(frozen=True, slots=True)
class AppServiceRegistry:
    """Injected application services for the minimal API shell."""

    market_data_service: MarketDataService
    backtest_service: BacktestService
    reporting_service: ReportingService


@dataclass
class SimpleApiApp:
    """Fallback API app used when FastAPI is not installed."""

    title: str
    routes: list[RouteDefinition] = field(default_factory=list)



def create_app(services: AppServiceRegistry) -> SimpleApiApp:
    """Create the minimal local API shell from injected services."""

    routes = [
        *build_market_routes(services.market_data_service),
        *build_backtest_routes(services.backtest_service),
        *build_reporting_routes(services.reporting_service),
    ]
    return SimpleApiApp(title="SleeperCloudQuant Formal API", routes=routes)
