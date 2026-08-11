"""Stage-86/Stage-B data-center routes."""

from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.data_center import (
    DataCenterAssetQuery,
    DataCenterDispositionRequest,
    DataCenterListResponse,
    DataCenterObjectResponse,
    DataCenterPublishRequest,
    DataCenterQualityBulkRequest,
    DataCenterQualityIssueQuery,
    DataCenterQualityScanRequest,
    DataCenterQualityRefetchRequest,
    DataCenterRetryRequest,
    DataCenterRouteTestRequest,
    DataCenterRoutesUpdateRequest,
    DataCenterSourceUpdateRequest,
    DataCenterSyncRequest,
)
from app.services.data_center_service import DataCenterService


def build_data_center_routes(service: DataCenterService) -> list[RouteDefinition]:
    return [
        RouteDefinition("GET", "/api/data-center/overview", "data_center_overview",
                        lambda: DataCenterObjectResponse(service.get_overview()), None),
        RouteDefinition("GET", "/api/data-center/sources", "data_center_sources",
                        lambda: DataCenterListResponse(service.list_sources()), None),
        RouteDefinition("GET", "/api/data-center/sources/{source_id}", "data_center_source_detail",
                        lambda source_id: DataCenterObjectResponse(service.get_source(source_id)), None),
        RouteDefinition("PUT", "/api/data-center/sources/{source_id}", "data_center_source_update",
                        lambda payload, source_id: DataCenterObjectResponse(service.update_source(
                            source_id, {
                                "enabled": payload.enabled,
                                "requests_per_minute": payload.requests_per_minute,
                                "concurrency": payload.concurrency,
                                "retry_count": payload.retry_count,
                            },
                        )), DataCenterSourceUpdateRequest),
        RouteDefinition("POST", "/api/data-center/sources/{source_id}/test", "data_center_source_test",
                        lambda payload, source_id: DataCenterObjectResponse(
                            service.test_source(source_id, live=payload.live)
                        ), DataCenterRouteTestRequest),
        RouteDefinition("GET", "/api/data-center/datasets", "data_center_datasets",
                        lambda: DataCenterListResponse(service.list_datasets()), None),
        RouteDefinition("GET", "/api/data-center/routes", "data_center_routes",
                        lambda: DataCenterListResponse(service.list_routes()), None),
        RouteDefinition("PUT", "/api/data-center/routes", "data_center_routes_update",
                        lambda payload: DataCenterListResponse(service.update_routes(payload.routes)),
                        DataCenterRoutesUpdateRequest),
        RouteDefinition("POST", "/api/data-center/routes/test", "data_center_route_test",
                        lambda payload: DataCenterObjectResponse(
                            service.test_route(payload.route_id, live=payload.live)
                        ), DataCenterRouteTestRequest),
        RouteDefinition("GET", "/api/data-center/sync/latest-target", "data_center_sync_latest_target",
                        lambda: DataCenterObjectResponse(service.latest_sync_target()), None),
        RouteDefinition("POST", "/api/data-center/sync/preview", "data_center_sync_preview",
                        lambda payload: DataCenterObjectResponse(service.preview_sync(
                            dataset=payload.dataset_id or payload.dataset,
                            target_trade_date=payload.target_trade_date,
                            start_trade_date=payload.start_trade_date,
                            symbols=payload.symbols,
                            all_current=payload.all_current,
                            adjustments=payload.adjustments,
                            mode=payload.mode,
                            selected_shards=payload.selected_shards,
                        )), DataCenterSyncRequest),
        RouteDefinition("POST", "/api/data-center/sync/tasks", "data_center_sync_task_create",
                        lambda payload: DataCenterObjectResponse(service.create_sync_task(
                            dataset=payload.dataset_id or payload.dataset,
                            target_trade_date=payload.target_trade_date,
                            start_trade_date=payload.start_trade_date,
                            symbols=payload.symbols,
                            all_current=payload.all_current,
                            adjustments=payload.adjustments,
                            run_now=payload.run_now,
                            mode=payload.mode,
                            preview_token=payload.preview_token,
                            selected_shards=payload.selected_shards,
                        )), DataCenterSyncRequest),
        RouteDefinition("GET", "/api/data-center/sync/tasks", "data_center_sync_tasks",
                        lambda: DataCenterListResponse(service.list_sync_tasks()), None),
        RouteDefinition("DELETE", "/api/data-center/sync/tasks/{task_id}", "data_center_sync_task_delete",
                        lambda task_id: DataCenterObjectResponse(service.delete_sync_task(task_id)), None),        RouteDefinition("GET", "/api/data-center/sync/tasks/{task_id}", "data_center_sync_task_detail",
                        lambda task_id: DataCenterObjectResponse(service.get_sync_task(task_id)), None),
        RouteDefinition("GET", "/api/data-center/sync/tasks/{task_id}/items", "data_center_sync_task_items",
                        lambda task_id: DataCenterListResponse(service.get_sync_task_items(task_id)), None),
        RouteDefinition("POST", "/api/data-center/sync/tasks/{task_id}/run", "data_center_sync_run",
                        lambda task_id: DataCenterObjectResponse(service.run_sync_task(task_id)), None),
        RouteDefinition("POST", "/api/data-center/sync/tasks/{task_id}/stop", "data_center_sync_stop",
                        lambda task_id: DataCenterObjectResponse(service.stop_sync_task(task_id)), None),
        RouteDefinition("POST", "/api/data-center/sync/tasks/{task_id}/retry-failed", "data_center_sync_retry",
                        lambda payload, task_id: DataCenterObjectResponse(
                            service.retry_failed_sync_task(task_id, run_now=payload.run_now)
                        ), DataCenterRetryRequest),
        RouteDefinition("GET", "/api/data-center/quality/rules", "data_center_quality_rules",
                        lambda: DataCenterListResponse(service.list_quality_rules()), None),
        RouteDefinition("POST", "/api/data-center/quality/scans", "data_center_quality_scan_create",
                        lambda payload: DataCenterObjectResponse(service.create_quality_scan(
                            dataset=payload.dataset, date_from=payload.date_from,
                            date_to=payload.date_to, scope=payload.scope,
                            symbols=payload.symbols, adjustments=payload.adjustments,
                            rules=payload.rules, run_now=payload.run_now,
                        )), DataCenterQualityScanRequest),
        RouteDefinition("GET", "/api/data-center/quality/scans", "data_center_quality_scans",
                        lambda: DataCenterListResponse(service.list_quality_scans()), None),
        RouteDefinition("DELETE", "/api/data-center/quality/scans/{scan_id}", "data_center_quality_scan_delete",
                        lambda scan_id: DataCenterObjectResponse(service.delete_quality_scan(scan_id)), None),
        RouteDefinition("GET", "/api/data-center/quality/scans/{scan_id}", "data_center_quality_scan_detail",
                        lambda scan_id: DataCenterObjectResponse(service.get_quality_scan(scan_id)), None),
        RouteDefinition("POST", "/api/data-center/quality/scans/{scan_id}/run", "data_center_quality_scan_run",
                        lambda scan_id: DataCenterObjectResponse(service.run_quality_scan(scan_id)), None),
        RouteDefinition("POST", "/api/data-center/quality/scans/{scan_id}/recheck", "data_center_quality_scan_recheck",
                        lambda scan_id: DataCenterObjectResponse(service.recheck_quality_scan(scan_id)), None),
        RouteDefinition("POST", "/api/data-center/quality/scans/{scan_id}/pause", "data_center_quality_scan_pause",
                        lambda scan_id: DataCenterObjectResponse(service.pause_quality_scan(scan_id)), None),
        RouteDefinition("POST", "/api/data-center/quality/scans/{scan_id}/resume", "data_center_quality_scan_resume",
                        lambda scan_id: DataCenterObjectResponse(service.resume_quality_scan(scan_id)), None),
        RouteDefinition("POST", "/api/data-center/quality/scans/{scan_id}/stop", "data_center_quality_scan_stop",
                        lambda scan_id: DataCenterObjectResponse(service.stop_quality_scan(scan_id)), None),
        RouteDefinition("GET", "/api/data-center/quality/filter-options", "data_center_quality_filter_options",
                        lambda: DataCenterObjectResponse(service.quality_filter_options()), None),
        RouteDefinition("GET", "/api/data-center/quality/issues", "data_center_quality_issues",
                        lambda query: DataCenterListResponse(service.list_quality_issues(
                            status=query.status, severity=query.severity, dataset=query.dataset,
                            source_task_id=query.source_task_id, source=query.source, symbol=query.symbol,
                            rule_id=query.rule_id, date_from=query.date_from,
                            date_to=query.date_to, limit=query.limit,
                        )), DataCenterQualityIssueQuery),
        RouteDefinition("GET", "/api/data-center/quality/issues/export", "data_center_quality_export",
                        lambda query: DataCenterObjectResponse(service.export_quality_issues(
                            status=query.status, severity=query.severity, dataset=query.dataset,
                            source_task_id=query.source_task_id, source=query.source, symbol=query.symbol,
                            rule_id=query.rule_id, date_from=query.date_from,
                            date_to=query.date_to, limit=query.limit,
                        )), DataCenterQualityIssueQuery),
        RouteDefinition("GET", "/api/data-center/quality/summary", "data_center_quality_summary",
                        lambda query: DataCenterObjectResponse(service.summarize_quality_issues(
                            severity=query.severity, dataset=query.dataset,
                            source_task_id=query.source_task_id, source=query.source, symbol=query.symbol,
                            rule_id=query.rule_id, date_from=query.date_from,
                            date_to=query.date_to,
                        )), DataCenterQualityIssueQuery),
        RouteDefinition("POST", "/api/data-center/quality/issues/bulk/disposition",
                        "data_center_quality_bulk_disposition",
                        lambda payload: DataCenterObjectResponse(
                            service.bulk_disposition_quality_issues(
                                payload.issue_ids, action=payload.action, reason=payload.reason,
                                operator=payload.operator,
                            )
                        ), DataCenterQualityBulkRequest),
        RouteDefinition("POST", "/api/data-center/quality/issues/bulk/refetch",
                        "data_center_quality_bulk_refetch",
                        lambda payload: DataCenterObjectResponse(
                            service.bulk_refetch_quality_issues(
                                payload.issue_ids, reason=payload.reason,
                                operator=payload.operator, run_now=payload.run_now,
                            )
                        ), DataCenterQualityBulkRequest),
        RouteDefinition("GET", "/api/data-center/quality/issues/{issue_id}", "data_center_quality_detail",
                        lambda issue_id: DataCenterObjectResponse(service.get_quality_issue(issue_id)), None),
        RouteDefinition("GET", "/api/data-center/quality/issues/{issue_id}/history", "data_center_quality_history",
                        lambda issue_id: DataCenterObjectResponse(service.get_quality_issue_history(issue_id)), None),
        RouteDefinition("POST", "/api/data-center/quality/issues/{issue_id}/refetch", "data_center_quality_refetch",
                        lambda payload, issue_id: DataCenterObjectResponse(
                            service.refetch_quality_issue(issue_id, run_now=payload.run_now)
                        ), DataCenterQualityRefetchRequest),
        RouteDefinition("POST", "/api/data-center/quality/issues/{issue_id}/disposition",
                        "data_center_quality_disposition",
                        lambda payload, issue_id: DataCenterObjectResponse(
                            service.disposition_quality_issue(
                                issue_id, action=payload.action, reason=payload.reason,
                                operator=payload.operator, before=payload.before, after=payload.after,
                            )
                        ), DataCenterDispositionRequest),
        RouteDefinition("GET", "/api/data-center/assets", "data_center_assets",
                        lambda query: DataCenterObjectResponse(
                            service.list_assets(version_id=query.version_id)
                        ), DataCenterAssetQuery),
        RouteDefinition("GET", "/api/data-center/versions", "data_center_versions",
                        lambda: DataCenterObjectResponse(service.list_versions()), None),
        RouteDefinition("POST", "/api/data-center/versions/publish", "data_center_version_publish",
                        lambda payload: DataCenterObjectResponse(
                            service.publish_version(task_id=payload.task_id)
                        ), DataCenterPublishRequest),
        RouteDefinition("POST", "/api/data-center/versions/{version_id}/set-default",
                        "data_center_version_default",
                        lambda version_id: DataCenterObjectResponse(
                            service.set_default_version(version_id)
                        ), None),
    ]
