from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.market import (
    MarketPriceHistoryQuery,
    MarketPriceHistoryResponse,
    MarketTradingCalendarQuery,
    MarketTradingCalendarResponse,
)
from app.services.market_data_service import MarketDataService



def get_price_history(service: MarketDataService, query: MarketPriceHistoryQuery) -> MarketPriceHistoryResponse:
    rows = service.get_price_history(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
    )
    return MarketPriceHistoryResponse(symbol=query.symbol, rows=rows)



def get_trading_calendar(service: MarketDataService, query: MarketTradingCalendarQuery) -> MarketTradingCalendarResponse:
    days = service.get_trading_calendar(
        start_date=query.start_date,
        end_date=query.end_date,
    )
    return MarketTradingCalendarResponse(days=days)



def build_market_routes(service: MarketDataService) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="GET",
            path="/api/market/price-history",
            name="market_price_history",
            handler=lambda query: get_price_history(service, query),
            request_model=MarketPriceHistoryQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/trading-calendar",
            name="market_trading_calendar",
            handler=lambda query: get_trading_calendar(service, query),
            request_model=MarketTradingCalendarQuery,
        ),
    ]
