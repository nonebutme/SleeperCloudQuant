from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.market import (
    AShareDailyPricesQuery,
    AShareDailyPricesResponse,
    AShareOverviewQuery,
    AShareOverviewResponse,
    AShareSymbolsQuery,
    AShareSymbolsResponse,
    IndexDailyPricesQuery,
    IndexDailyPricesResponse,
    IndexSymbolsQuery,
    IndexSymbolsResponse,
    MarketDataBrowserQuery,
    MarketDataBrowserResponse,
    MarketLocalPriceBarStatusQuery,
    MarketLocalPriceBarStatusResponse,
    MarketLocalPriceBarAssetsQuery,
    MarketLocalPriceBarAssetsResponse,
    MarketLocalPriceBarQualityQuery,
    MarketLocalPriceBarQualityResponse,
    MarketLocalPriceBarRepairRequest,
    MarketLocalPriceBarRepairResponse,
    MarketLocalPriceBarsQuery,
    MarketLocalPriceBarsResponse,
    MarketPanoramaQuery,
    MarketPanoramaResponse,
    MarketPriceHistoryQuery,
    MarketPriceHistoryResponse,
    MarketSyncPriceHistoryRequest,
    MarketSyncResponse,
    MarketSyncStatusResponse,
    MarketSyncTradingCalendarRequest,
    MarketTradingCalendarQuery,
    MarketTradingCalendarResponse,
)
from app.services.market_data_service import MarketDataService



def get_a_share_overview(
    service: MarketDataService,
    query: AShareOverviewQuery,
) -> AShareOverviewResponse:
    return AShareOverviewResponse(overview=service.get_a_share_overview())


def get_a_share_symbols(
    service: MarketDataService,
    query: AShareSymbolsQuery,
) -> AShareSymbolsResponse:
    return AShareSymbolsResponse(catalog=service.list_a_share_symbols(
        query=query.query,
        market=query.market,
        limit=query.limit,
        offset=query.offset,
    ))


def get_a_share_daily_prices(
    service: MarketDataService,
    query: AShareDailyPricesQuery,
) -> AShareDailyPricesResponse:
    return AShareDailyPricesResponse(daily=service.get_a_share_daily_prices(
        symbol=query.symbol,
        adjustment=query.adjustment,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        offset=query.offset,
    ))


def get_index_symbols(
    service: MarketDataService,
    query: IndexSymbolsQuery,
) -> IndexSymbolsResponse:
    catalog = service.list_index_symbols()
    if query.market:
        catalog = {
            **catalog,
            "items": [
                item for item in catalog["items"]
                if str(item.get("market") or "") == query.market
            ],
        }
    return IndexSymbolsResponse(catalog=catalog)


def get_index_daily_prices(
    service: MarketDataService,
    query: IndexDailyPricesQuery,
) -> IndexDailyPricesResponse:
    return IndexDailyPricesResponse(daily=service.get_index_daily_prices(
        index_symbol=query.index_symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        offset=query.offset,
    ))


def get_market_panorama(service: MarketDataService, query: MarketPanoramaQuery) -> MarketPanoramaResponse:
    return MarketPanoramaResponse(
        panorama=service.get_market_panorama(
            trade_date=query.trade_date,
            symbol=query.symbol,
            asset_type=query.asset_type,
        )
    )

def get_market_data_browser(service: MarketDataService, query: MarketDataBrowserQuery) -> MarketDataBrowserResponse:
    return MarketDataBrowserResponse(
        browser=service.get_local_market_data_browser(
            symbol=query.symbol,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
        )
    )


def get_price_history(service: MarketDataService, query: MarketPriceHistoryQuery) -> MarketPriceHistoryResponse:
    rows = service.get_price_history(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
    )
    return MarketPriceHistoryResponse(symbol=query.symbol, rows=rows, source_trace=service.get_source_trace())



def get_local_price_bar_assets(service: MarketDataService, query: MarketLocalPriceBarAssetsQuery) -> MarketLocalPriceBarAssetsResponse:
    return MarketLocalPriceBarAssetsResponse(
        assets=service.get_local_price_bar_assets(symbol=query.symbol, limit=query.limit)
    )

def get_local_price_bars(service: MarketDataService, query: MarketLocalPriceBarsQuery) -> MarketLocalPriceBarsResponse:
    rows = service.get_local_price_bars(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
    )
    status = service.get_local_price_bar_status(symbol=query.symbol)
    return MarketLocalPriceBarsResponse(symbol=query.symbol, rows=rows, storage_status=status)



def get_local_price_bar_status(service: MarketDataService, query: MarketLocalPriceBarStatusQuery) -> MarketLocalPriceBarStatusResponse:
    return MarketLocalPriceBarStatusResponse(status=service.get_local_price_bar_status(symbol=query.symbol))


def inspect_local_price_bar_quality(service: MarketDataService, query: MarketLocalPriceBarQualityQuery) -> MarketLocalPriceBarQualityResponse:
    return MarketLocalPriceBarQualityResponse(
        report=service.inspect_local_price_bar_quality(
            symbol=query.symbol,
            start_date=query.start_date,
            end_date=query.end_date,
        )
    )



