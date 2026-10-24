"""Configuration center routes."""

from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.config import (
    ConfigAShareSchedulerConfigureRequestPayload,
    ConfigAShareSchedulerResponsePayload,
    ConfigAShareSyncJobCreateRequestPayload,
    ConfigAShareSyncJobListResponsePayload,
    BacktestProfilesResponsePayload,
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


def get_a_share_scheduler_status(service: ConfigCenterService) -> ConfigAShareSchedulerResponsePayload:
    return ConfigAShareSchedulerResponsePayload(result=service.get_a_share_scheduler_status())


def configure_a_share_scheduler(service: ConfigCenterService, payload: ConfigAShareSchedulerConfigureRequestPayload) -> ConfigAShareSchedulerResponsePayload:
    return ConfigAShareSchedulerResponsePayload(result=service.configure_a_share_scheduler(
        enabled=payload.enabled,
        run_time=payload.run_time,
        timezone_name=payload.timezone_name,
        adjustments=payload.adjustments,
    ))


def list_a_share_sync_jobs(service: ConfigCenterService) -> ConfigAShareSyncJobListResponsePayload:
    return ConfigAShareSyncJobListResponsePayload(jobs=service.list_a_share_sync_jobs())


def create_a_share_sync_job(service: ConfigCenterService, payload: ConfigAShareSyncJobCreateRequestPayload) -> ConfigAShareSchedulerResponsePayload:
    return ConfigAShareSchedulerResponsePayload(result=service.create_a_share_sync_job(
        target_trade_date=payload.target_trade_date,
        symbols=payload.symbols,
        all_current=payload.all_current,
        adjustments=payload.adjustments,
        run_now=payload.run_now,
    ))


def get_a_share_sync_job(service: ConfigCenterService, job_id: str) -> ConfigAShareSchedulerResponsePayload:
    return ConfigAShareSchedulerResponsePayload(result=service.get_a_share_sync_job(job_id))


def run_a_share_sync_job(service: ConfigCenterService, job_id: str) -> ConfigAShareSchedulerResponsePayload:
    return ConfigAShareSchedulerResponsePayload(result=service.run_a_share_sync_job(job_id))


def retry_a_share_sync_job(service: ConfigCenterService, job_id: str) -> ConfigAShareSchedulerResponsePayload:
    return ConfigAShareSchedulerResponsePayload(result=service.retry_a_share_sync_job(job_id))


def tick_a_share_scheduler(service: ConfigCenterService) -> ConfigAShareSchedulerResponsePayload:
    return ConfigAShareSchedulerResponsePayload(result=service.tick_a_share_scheduler())


def recover_a_share_scheduler(service: ConfigCenterService) -> ConfigAShareSchedulerResponsePayload:
    return ConfigAShareSchedulerResponsePayload(result=service.recover_a_share_scheduler())


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
            method="GET",
            path="/api/config/a-share-scheduler/status",
            name="a_share_scheduler_status",
            handler=lambda: get_a_share_scheduler_status(service),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/a-share-scheduler/settings",
            name="a_share_scheduler_configure",
            handler=lambda payload: configure_a_share_scheduler(service, payload),
            request_model=ConfigAShareSchedulerConfigureRequestPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/a-share-scheduler/tick",
            name="a_share_scheduler_tick",
            handler=lambda: tick_a_share_scheduler(service),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/a-share-scheduler/recover",
            name="a_share_scheduler_recover",
            handler=lambda: recover_a_share_scheduler(service),
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/config/a-share-sync/jobs",
            name="a_share_sync_jobs",
            handler=lambda: list_a_share_sync_jobs(service),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/a-share-sync/jobs",
            name="a_share_sync_job_create",
            handler=lambda payload: create_a_share_sync_job(service, payload),
            request_model=ConfigAShareSyncJobCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/config/a-share-sync/jobs/{job_id}",
            name="a_share_sync_job_get",
            handler=lambda job_id: get_a_share_sync_job(service, job_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/a-share-sync/jobs/{job_id}/run",
            name="a_share_sync_job_run",
            handler=lambda job_id: run_a_share_sync_job(service, job_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/config/a-share-sync/jobs/{job_id}/retry",
            name="a_share_sync_job_retry",
            handler=lambda job_id: retry_a_share_sync_job(service, job_id),
            request_model=None,
        ),
    ]
