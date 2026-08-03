"""P1 read-only Dataset Product service and route smoke checks."""

from app.api.datasets import build_dataset_product_routes, get_dataset_product, list_dataset_products
from app.schemas.datasets import DatasetProductListQuery
from app.services.dataset_product_service import DatasetProductService


class _Catalog:
    def list_datasets(self):
        return [
            {
                "dataset_id": "a_share_daily",
                "layer_id": "L1",
                "display_name": "A-share daily",
                "description": "raw/qfq/hfq daily bars",
                "availability_status": "connected",
                "sync_enabled": True,
                "config_fields": ["target_trade_date", "adjustments"],
                "schema_version": "v1",
                "producer_type": "external_source",
                "producer_id": "akshare",
                "route_required": True,
            },
            {
                "dataset_id": "financial_statements",
                "layer_id": "L3",
                "display_name": "Financial statements",
                "description": "disabled candidate",
                "availability_status": "disabled",
            },
        ]


def main() -> None:
    service = DatasetProductService(_Catalog())
    listing = list_dataset_products(service, DatasetProductListQuery(status="connected"))
    assert listing.summary["catalog_authority"] == "data_center"
    assert listing.summary["write_capability"] is False
    assert [item["dataset_id"] for item in listing.items] == ["a_share_daily"]
    detail = get_dataset_product(service, "a_share_daily")
    assert detail.product["sync_enabled"] is True
    assert detail.product["schema_status"] == "metadata_pending"
    routes = build_dataset_product_routes(service)
    assert [route.path for route in routes] == ["/api/datasets", "/api/datasets/{dataset_id}"]
    print("[dataset-product-service] passed")


if __name__ == "__main__":
    main()

