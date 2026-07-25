from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from app.api.contracts import RouteDefinition
from app.schemas.reporting import (
    BacktestModeReportResponsePayload,
    BatchSummaryResponse,
    ExperimentReviewPackageCreateRequestPayload,
    ExperimentReviewPackageResponsePayload,
    ExperimentReportComparisonResponsePayload,
    ParameterScanComparisonResponse,
    ReportSnapshotDetailResponse,
    ReportSnapshotListResponse,
    ReportSnapshotSaveRequestPayload,
    ReportSnapshotSaveResponse,
    ReportPackageCreateRequestPayload,
    ReportPackageDirectoryQueryPayload,
    ReportPackageDirectoryResponsePayload,
    ReportPackageExportManifestQueryPayload,
    ReportPackageExportManifestResponsePayload,
    ReportPackageExportQueryPayload,
    ReportPackageLifecycleUpdateRequestPayload,
    ReportPackageLifecycleUpdateResponsePayload,
    ReportPackageExportResponsePayload,
    ReportPackageListResponsePayload,
    ReportPackageResponsePayload,
    ReportingAIWorkflowReplayQuery,
    ReportingAIWorkflowReplayResponse,
    RunDetailResponse,
    StrategyEvaluationResponse,
)
from app.services.reporting_service import ReportingService
from app.services.backtest_mode_report_service import BacktestModeReportService


_EXPERIMENT_INDEX_PATH = Path("var/runtime/backtest_experiment_index.json")


def get_run_detail(service: ReportingService, run_id: str) -> RunDetailResponse | None:
    detail = service.get_run_detail(run_id)
    return _wrap_run_detail(detail)


def get_batch_summary(service: ReportingService, experiment_id: str) -> BatchSummaryResponse | None:
    summary = service.get_batch_summary(experiment_id)
    return _wrap_batch_summary(summary)


def get_strategy_evaluation(service: ReportingService, run_id: str) -> StrategyEvaluationResponse | None:
    report = service.get_strategy_evaluation(run_id)
    if report is None:
        return None
    return StrategyEvaluationResponse(report=report)


def save_strategy_evaluation_snapshot(
    service: ReportingService,
    payload: ReportSnapshotSaveRequestPayload,
    run_id: str,
) -> ReportSnapshotSaveResponse | None:
    snapshot = service.save_strategy_evaluation_snapshot(
        run_id,
        report_type=payload.report_type,
        report_version=payload.report_version,
    )
    if snapshot is None:
        return None
    return ReportSnapshotSaveResponse(snapshot=snapshot)


def save_parameter_scan_comparison_snapshot(
    service: ReportingService,
    payload: ReportSnapshotSaveRequestPayload,
    run_id_prefix: str,
) -> ReportSnapshotSaveResponse | None:
    snapshot = service.save_parameter_scan_comparison_snapshot(
        unquote(run_id_prefix),
        report_type=payload.report_type or "parameter_scan_comparison",
        report_version=payload.report_version or "parameter-scan-v1",
    )
    if snapshot is None:
        return None
    return ReportSnapshotSaveResponse(snapshot=snapshot)


def list_report_snapshots(service: ReportingService, run_id: str) -> ReportSnapshotListResponse:
    snapshots = service.list_report_snapshots(unquote(run_id), report_type=None)
    return ReportSnapshotListResponse(snapshots=snapshots)


def get_report_snapshot(service: ReportingService, snapshot_id: str) -> ReportSnapshotDetailResponse | None:
    snapshot = service.get_report_snapshot(unquote(snapshot_id))
    if snapshot is None:
        return None
    return ReportSnapshotDetailResponse(snapshot=snapshot)


def create_report_package(
    service: ReportingService,
    payload: ReportPackageCreateRequestPayload,
    run_id: str,
) -> ReportPackageResponsePayload | None:
    package = service.create_report_package(
        unquote(run_id),
        symbol=payload.symbol,
        workflow_id=payload.workflow_id,
        title=payload.title,
    )
    if package is None:
        return None
    return ReportPackageResponsePayload(package=package)


def list_report_packages(service: ReportingService, run_id: str) -> ReportPackageListResponsePayload:
    packages = service.list_report_packages(unquote(run_id))
    return ReportPackageListResponsePayload(packages=packages)



def list_report_package_directory(
    service: ReportingService,
    payload: ReportPackageDirectoryQueryPayload,
) -> ReportPackageDirectoryResponsePayload:
    directory = service.list_report_package_directory(
        run_id=payload.run_id,
        package_type=payload.package_type,
        lifecycle_status=payload.lifecycle_status,
        limit=payload.limit,
    )
    return ReportPackageDirectoryResponsePayload(directory=directory)


