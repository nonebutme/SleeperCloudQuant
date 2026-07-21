"""AI analysis routes."""

from __future__ import annotations

from urllib.parse import unquote

from app.api.contracts import RouteDefinition
from app.schemas.ai import (
    AIAnalysisRequestPayload,
    AIAnalysisResponsePayload,
    AIWorkflowDetailResponsePayload,
    AIWorkflowHistoryRequestPayload,
    AIWorkflowHistoryResponsePayload,
    AIWorkflowRunRequestPayload,
    AIWorkflowRunResponsePayload,
)
from app.services.ai_analysis_service import AIAnalysisService


def analyze_stock(service: AIAnalysisService, payload: AIAnalysisRequestPayload) -> AIAnalysisResponsePayload:
    report = service.analyze_stock(
        symbol=payload.symbol,
        analysis_date=payload.analysis_date,
        report_id=payload.report_id,
        include_risk_notice=payload.include_risk_notice,
    )
    return AIAnalysisResponsePayload(report=report)


def run_workflow(service: AIAnalysisService, payload: AIWorkflowRunRequestPayload) -> AIWorkflowRunResponsePayload:
    workflow = service.run_workflow(
        symbol=payload.symbol,
        analysis_date=payload.analysis_date,
        report_id=payload.report_id,
        max_debate_rounds=payload.max_debate_rounds,
        include_risk_notice=payload.include_risk_notice,
        enabled_analysts=payload.enabled_analysts,
        enabled_researchers=payload.enabled_researchers,
        risk_team=payload.risk_team,
        provider_profile=payload.provider_profile,
        decision_policy=payload.decision_policy,
    )
    return AIWorkflowRunResponsePayload(workflow=workflow)


def list_workflows(service: AIAnalysisService, payload: AIWorkflowHistoryRequestPayload) -> AIWorkflowHistoryResponsePayload:
    workflows = service.list_workflows(symbol=payload.symbol, limit=payload.limit)
    return AIWorkflowHistoryResponsePayload(workflows=workflows)


def get_workflow(service: AIAnalysisService, workflow_id: str) -> AIWorkflowDetailResponsePayload | None:
    workflow = service.get_workflow(unquote(workflow_id))
    if workflow is None:
        return None
    return AIWorkflowDetailResponsePayload(workflow=workflow)


def build_ai_routes(service: AIAnalysisService) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="POST",
            path="/api/ai/analyze",
            name="ai_analyze_stock",
            handler=lambda payload: analyze_stock(service, payload),
            request_model=AIAnalysisRequestPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/ai/workflow/run",
            name="ai_workflow_run",
            handler=lambda payload: run_workflow(service, payload),
            request_model=AIWorkflowRunRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/ai/workflows",
            name="ai_workflow_history",
            handler=lambda payload: list_workflows(service, payload),
            request_model=AIWorkflowHistoryRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/ai/workflow/{workflow_id}",
            name="ai_workflow_detail",
            handler=lambda workflow_id: get_workflow(service, workflow_id),
        ),
    ]

