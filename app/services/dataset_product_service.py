"""Read-only Dataset Product view over the existing data-center catalog."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any, Protocol

from domain.dataset.product_models import DatasetProduct


class DatasetCatalogReader(Protocol):
    def list_datasets(self) -> Sequence[Mapping[str, Any]]: ...


class DatasetProductService:
    """Expose research-facing products without owning a second catalog."""

    def __init__(self, catalog_reader: DatasetCatalogReader) -> None:
        self._catalog_reader = catalog_reader

    def list_products(
        self,
        *,
        status: str = "",
        layer_id: str = "",
        search: str = "",
    ) -> dict[str, Any]:
        normalized_status = status.strip()
        normalized_layer = layer_id.strip().upper()
        normalized_search = search.strip().lower()
        items: list[dict[str, Any]] = []
        for record in self._catalog_reader.list_datasets():
            product = self._to_product(record)
            if normalized_status and product.status != normalized_status:
                continue
            if normalized_layer and product.layer_id.upper() != normalized_layer:
                continue
            haystack = " ".join((product.dataset_id, product.name, product.description)).lower()
            if normalized_search and normalized_search not in haystack:
                continue
            items.append(self._to_view(product, record))
        return {
            "items": items,
            "summary": {
                "total": len(items),
                "connected": sum(item["status"] == "connected" for item in items),
                "unavailable": sum(item["status"] == "unavailable" for item in items),
                "disabled": sum(item["status"] == "disabled" for item in items),
                "catalog_authority": "data_center",
                "write_capability": False,
            },
        }

    def get_product(self, dataset_id: str) -> dict[str, Any]:
        normalized = dataset_id.strip()
        for record in self._catalog_reader.list_datasets():
            if str(record.get("dataset_id") or "") == normalized:
                return self._to_view(self._to_product(record), record)
        raise KeyError(f"unknown dataset_id: {dataset_id}")

    @staticmethod
    def _to_product(record: Mapping[str, Any]) -> DatasetProduct:
        return DatasetProduct(
            dataset_id=str(record.get("dataset_id") or ""),
            name=str(record.get("display_name") or record.get("dataset_id") or ""),
            layer_id=str(record.get("layer_id") or ""),
            description=str(record.get("description") or ""),
            producer_type=str(record.get("producer_type") or "external_source"),
            producer_id=str(record.get("producer_id") or ""),
            status=str(record.get("availability_status") or "unavailable"),
            schema_version=str(record.get("schema_version") or "v1"),
        )

    @staticmethod
    def _to_view(product: DatasetProduct, record: Mapping[str, Any]) -> dict[str, Any]:
        view = asdict(product)
        view.update(
            {
                "sync_enabled": bool(record.get("sync_enabled", False)),
                "config_fields": list(record.get("config_fields") or []),
                "route_required": bool(record.get("route_required", True)),
                "schema_status": "available" if product.fields else "metadata_pending",
                "catalog_authority": "data_center",
            }
        )
        return view

