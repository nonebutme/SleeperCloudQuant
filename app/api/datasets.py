"""Dataset Product routes prepared for later main-router registration."""

from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.datasets import (
    DatasetProductListQuery,
    DatasetProductListResponse,
    DatasetProductResponse,
)
from app.services.dataset_product_service import DatasetProductService


def list_dataset_products(
    service: DatasetProductService,
    query: DatasetProductListQuery,
) -> DatasetProductListResponse:
    result = service.list_products(
        status=query.status,
        layer_id=query.layer_id,
        search=query.search,
    )
    return DatasetProductListResponse(
        items=list(result["items"]),
        summary=dict(result["summary"]),
    )


def get_dataset_product(
    service: DatasetProductService,
    dataset_id: str,
) -> DatasetProductResponse:
    return DatasetProductResponse(product=service.get_product(dataset_id))


def build_dataset_product_routes(service: DatasetProductService) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="GET",
            path="/api/datasets",
            name="dataset_products",
            handler=lambda query: list_dataset_products(service, query),
            request_model=DatasetProductListQuery,
        ),
        RouteDefinition(
            method="GET",
            path="/api/datasets/{dataset_id}",
            name="dataset_product_detail",
            handler=lambda dataset_id: get_dataset_product(service, dataset_id),
            request_model=None,
        ),
    ]