def repair_local_price_bar_gaps(service: MarketDataService, payload: MarketLocalPriceBarRepairRequest) -> MarketLocalPriceBarRepairResponse:
    return MarketLocalPriceBarRepairResponse(
        result=service.repair_local_price_bar_gaps(
            symbol=payload.symbol,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
    )


def get_trading_calendar(service: MarketDataService, query: MarketTradingCalendarQuery) -> MarketTradingCalendarResponse:
    days = service.get_trading_calendar(
        start_date=query.start_date,
        end_date=query.end_date,
    )
    return MarketTradingCalendarResponse(days=days)



def sync_price_history(service: MarketDataService, payload: MarketSyncPriceHistoryRequest) -> MarketSyncResponse:
    summary = service.sync_price_history(
        symbol=payload.symbol,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return _to_sync_response(summary)



def sync_trading_calendar(
    service: MarketDataService,
    payload: MarketSyncTradingCalendarRequest,
) -> MarketSyncResponse:
    summary = service.sync_trading_calendar(
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return _to_sync_response(summary)



def get_sync_status(service: MarketDataService, dataset: str) -> MarketSyncStatusResponse:
    return MarketSyncStatusResponse(status=service.get_sync_status(dataset=dataset))



def build_market_routes(service: MarketDataService) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="GET",
            path="/api/market/a-share/overview",
            name="market_a_share_overview",
            handler=lambda query: get_a_share_overview(service, query),
            request_model=AShareOverviewQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/a-share/symbols",
            name="market_a_share_symbols",
            handler=lambda query: get_a_share_symbols(service, query),
            request_model=AShareSymbolsQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/a-share/daily",
            name="market_a_share_daily",
            handler=lambda query: get_a_share_daily_prices(service, query),
            request_model=AShareDailyPricesQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/index-symbols",
            name="market_index_symbols",
            handler=lambda query: get_index_symbols(service, query),
            request_model=IndexSymbolsQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/index-daily",
            name="market_index_daily",
            handler=lambda query: get_index_daily_prices(service, query),
            request_model=IndexDailyPricesQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/panorama",
            name="market_panorama",
            handler=lambda query: get_market_panorama(service, query),
            request_model=MarketPanoramaQuery,
        ),        RouteDefinition(
            method="GET",
            path="/api/market/data-browser",
            name="market_data_browser",
            handler=lambda query: get_market_data_browser(service, query),
            request_model=MarketDataBrowserQuery,
        ),        RouteDefinition(
            method="GET",
            path="/api/market/price-history",
            name="market_price_history",
            handler=lambda query: get_price_history(service, query),
            request_model=MarketPriceHistoryQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/local-price-bars/assets",
            name="market_local_price_bar_assets",
            handler=lambda query: get_local_price_bar_assets(service, query),
            request_model=MarketLocalPriceBarAssetsQuery,
        ),        RouteDefinition(
            method="GET",
            path="/api/market/local-price-bars",
            name="market_local_price_bars",
            handler=lambda query: get_local_price_bars(service, query),
            request_model=MarketLocalPriceBarsQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/local-price-bars/status",
            name="market_local_price_bar_status",
            handler=lambda query: get_local_price_bar_status(service, query),
            request_model=MarketLocalPriceBarStatusQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/local-price-bars/quality",
            name="market_local_price_bar_quality",
            handler=lambda query: inspect_local_price_bar_quality(service, query),
            request_model=MarketLocalPriceBarQualityQuery,
        ),
        RouteDefinition(
            method="POST",
            path="/api/market/local-price-bars/repair-gaps",
            name="market_local_price_bar_repair_gaps",
            handler=lambda payload: repair_local_price_bar_gaps(service, payload),
            request_model=MarketLocalPriceBarRepairRequest,
        ),        RouteDefinition(
            method="GET",
            path="/api/market/trading-calendar",
            name="market_trading_calendar",
            handler=lambda query: get_trading_calendar(service, query),
            request_model=MarketTradingCalendarQuery,
        ),
        RouteDefinition(
            method="POST",
            path="/api/market/sync-price-history",
            name="market_sync_price_history",
            handler=lambda payload: sync_price_history(service, payload),
            request_model=MarketSyncPriceHistoryRequest,
        ),
        RouteDefinition(
            method="POST",
            path="/api/market/sync-trading-calendar",
            name="market_sync_trading_calendar",
            handler=lambda payload: sync_trading_calendar(service, payload),
            request_model=MarketSyncTradingCalendarRequest,
        ),
        RouteDefinition(
            method="GET",
            path="/api/market/sync-status/{dataset}",
            name="market_sync_status",
            handler=lambda dataset: get_sync_status(service, dataset),
            request_model=None,
        ),
    ]



def _to_sync_response(summary: object) -> MarketSyncResponse:
    return MarketSyncResponse(summary=summary)


