"""Request payloads for governed factor research APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FactorResearchConfigRequest:
    factor_id: str
    start_date: str
    end_date: str
    factor_version: str | None = None
    task_id: str | None = None
    name: str | None = None
    pool_type: str = "all_a"
    universe_policy: str = "observed_price_with_lifecycle"
    pool_code: str | None = None
    pool_as_of_date: str | None = None
    symbols: list[str] = field(default_factory=list)
    symbol_limit: int = 0
    research_mode: str = "governed"
    sample_split: dict[str, Any] = field(default_factory=dict)
    acceptance_policy_id: str = "factor-acceptance-v1"
    data_version_id: str | None = None
    factor_adjustment: str = "raw"
    outcome_adjustment: str = "qfq"
    forward_horizons: list[int] = field(default_factory=lambda: [5])
    preprocessing: dict[str, Any] = field(default_factory=dict)
    group_count: int = 5
    rebalance_frequency: str = "daily_cross_section"
    cost_assumption: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FactorResearchDashboardQuery:
    factor_id: str | None = None
    pool_type: str | None = None
    context_id: str | None = None


@dataclass(frozen=True, slots=True)
class FactorResearchArtifactListQuery:
    factor_id: str | None = None
    limit: str | None = None


@dataclass(frozen=True, slots=True)
class FactorResearchTaskListQuery:
    status: str | None = None
    limit: str | None = None

@dataclass(frozen=True, slots=True)
class FactorOptimizationConfigRequest:
    artifact_id: str
    task_id: str | None = None
    value_field: str = "aligned_value"
    forward_horizons: list[int] = field(default_factory=list)
    group_counts: list[int] = field(default_factory=lambda: [3, 5, 10])
    one_side_rates: list[float] = field(default_factory=lambda: [0.0])
    min_cross_section_size: int = 5


@dataclass(frozen=True, slots=True)
class FactorOptimizationTaskListQuery:
    status: str | None = None
    limit: str | None = None


@dataclass(frozen=True, slots=True)
class FactorArtifactReviewRequest:
    decision: str
    note: str
    reviewer: str = "local-research-owner"


@dataclass(frozen=True, slots=True)
class FactorArtifactSuspendRequest:
    note: str


@dataclass(frozen=True, slots=True)
class FactorArtifactMonitorRequest:
    lookback_periods: int = 22


@dataclass(frozen=True, slots=True)
class FactorOosRevealRequest:
    reason: str
    actor: str = "local-research-owner"


@dataclass(frozen=True, slots=True)
class MultiFactorResearchRequest:
    factor_id: str
    name: str
    artifact_ids: list[str] = field(default_factory=list)
    method: str = "equal_rank"
    weights: list[float] = field(default_factory=list)
    description: str = ""




@dataclass(frozen=True, slots=True)
class FactorResearchReportCompareQuery:
    report_ids: str | None = None


@dataclass(frozen=True, slots=True)
class FactorIndexComponentsRequest:
    rows: list[dict[str, Any]] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class FactorDefinitionCreateRequest:
    factor_id: str
    name: str
    expression: str
    category: str = "自定义"
    description: str = ""
    direction: str = "positive"