def build_report_package_export_manifest(
    service: ReportingService,
    payload: ReportPackageExportManifestQueryPayload,
) -> ReportPackageExportManifestResponsePayload:
    manifest = service.build_report_package_export_manifest(
        run_id=payload.run_id,
        package_type=payload.package_type,
        lifecycle_status=payload.lifecycle_status,
        formats=payload.formats,
        limit=payload.limit,
    )
    return ReportPackageExportManifestResponsePayload(manifest=manifest)

def export_report_package(
    service: ReportingService,
    payload: ReportPackageExportQueryPayload,
    package_id: str,
) -> ReportPackageExportResponsePayload | None:
    exported = service.export_report_package(unquote(package_id), export_format=payload.format)
    if exported is None:
        return None
    return ReportPackageExportResponsePayload(export=exported)


def update_report_package_lifecycle(
    service: ReportingService,
    payload: ReportPackageLifecycleUpdateRequestPayload,
    package_id: str,
) -> ReportPackageLifecycleUpdateResponsePayload | None:
    package = service.update_report_package_lifecycle(
        unquote(package_id),
        status=payload.status,
        retention_policy=payload.retention_policy,
        protected=payload.protected,
        reason=payload.reason,
        updated_by=payload.updated_by,
    )
    if package is None:
        return None
    return ReportPackageLifecycleUpdateResponsePayload(package=package)
def delete_report_package(service: ReportingService, package_id: str) -> ReportPackageResponsePayload | None:
    package = service.delete_report_package(unquote(package_id))
    if package is None:
        return None
    return ReportPackageResponsePayload(package=package)


def delete_ai_workflow(service: ReportingService, workflow_id: str) -> dict[str, Any] | None:
    workflow = service.delete_ai_workflow(unquote(workflow_id))
    if workflow is None:
        return None
    return {"workflow": workflow}

def get_report_package(service: ReportingService, package_id: str) -> ReportPackageResponsePayload | None:
    package = service.get_report_package(unquote(package_id))
    if package is None:
        return None
    return ReportPackageResponsePayload(package=package)


def create_experiment_comparison_package(
    service: ReportingService,
    payload: ReportPackageCreateRequestPayload,
    run_id_prefix: str,
) -> ReportPackageResponsePayload | None:
    package = service.create_experiment_comparison_package(
        unquote(run_id_prefix),
        title=payload.title,
    )
    if package is None:
        return None
    return ReportPackageResponsePayload(package=package)
def create_experiment_review_package(
    service: ReportingService,
    payload: ExperimentReviewPackageCreateRequestPayload,
    experiment_id: str,
) -> ExperimentReviewPackageResponsePayload:
    experiment = _find_experiment_index(unquote(experiment_id))
    if experiment is None:
        return ExperimentReviewPackageResponsePayload(review={"experiment_id": unquote(experiment_id), "status": "not_found"})
    primary_run_id = str(experiment.get("primary_run_id") or "")
    run_id_prefix = str(experiment.get("run_id_prefix") or experiment.get("experiment_id") or unquote(experiment_id))
    if not primary_run_id:
        primary_run_id = f"{run_id_prefix}-001"
    detail = service.get_run_detail(primary_run_id)
    evaluation = service.get_strategy_evaluation(primary_run_id)
    package = None
    if payload.create_package:
        package = service.create_report_package(
            primary_run_id,
            symbol=payload.symbol,
            workflow_id=payload.workflow_id,
            title=payload.title or f"{experiment.get('name') or experiment_id} 实验复盘报告包",
        )
    packages = service.list_report_packages(primary_run_id)
    package_id = str((package or {}).get("package_id") or "")
    export_links = {}
    if package_id:
        export_links = {
            "html": f"/api/reporting/report-packages/{package_id}/export?format=html",
            "json": f"/api/reporting/report-packages/{package_id}/export?format=json",
            "pdf": f"/api/reporting/report-packages/{package_id}/export?format=pdf",
            "word": f"/api/reporting/report-packages/{package_id}/export?format=word",
        }
    review = {
        "experiment_id": experiment.get("experiment_id") or unquote(experiment_id),
        "status": "review_ready" if detail is not None and evaluation is not None else "needs_attention",
        "experiment": experiment,
        "run_id_prefix": run_id_prefix,
        "primary_run_id": primary_run_id,
        "run_detail": detail,
        "strategy_evaluation": evaluation,
        "report_package": package or {},
        "report_packages": packages,
        "export_links": export_links,
        "review_links": {
            "experiment_index": f"/api/backtest/experiments/index/{experiment.get('experiment_id') or experiment_id}",
            "experiment_panel": f"/api/backtest/experiments/{run_id_prefix}/panel",
            "portfolio_panel": f"/api/backtest/results/{run_id_prefix}/portfolio-panel",
            "run_detail": f"/api/reporting/run-detail/{primary_run_id}",
            "strategy_evaluation": f"/api/reporting/strategy-evaluation/{primary_run_id}",
            "report_packages": f"/api/reporting/run-detail/{primary_run_id}/report-packages",
        },
    }
    return ExperimentReviewPackageResponsePayload(review=review)


