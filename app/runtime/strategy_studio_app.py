"""Canonical parallel composition root for the Strategy Studio candidate."""

from __future__ import annotations

from pathlib import Path

from app.api.datasets import build_dataset_product_routes
from app.api.strategy_studio import build_strategy_studio_routes
from app.runtime.demo_registry import build_demo_app
from app.services.dataset_product_service import DatasetProductService
from app.services.sqlite_strategy_manifest_service import SqliteStrategyManifestService
from data_platform.storage.data_center_store import DataCenterStore


def build_strategy_studio_app():
    app = build_demo_app()
    data_center_store = DataCenterStore(Path("var/market/a_share_market.sqlite3"))
    data_center_store.ensure_schema()
    dataset_service = DatasetProductService(data_center_store)
    manifest_service = SqliteStrategyManifestService(
        Path("var/runtime/strategy_library.sqlite3"),
        dataset_product_service=dataset_service,
    )
    app.routes.extend(build_dataset_product_routes(dataset_service))
    app.routes.extend(build_strategy_studio_routes(manifest_service))
    return app

