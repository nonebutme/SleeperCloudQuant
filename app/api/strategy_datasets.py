"""Read-only strategy Dataset catalog and example routes."""

from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.strategy_datasets import (
    StrategyDatasetListQuery,
    StrategyDatasetListResponse,
    StrategyDatasetObjectResponse,
    StrategyDatasetValidationRequest,
    StrategyDatasetPreviewRequest,
)
from app.services.strategy_dataset_service import StrategyDatasetService


def build_strategy_dataset_routes(service: StrategyDatasetService) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            "GET",
            "/api/strategy-datasets",
            "strategy_datasets",
            lambda query: _list(service, query),
            StrategyDatasetListQuery,
        ),
        RouteDefinition(
            "GET",
            "/api/strategy-datasets/categories",
            "strategy_dataset_categories",
            lambda: StrategyDatasetObjectResponse(service.list_categories()),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/strategy-datasets/validate-requirements",
            "strategy_dataset_validate_requirements",
            lambda request: StrategyDatasetObjectResponse(
                service.validate_requirements(request.source_code, request.dataset_ids)
            ),
            StrategyDatasetValidationRequest,
        ),
        RouteDefinition(
            "GET",
            "/api/strategy-datasets/{dataset_id}",
            "strategy_dataset_detail",
            lambda dataset_id: StrategyDatasetObjectResponse(service.get_product(dataset_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/strategy-datasets/{dataset_id}/preview",
            "strategy_dataset_preview",
            lambda request, dataset_id: StrategyDatasetObjectResponse(
                service.preview(
                    dataset_id,
                    symbol=request.symbol,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    adjustment=request.adjustment,
                    limit=request.limit,
                )
            ),
            StrategyDatasetPreviewRequest,
        ),
        RouteDefinition(
            "GET",
            "/api/strategy-datasets/{dataset_id}/research",
            "strategy_dataset_research",
            lambda dataset_id: StrategyDatasetObjectResponse(service.get_research(dataset_id)),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/strategy-datasets/{dataset_id}/examples",
            "strategy_dataset_examples",
            lambda dataset_id: StrategyDatasetObjectResponse(service.list_examples(dataset_id)),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/strategy-datasets/{dataset_id}/examples/{example_id}",
            "strategy_dataset_example_detail",
            lambda dataset_id, example_id: StrategyDatasetObjectResponse(
                service.get_example(dataset_id, example_id)
            ),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/strategy-datasets/{dataset_id}/examples/{example_id}/instantiate",
            "strategy_dataset_example_instantiate",
            lambda dataset_id, example_id: StrategyDatasetObjectResponse(
                service.instantiate_example(dataset_id, example_id)
            ),
            None,
        ),
    ]


def _list(
    service: StrategyDatasetService,
    query: StrategyDatasetListQuery,
) -> StrategyDatasetListResponse:
    result = service.list_products(
        status=query.status,
        layer_id=query.layer_id,
        search=query.search,
        consumer_scope=query.consumer_scope,
    )
    return StrategyDatasetListResponse(
        items=list(result["items"]),
        summary=dict(result["summary"]),
    )
