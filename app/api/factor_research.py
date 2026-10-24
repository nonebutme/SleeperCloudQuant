"""Formal stage-87 factor-research routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.api.contracts import RouteDefinition
from app.schemas.factor_research import (
    FactorDefinitionCreateRequest,
    FactorOptimizationConfigRequest,
    FactorOptimizationTaskListQuery,
    FactorResearchConfigRequest,
    FactorResearchArtifactListQuery,
    FactorResearchDashboardQuery,
    FactorResearchReportCompareQuery,
    FactorResearchTaskListQuery,
    FactorArtifactReviewRequest,
    FactorArtifactSuspendRequest,
    FactorArtifactMonitorRequest,
    FactorOosRevealRequest,
    MultiFactorResearchRequest,
)
from app.services.factor_analysis_service import FactorAnalysisService


def _limit(value: str | None, default: int = 50) -> int:
    if value is None or value == "":
        return default
    try:
        return max(1, min(int(value), 200))
    except ValueError as error:
        raise ValueError("limit must be an integer") from error


def _governed_response(
    service: FactorAnalysisService,
    payload: dict[str, Any],
) -> dict[str, Any]:
    result = dict(payload)
    if not result.get("capabilities"):
        result["capabilities"] = service.capabilities()
    report_payload = result.get("payload")
    research = dict(report_payload) if isinstance(report_payload, dict) else result
    preflight = result.get("preflight")
    preflight = dict(preflight) if isinstance(preflight, dict) else {}
    context = result.get("context") or research.get("context") or preflight.get("context")
    context = dict(context) if isinstance(context, dict) else {}
    if context:
        result.setdefault("context_hash", context.get("context_hash") or result.get("context_hash"))
        result.setdefault(
            "data_version",
            research.get("data_version") or preflight.get("data_version"),
        )
        result.setdefault(
            "requested_range",
            research.get("requested_range") or context.get("requested_range"),
        )
        result.setdefault(
            "effective_range",
            research.get("effective_range") or context.get("effective_range"),
        )
        result.setdefault(
            "evidence",
            research.get("evidence") or preflight.get("evidence") or {},
        )
        result.setdefault(
            "reasons",
            research.get("reasons") or preflight.get("reasons") or [],
        )
    return result


def build_factor_research_routes(
    service: FactorAnalysisService,
) -> list[RouteDefinition]:
    respond = lambda payload: _governed_response(service, payload)
    return [
        RouteDefinition(
            "POST",
            "/api/factor-research/definitions/validate",
            "factor_research_definition_validate",
            lambda payload: respond(service.validate_definition(asdict(payload))),
            FactorDefinitionCreateRequest,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/definitions",
            "factor_research_definition_create",
            lambda payload: respond(service.create_definition(asdict(payload))),
            FactorDefinitionCreateRequest,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/definitions",
            "factor_research_definitions",
            lambda: respond(service.list_definitions()),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/definitions/{factor_id}",
            "factor_research_definition_detail",
            lambda factor_id: respond(service.get_definition(factor_id)),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/r3-studies",
            "factor_research_r3_studies",
            lambda: respond(service.list_r3_studies()),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/dashboard",
            "factor_research_dashboard",
            lambda query: respond(
                service.dashboard(
                    factor_id=str(query.factor_id or ""),
                    pool_type=str(query.pool_type or ""),
                    context_id=str(query.context_id or ""),
                )
            ),
            FactorResearchDashboardQuery,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/preflight",
            "factor_research_preflight",
            lambda payload: respond(service.preflight(asdict(payload))),
            FactorResearchConfigRequest,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/tasks",
            "factor_research_task_create",
            lambda payload: respond(service.create_task(asdict(payload))),
            FactorResearchConfigRequest,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/tasks",
            "factor_research_tasks",
            lambda query: respond(
                service.list_tasks(
                    status=str(query.status or ""),
                    limit=_limit(query.limit),
                )
            ),
            FactorResearchTaskListQuery,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/tasks/{task_id}",
            "factor_research_task_detail",
            lambda task_id: respond(service.get_task(task_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/tasks/{task_id}/start",
            "factor_research_task_start",
            lambda task_id: respond(service.start_task(task_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/tasks/{task_id}/stop",
            "factor_research_task_stop",
            lambda task_id: respond(service.stop_task(task_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/tasks/{task_id}/retry-failed",
            "factor_research_task_retry",
            lambda task_id: respond(service.retry_failed(task_id)),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/reports/{report_id}",
            "factor_research_report",
            lambda report_id: respond(service.get_report(report_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/reports/{report_id}/reveal-out-of-sample",
            "factor_research_report_reveal_out_of_sample",
            lambda payload, report_id: respond(
                service.reveal_out_of_sample(report_id, **asdict(payload))
            ),
            FactorOosRevealRequest,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/reports/{report_id}/compare",
            "factor_research_report_compare",
            lambda query, report_id: respond(
                service.compare_reports(
                    report_id,
                    [
                        item.strip()
                        for item in str(query.report_ids or "").split(",")
                        if item.strip()
                    ],
                )
            ),
            FactorResearchReportCompareQuery,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/artifacts",
            "factor_research_artifacts",
            lambda query: respond(
                service.list_artifacts(
                    factor_id=str(query.factor_id or ""), limit=_limit(query.limit, 100)
                )
            ),
            FactorResearchArtifactListQuery,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/multi-factor/research",
            "multi_factor_research_create",
            lambda payload: respond(service.create_multi_factor_research(asdict(payload))),
            MultiFactorResearchRequest,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/artifacts/{artifact_id}/governance",
            "factor_research_artifact_governance",
            lambda artifact_id: respond(service.get_artifact_governance(artifact_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/artifacts/{artifact_id}/review",
            "factor_research_artifact_review",
            lambda payload, artifact_id: respond(
                service.review_artifact(artifact_id, **asdict(payload))
            ),
            FactorArtifactReviewRequest,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/artifacts/{artifact_id}/register",
            "factor_research_artifact_register",
            lambda artifact_id: respond(service.register_artifact(artifact_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/artifacts/{artifact_id}/suspend",
            "factor_research_artifact_suspend",
            lambda payload, artifact_id: respond(
                service.suspend_artifact(artifact_id, **asdict(payload))
            ),
            FactorArtifactSuspendRequest,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/artifacts/{artifact_id}/monitor",
            "factor_research_artifact_monitor",
            lambda payload, artifact_id: respond(
                service.monitor_artifact(artifact_id, **asdict(payload))
            ),
            FactorArtifactMonitorRequest,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/artifacts/{artifact_id}/monitoring",
            "factor_research_artifact_monitoring",
            lambda artifact_id: respond(service.list_artifact_monitoring(artifact_id)),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/artifacts/{artifact_id}/strategy-declaration",
            "factor_research_artifact_strategy_declaration",
            lambda artifact_id: respond(
                service.export_strategy_factor_declaration(artifact_id)
            ),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/artifacts/{artifact_id}",
            "factor_research_artifact_detail",
            lambda artifact_id: respond(service.get_artifact(artifact_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/optimization/preflight",
            "factor_optimization_preflight",
            lambda payload: respond(service.preflight_optimization(asdict(payload))),
            FactorOptimizationConfigRequest,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/optimization/tasks",
            "factor_optimization_task_create",
            lambda payload: respond(service.create_optimization_task(asdict(payload))),
            FactorOptimizationConfigRequest,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/optimization/tasks",
            "factor_optimization_tasks",
            lambda query: respond(
                service.list_optimization_tasks(
                    status=str(query.status or ""),
                    limit=_limit(query.limit),
                )
            ),
            FactorOptimizationTaskListQuery,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/optimization/tasks/{task_id}",
            "factor_optimization_task_detail",
            lambda task_id: respond(service.get_optimization_task(task_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/optimization/tasks/{task_id}/start",
            "factor_optimization_task_start",
            lambda task_id: respond(service.start_optimization_task(task_id)),
            None,
        ),
        RouteDefinition(
            "POST",
            "/api/factor-research/optimization/tasks/{task_id}/retry",
            "factor_optimization_task_retry",
            lambda task_id: respond(service.retry_optimization_task(task_id)),
            None,
        ),
        RouteDefinition(
            "GET",
            "/api/factor-research/optimization/reports/{report_id}",
            "factor_optimization_report",
            lambda report_id: respond(service.get_optimization_report(report_id)),
            None,
        ),

    ]
