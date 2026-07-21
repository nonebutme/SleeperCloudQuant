"""Configuration center routes."""

from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.config import (
    BacktestProfilesResponsePayload,
    ConfigMarketProviderPreflightRequestPayload,
    ConfigMarketProviderPreflightResponsePayload,
    ConfigMarketProviderSyncTaskCreateRequestPayload,
    ConfigMarketProviderSyncTaskListResponsePayload,
    ConfigMarketProviderSyncTaskResponsePayload,
    ConfigRuntimeDraftSaveRequestPayload,
    ConfigRuntimeDraftSaveResponsePayload,
    ConfigStatusResponsePayload,
)
from app.services.config_center_service import ConfigCenterService


def get_config_status(service: ConfigCenterService) -> ConfigStatusResponsePayload:
    return ConfigStatusResponsePayload(status=service.get_status())


def get_backtest_profiles(service: ConfigCenterService) -> BacktestProfilesResponsePayload:
    return BacktestProfilesResponsePayload(profiles=service.get_backtest_profiles())


def save_runtime_draft(service: ConfigCenterService, payload: ConfigRuntimeDraftSaveRequestPayload) -> ConfigRuntimeDraftSaveResponsePayload:
    draft = service.save_runtime_draft(payload.settings)
    return ConfigRuntimeDraftSaveResponsePayload(status="draft_saved", draft=draft)


def preflight_market_provider(service: ConfigCenterService, payload: ConfigMarketProviderPreflightRequestPayload) -> ConfigMarketProviderPreflightResponsePayload:
    result = service.preflight_market_provider(symbol=payload.symbol, start_date=payload.start_date, end_date=payload.end_date)
    return ConfigMarketProviderPreflightResponsePayload(result=result)


def list_market_provider_sync_tasks(service: ConfigCenterService) -> ConfigMarketProviderSyncTaskListResponsePayload:
    return ConfigMarketProviderSyncTaskListResponsePayload(tasks=service.list_market_provider_sync_tasks())


def create_market_provider_sync_task(service: ConfigCenterService, payload: ConfigMarketProviderSyncTaskCreateRequestPayload) -> ConfigMarketProviderSyncTaskResponsePayload:
    task = service.create_market_provider_sync_task(symbols=payload.symbols, start_date=payload.start_date, end_date=payload.end_date, interval_seconds=payload.interval_seconds)
    return ConfigMarketProviderSyncTaskResponsePayload(task=task)


def get_market_provider_sync_task(service: ConfigCenterService, task_id: str) -> ConfigMarketProviderSyncTaskResponsePayload:
    return ConfigMarketProviderSyncTaskResponsePayload(task=service.get_market_provider_sync_task(task_id))


def run_market_provider_sync_task(service: ConfigCenterService, task_id: str) -> ConfigMarketProviderSyncTaskResponsePayload:
    return ConfigMarketProviderSyncTaskResponsePayload(task=service.run_market_provider_sync_task(task_id))


def retry_market_provider_sync_task(service: ConfigCenterService, task_id: str) -> ConfigMarketProviderSyncTaskResponsePayload:
    return ConfigMarketProviderSyncTaskResponsePayload(task=service.retry_market_provider_sync_task(task_id))


def build_config_routes(service: ConfigCenterService) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="GET",
            path="/api/config/status",
            name="config_status",
            handler=lambda: get_config_status(service),
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/config/backtest-profiles",
            name="config_backtest_profiles",
            handler=lambda: get_backtest_profiles(service),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/runtime-draft",
            name="config_runtime_draft_save",
            handler=lambda payload: save_runtime_draft(service, payload),
            request_model=ConfigRuntimeDraftSaveRequestPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/market-provider/preflight",
            name="config_market_provider_preflight",
            handler=lambda payload: preflight_market_provider(service, payload),
            request_model=ConfigMarketProviderPreflightRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/config/market-provider/sync-tasks",
            name="config_market_provider_sync_tasks",
            handler=lambda: list_market_provider_sync_tasks(service),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/market-provider/sync-tasks",
            name="config_market_provider_sync_task_create",
            handler=lambda payload: create_market_provider_sync_task(service, payload),
            request_model=ConfigMarketProviderSyncTaskCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/config/market-provider/sync-tasks/{task_id}",
            name="config_market_provider_sync_task_get",
            handler=lambda task_id: get_market_provider_sync_task(service, task_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/market-provider/sync-tasks/{task_id}/run",
            name="config_market_provider_sync_task_run",
            handler=lambda task_id: run_market_provider_sync_task(service, task_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/market-provider/sync-tasks/{task_id}/retry",
            name="config_market_provider_sync_task_retry",
            handler=lambda task_id: retry_market_provider_sync_task(service, task_id),
            request_model=None,
        ),
    ]