def get_experiment_report_comparison(
    service: ReportingService,
    run_id_prefix: str,
) -> ExperimentReportComparisonResponsePayload:
    comparison = service.get_experiment_report_comparison(unquote(run_id_prefix))
    return ExperimentReportComparisonResponsePayload(comparison=comparison)
def get_ai_workflow_replay(
    service: ReportingService,
    payload: ReportingAIWorkflowReplayQuery,
    run_id: str,
) -> ReportingAIWorkflowReplayResponse | None:
    replay = service.get_ai_workflow_replay(unquote(run_id), symbol=payload.symbol)
    if replay.get("reason") == "run_not_found":
        return None
    return ReportingAIWorkflowReplayResponse(replay=replay)

def get_parameter_scan_comparison(service: ReportingService, run_id_prefix: str) -> ParameterScanComparisonResponse | None:
    report = service.get_parameter_scan_comparison(unquote(run_id_prefix))
    if report is None:
        return None
    return ParameterScanComparisonResponse(report=report)


def get_shared_portfolio_mode_report(
    service: BacktestModeReportService | None,
    task_id: str,
) -> BacktestModeReportResponsePayload:
    report = service.get_shared_portfolio_report(unquote(task_id)) if service is not None else {"status": "unavailable"}
    return BacktestModeReportResponsePayload(report=report)


def get_independent_screening_mode_report(
    service: BacktestModeReportService | None,
    task_id: str,
) -> BacktestModeReportResponsePayload:
    report = service.get_independent_screening_report(unquote(task_id)) if service is not None else {"status": "unavailable"}
    return BacktestModeReportResponsePayload(report=report)

def get_independent_screening_run_report(
    service: BacktestModeReportService | None,
    task_id: str,
    run_id: str,
) -> BacktestModeReportResponsePayload:
    report = service.get_independent_run_report(unquote(task_id), unquote(run_id)) if service is not None else {"status": "unavailable"}
    return BacktestModeReportResponsePayload(report=report)


