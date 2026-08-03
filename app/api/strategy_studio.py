"""Strategy Studio manifest routes."""

from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.strategy_studio import (
    StrategyManifestListResponse,
    StrategyManifestResponse,
    StrategyManifestSaveRequest,
)
from app.services.strategy_manifest_service import StrategyManifestService
from domain.dataset.product_models import DatasetRequirement
from domain.strategy import StrategyManifest


def save_strategy_manifest(
    service: StrategyManifestService,
    payload: StrategyManifestSaveRequest,
) -> StrategyManifestResponse:
    manifest = StrategyManifest(
        strategy_id=payload.strategy_id,
        strategy_version=payload.strategy_version,
        name=payload.name,
        source_sha256=payload.source_sha256,
        dataset_requirements=tuple(
            DatasetRequirement(**dict(item)) for item in payload.dataset_requirements
        ),
        factor_ids=tuple(payload.factor_ids),
        assets=dict(payload.assets),
        signals=dict(payload.signals),
        portfolio=dict(payload.portfolio),
        risk=dict(payload.risk),
        execution=dict(payload.execution),
        code=dict(payload.code),
        validation=dict(payload.validation),
    )
    return StrategyManifestResponse(manifest=service.save(manifest))


def list_strategy_manifests(service: StrategyManifestService) -> StrategyManifestListResponse:
    return StrategyManifestListResponse(manifests=service.list())


def get_strategy_manifest(
    service: StrategyManifestService,
    strategy_id: str,
    strategy_version: str,
) -> StrategyManifestResponse:
    return StrategyManifestResponse(manifest=service.get(strategy_id, strategy_version))


def build_strategy_studio_routes(service: StrategyManifestService) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="GET",
            path="/api/strategy-studio/manifests",
            name="strategy_studio_manifests",
            handler=lambda: list_strategy_manifests(service),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/strategy-studio/manifests",
            name="strategy_studio_manifest_save",
            handler=lambda payload: save_strategy_manifest(service, payload),
            request_model=StrategyManifestSaveRequest,
        ),
        RouteDefinition(
            method="GET",
            path="/api/strategy-studio/manifests/{strategy_id}/{strategy_version}",
            name="strategy_studio_manifest_detail",
            handler=lambda strategy_id, strategy_version: get_strategy_manifest(
                service, strategy_id, strategy_version
            ),
            request_model=None,
        ),
    ]

