"""AI analysis request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AIAnalysisRequestPayload:
    """Minimal request payload for one stock AI analysis task."""

    symbol: str
    analysis_date: str | None = None
    report_id: str | None = None
    include_risk_notice: bool = True


@dataclass(frozen=True, slots=True)
class AIAnalysisReportPayload:
    """Structured AI analysis report shown by the Web MVP."""

    report_id: str
    symbol: str
    title: str
    status: str
    generated_at: str
    data_basis: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    disclaimer: str = ""
    provider_mode: str = "local-demo"
    source_trace: dict[str, Any] = field(default_factory=dict)
    analyst_team: list[dict[str, Any]] = field(default_factory=list)
    research_debate: list[dict[str, Any]] = field(default_factory=list)
    risk_committee: list[dict[str, Any]] = field(default_factory=list)
    portfolio_decision: dict[str, Any] = field(default_factory=dict)
    workflow_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AIAnalysisResponsePayload:
    """Minimal response payload for one AI analysis task."""

    report: AIAnalysisReportPayload


@dataclass(frozen=True, slots=True)
class AIWorkflowRunRequestPayload:
    """Run a TradingAgents-style local workflow trace."""

    symbol: str
    analysis_date: str | None = None
    report_id: str | None = None
    max_debate_rounds: int = 1
    include_risk_notice: bool = True
    enabled_analysts: list[str] = field(default_factory=list)
    enabled_researchers: list[str] = field(default_factory=list)
    risk_team: list[str] = field(default_factory=list)
    provider_profile: str | None = None
    decision_policy: str | None = None
    online_tools_enabled: bool = False


@dataclass(frozen=True, slots=True)
class AIWorkflowRunResponsePayload:
    """Response wrapper for a TradingAgents-style workflow trace."""

    workflow: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class AIWorkflowHistoryRequestPayload:
    """Query saved AI workflow traces."""

    symbol: str | None = None
    limit: int = 20


@dataclass(frozen=True, slots=True)
class AIWorkflowHistoryResponsePayload:
    """Response wrapper for saved workflow trace summaries."""

    workflows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AIWorkflowDetailResponsePayload:
    """Response wrapper for one saved workflow trace."""

    workflow: dict[str, Any] = field(default_factory=dict)



