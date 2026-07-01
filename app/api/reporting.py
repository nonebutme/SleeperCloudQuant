from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.reporting import BatchSummaryResponse, RunDetailResponse
from app.services.reporting_service import ReportingService



def get_run_detail(service: ReportingService, run_id: str) -> RunDetailResponse | None:
    detail = service.get_run_detail(run_id)
    if detail is None:
        return None
    return RunDetailResponse(detail=detail)



def get_batch_summary(service: ReportingService, experiment_id: str) -> BatchSummaryResponse | None:
    summary = service.get_batch_summary(experiment_id)
    if summary is None:
        return None
    return BatchSummaryResponse(summary=summary)



def build_reporting_routes(service: ReportingService) -> list[RouteDefinition]:
    return [
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
    ]