def build_reporting_routes(
    service: ReportingService,
    mode_report_service: BacktestModeReportService | None = None,
) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="GET",
            path="/api/reporting/backtest-modes/shared-portfolio/{task_id}",
            name="reporting_shared_portfolio_mode_report",
            handler=lambda task_id: get_shared_portfolio_mode_report(mode_report_service, task_id),
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/backtest-modes/independent-screening/{task_id}",
            name="reporting_independent_screening_mode_report",
            handler=lambda task_id: get_independent_screening_mode_report(mode_report_service, task_id),
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/backtest-modes/independent-screening/{task_id}/runs/{run_id}",
            name="reporting_independent_screening_single_run_report",
            handler=lambda task_id, run_id: get_independent_screening_run_report(mode_report_service, task_id, run_id),
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/run-detail/{run_id}",
            name="reporting_run_detail",
            handler=lambda run_id: get_run_detail(service, run_id),
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/batch-summary/{experiment_id}",
            name="reporting_batch_summary",
            handler=lambda experiment_id: get_batch_summary(service, experiment_id),
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/strategy-evaluation/{run_id}",
            name="reporting_strategy_evaluation",
            handler=lambda run_id: get_strategy_evaluation(service, run_id),
        ),
        RouteDefinition(
            method="POST",
            path="/api/reporting/strategy-evaluation/{run_id}/snapshots",
            name="reporting_strategy_evaluation_snapshot_save",
            handler=lambda payload, run_id: save_strategy_evaluation_snapshot(service, payload, run_id),
            request_model=ReportSnapshotSaveRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/run-detail/{run_id}/snapshots",
            name="reporting_snapshot_list",
            handler=lambda run_id: list_report_snapshots(service, run_id),
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/run-detail/{run_id}/ai-workflow",
            name="reporting_ai_workflow_replay",
            handler=lambda payload, run_id: get_ai_workflow_replay(service, payload, run_id),
            request_model=ReportingAIWorkflowReplayQuery,
        ),
        RouteDefinition(
            method="POST",
            path="/api/reporting/run-detail/{run_id}/report-package",
            name="reporting_report_package_create",
            handler=lambda payload, run_id: create_report_package(service, payload, run_id),
            request_model=ReportPackageCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/run-detail/{run_id}/report-packages",
            name="reporting_report_package_list",
            handler=lambda run_id: list_report_packages(service, run_id),
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/report-packages",
            name="reporting_report_package_directory",
            handler=lambda payload: list_report_package_directory(service, payload),
            request_model=ReportPackageDirectoryQueryPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/report-packages/export-manifest",
            name="reporting_report_package_export_manifest",
            handler=lambda payload: build_report_package_export_manifest(service, payload),
            request_model=ReportPackageExportManifestQueryPayload,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/reporting/ai-workflows/{workflow_id}",
            name="reporting_ai_workflow_delete",
            handler=lambda workflow_id: delete_ai_workflow(service, workflow_id),
            request_model=None,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/reporting/report-packages/{package_id}",
            name="reporting_report_package_delete",
            handler=lambda package_id: delete_report_package(service, package_id),
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/report-packages/{package_id}",
            name="reporting_report_package_detail",
            handler=lambda package_id: get_report_package(service, package_id),
        ),
        RouteDefinition(
            method="POST",
            path="/api/reporting/report-packages/{package_id}/lifecycle",
            name="reporting_report_package_lifecycle_update",
            handler=lambda payload, package_id: update_report_package_lifecycle(service, payload, package_id),
            request_model=ReportPackageLifecycleUpdateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/report-packages/{package_id}/export",
            name="reporting_report_package_export",
            handler=lambda payload, package_id: export_report_package(service, payload, package_id),
            request_model=ReportPackageExportQueryPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/reporting/experiments/{run_id_prefix}/comparison-package",
            name="reporting_experiment_comparison_package_create",
            handler=lambda payload, run_id_prefix: create_experiment_comparison_package(service, payload, run_id_prefix),
            request_model=ReportPackageCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/experiments/{run_id_prefix}/comparison",
            name="reporting_experiment_report_comparison",
            handler=lambda run_id_prefix: get_experiment_report_comparison(service, run_id_prefix),
        ),
        RouteDefinition(
            method="POST",
            path="/api/reporting/experiments/{experiment_id}/review-package",
            name="reporting_experiment_review_package_create",
            handler=lambda payload, experiment_id: create_experiment_review_package(service, payload, experiment_id),
            request_model=ExperimentReviewPackageCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/parameter-scan/{run_id_prefix}/comparison",
            name="reporting_parameter_scan_comparison",
            handler=lambda run_id_prefix: get_parameter_scan_comparison(service, run_id_prefix),
        ),
        RouteDefinition(
            method="POST",
            path="/api/reporting/parameter-scan/{run_id_prefix}/comparison/snapshots",
            name="reporting_parameter_scan_comparison_snapshot_save",
            handler=lambda payload, run_id_prefix: save_parameter_scan_comparison_snapshot(service, payload, run_id_prefix),
            request_model=ReportSnapshotSaveRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/reporting/snapshots/{snapshot_id}",
            name="reporting_snapshot_detail",
            handler=lambda snapshot_id: get_report_snapshot(service, snapshot_id),
        ),
    ]


def _wrap_run_detail(detail: object) -> RunDetailResponse | None:
    if detail is None:
        return None
    return RunDetailResponse(detail=detail)


def _wrap_batch_summary(summary: object) -> BatchSummaryResponse | None:
    if summary is None:
        return None
    return BatchSummaryResponse(summary=summary)
def _load_experiment_index() -> list[dict[str, Any]]:
    if not _EXPERIMENT_INDEX_PATH.exists():
        return []
    try:
        raw = json.loads(_EXPERIMENT_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    experiments = raw.get("experiments") if isinstance(raw, dict) else raw
    if not isinstance(experiments, list):
        return []
    return [dict(item) for item in experiments if isinstance(item, dict)]


def _find_experiment_index(experiment_id: str) -> dict[str, Any] | None:
    for experiment in _load_experiment_index():
        if str(experiment.get("experiment_id") or "") == experiment_id:
            return experiment
    return None

















