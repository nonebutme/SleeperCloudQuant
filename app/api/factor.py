from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.factor import (
    FactorCrossSectionSummaryItem,
    FactorCrossSectionSummaryQuery,
    FactorCrossSectionSummaryResponse,
    FactorDefinitionsResponse,
    FactorPoolMembersQuery,
    FactorPoolMembersResponse,
    FactorSummaryQuery,
    FactorSummaryResponse,
    FactorTopNQuery,
    FactorTopNResponse,
    FactorValuesQuery,
    FactorValuesResponse,
)
from app.services.factor_research_service import FactorResearchService



def _parse_factor_ids(raw_value: str | None) -> list[str] | None:
    if not raw_value:
        return None
    values = [item.strip() for item in str(raw_value).split(",") if item.strip()]
    return values or None



def _parse_top_n_limit(raw_value: str | None) -> int:
    if not raw_value:
        return 10
    try:
        return int(raw_value)
    except ValueError as exc:
        from app.runtime.http_adapter import DispatchError

        raise DispatchError(400, "limit must be an integer") from exc



def _parse_descending(raw_value: str | None) -> bool:
    return str(raw_value or "true").strip().lower() not in {"false", "0", "no"}



def list_factor_definitions(service: FactorResearchService) -> FactorDefinitionsResponse:
    return FactorDefinitionsResponse(definitions=service.list_factor_definitions())



def get_pool_members(service: FactorResearchService, query: FactorPoolMembersQuery) -> FactorPoolMembersResponse:
    symbols = service.get_pool_members(index_code=query.index_code, date=query.date)
    return FactorPoolMembersResponse(index_code=query.index_code, date=query.date, symbols=symbols)



def get_factor_summary(service: FactorResearchService, query: FactorSummaryQuery) -> FactorSummaryResponse:
    rows = service.get_factor_summary(symbol=query.symbol, trade_date=query.trade_date, start_date=query.start_date, end_date=query.end_date, factor_ids=_parse_factor_ids(query.factor_ids))
    return FactorSummaryResponse(symbol=query.symbol, trade_date=query.trade_date, rows=rows)



def get_factor_cross_section_summary(service: FactorResearchService, query: FactorCrossSectionSummaryQuery) -> FactorCrossSectionSummaryResponse:
    summaries = service.get_pool_factor_summary(index_code=query.index_code, date=query.date, trade_date=query.trade_date, start_date=query.start_date, end_date=query.end_date, factor_ids=_parse_factor_ids(query.factor_ids))
    return FactorCrossSectionSummaryResponse(
        index_code=query.index_code,
        date=query.date,
        trade_date=query.trade_date,
        summaries=[_to_cross_section_item(symbol, rows) for symbol, rows in summaries.items()],
    )



def get_factor_values(service: FactorResearchService, query: FactorValuesQuery) -> FactorValuesResponse:
    rows = service.get_factor_values(factor_id=query.factor_id, symbol=query.symbol, start_date=query.start_date, end_date=query.end_date)
    return FactorValuesResponse(factor_id=query.factor_id, symbol=query.symbol, rows=rows)



def get_factor_top_n(service: FactorResearchService, query: FactorTopNQuery) -> FactorTopNResponse:
    ranking = service.get_factor_top_n(
        factor_id=query.factor_id,
        trade_date=query.trade_date,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=_parse_top_n_limit(query.limit),
        descending=_parse_descending(query.descending),
    )
    return FactorTopNResponse(ranking=ranking)



def build_factor_routes(service: FactorResearchService) -> list[RouteDefinition]:
    return [
        RouteDefinition(method="GET", path="/api/factors/definitions", name="factor_definitions", handler=lambda: list_factor_definitions(service), request_model=None),
        RouteDefinition(method="GET", path="/api/factors/pool-members", name="factor_pool_members", handler=lambda query: get_pool_members(service, query), request_model=FactorPoolMembersQuery),
        RouteDefinition(method="GET", path="/api/factors/summary", name="factor_summary", handler=lambda query: get_factor_summary(service, query), request_model=FactorSummaryQuery),
        RouteDefinition(method="GET", path="/api/factors/cross-section-summary", name="factor_cross_section_summary", handler=lambda query: get_factor_cross_section_summary(service, query), request_model=FactorCrossSectionSummaryQuery),
        RouteDefinition(method="GET", path="/api/factors/values", name="factor_values", handler=lambda query: get_factor_values(service, query), request_model=FactorValuesQuery),
        RouteDefinition(method="GET", path="/api/factors/top-n", name="factor_top_n", handler=lambda query: get_factor_top_n(service, query), request_model=FactorTopNQuery),
    ]



def _to_cross_section_item(symbol: str, rows: object) -> FactorCrossSectionSummaryItem:
    return FactorCrossSectionSummaryItem(symbol=symbol, rows=rows)
