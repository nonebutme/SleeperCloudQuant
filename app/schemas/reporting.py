"""Reporting request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.report.models import BatchExperimentSummaryModel, BacktestRunDetailModel


@dataclass(frozen=True, slots=True)
class BacktestModeReportResponsePayload:
    """Professional report for one backtest execution mode task."""

    report: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class RunDetailResponse:
    """Minimal response payload for one run-detail query."""

    detail: BacktestRunDetailModel


@dataclass(frozen=True, slots=True)
class BatchSummaryResponse:
    """Minimal response payload for one batch-summary query."""

    summary: BatchExperimentSummaryModel


@dataclass(frozen=True, slots=True)
class StrategyEvaluationMetricPayload:
    """One metric shown inside a strategy-evaluation dimension."""

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class StrategyEvaluationChartPayload:
    """Small chart payload rendered by the Web MVP without external dependencies."""

    kind: str
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StrategyEvaluationDimensionPayload:
    """One of the seven strategy-evaluation dimensions from the three2 template."""

    key: str
    short_label: str
    title: str
    score: int
    level: str
    metrics: list[StrategyEvaluationMetricPayload] = field(default_factory=list)
    chart: StrategyEvaluationChartPayload = field(default_factory=lambda: StrategyEvaluationChartPayload(kind="bar"))
    evidence_status: str = "ready"
    score_reason: str = ""


@dataclass(frozen=True, slots=True)
class StrategyEvaluationReportPayload:
    """Seven-dimension strategy evaluation report inspired by SleeperCloudQuant-old three2.html."""

    run_id: str
    strategy_name: str
    title: str
    subtitle: str
    average_score: int
    dimensions: list[StrategyEvaluationDimensionPayload] = field(default_factory=list)
    conclusions: list[str] = field(default_factory=list)
    data_quality_notes: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    score_breakdown: dict[str, Any] = field(default_factory=dict)
    decision_flags: list[dict[str, Any]] = field(default_factory=list)
    analysis_summary: dict[str, Any] = field(default_factory=dict)
    report_version: str = "strategy-evaluation-v2"
    evaluation_scope: str = "single_run_or_shared_portfolio"
    evidence_quality: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyEvaluationResponse:
    """Response wrapper for the strategy-evaluation report."""

    report: StrategyEvaluationReportPayload


@dataclass(frozen=True, slots=True)
class ReportSnapshotSummaryPayload:
    """Summary row for one persisted report snapshot."""

    snapshot_id: str
    run_id: str
    report_type: str
    report_version: str
    created_at: str
    title: str


@dataclass(frozen=True, slots=True)
class ReportSnapshotPayload:
    """One persisted report snapshot with its full payload."""

    snapshot_id: str
    run_id: str
    report_type: str
    report_version: str
    created_at: str
    title: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReportSnapshotSaveRequestPayload:
    """Request to save a generated report as an auditable snapshot."""

    report_type: str = "strategy_evaluation"
    report_version: str = "three2-v1"


@dataclass(frozen=True, slots=True)
class ReportSnapshotSaveResponse:
    """Response returned after saving one report snapshot."""

    snapshot: ReportSnapshotPayload
    status: str = "snapshot_saved"


@dataclass(frozen=True, slots=True)
class ReportSnapshotListResponse:
    """List persisted report snapshots for one run."""

    snapshots: list[ReportSnapshotSummaryPayload] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReportSnapshotDetailResponse:
    """Read one persisted report snapshot."""

    snapshot: ReportSnapshotPayload


@dataclass(frozen=True, slots=True)
class ParameterScanComparisonRowPayload:
    """One ranked row in a parameter-scan comparison report."""

    rank: int
    run_id: str
    strategy_name: str
    strategy_id: str | None
    strategy_version: str | None
    parameters: dict[str, Any] = field(default_factory=dict)
    annualized_returns: float | None = None
    total_returns: float | None = None
    max_drawdown: float | None = None
    sharpe: float | None = None
    score: float = 0.0
    status: str = "unknown"


@dataclass(frozen=True, slots=True)
class ParameterScanComparisonReportPayload:
    """Comparison report for runs produced by one parameter scan."""

    run_id_prefix: str
    title: str
    best_run_id: str | None
    best_parameters: dict[str, Any] = field(default_factory=dict)
    rows: list[ParameterScanComparisonRowPayload] = field(default_factory=list)
    recommendation: str = ""
    data_quality_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ParameterScanComparisonResponse:
    """Response wrapper for one parameter-scan comparison report."""

    report: ParameterScanComparisonReportPayload

@dataclass(frozen=True, slots=True)
class ReportingAIWorkflowReplayQuery:
    """Query linked AI workflow trace for a reporting run."""

    symbol: str | None = None


@dataclass(frozen=True, slots=True)
class ReportingAIWorkflowReplayResponse:
    """Response wrapper for AI workflow replay shown in the report center."""

    replay: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ReportPackageCreateRequestPayload:
    """Create an auditable research package binding run, AI workflow, and report snapshot."""

    symbol: str | None = None
    workflow_id: str | None = None
    title: str | None = None


@dataclass(frozen=True, slots=True)
class ReportPackageResponsePayload:
    """Response wrapper for one research report package."""

    package: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReportPackageListResponsePayload:
    """List research report packages for one run."""

    packages: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReportPackageDirectoryQueryPayload:
    """Query report packages across runs for archive browsing."""

    run_id: str | None = None
    package_type: str | None = None
    lifecycle_status: str | None = None
    limit: str | int = 20


@dataclass(frozen=True, slots=True)
class ReportPackageDirectoryResponsePayload:
    """Report package archive directory response."""

    directory: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ReportPackageLifecycleUpdateRequestPayload:
    """Update non-destructive lifecycle metadata for one report package."""

    status: str = "active"
    retention_policy: str | None = None
    protected: bool = False
    reason: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class ReportPackageLifecycleUpdateResponsePayload:
    """Response after updating report package lifecycle metadata."""

    package: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ReportPackageExportManifestQueryPayload:
    """Build an offline export manifest from filtered report packages."""

    run_id: str | None = None
    package_type: str | None = None
    lifecycle_status: str | None = None
    formats: str = "html,json"
    limit: str | int = 20


@dataclass(frozen=True, slots=True)
class ReportPackageExportManifestResponsePayload:
    """Offline export manifest response."""

    manifest: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ReportPackageExportQueryPayload:
    """Query one report package export format."""

    format: str = "html"


@dataclass(frozen=True, slots=True)
class ReportPackageExportResponsePayload:
    """Exported report package content returned through JSON transport."""

    export: dict[str, Any] = field(default_factory=dict)



@dataclass(frozen=True, slots=True)
class ExperimentReportComparisonResponsePayload:
    """Experiment-level report comparison response."""

    comparison: dict[str, Any] = field(default_factory=dict)
@dataclass(frozen=True, slots=True)
class ExperimentReviewPackageCreateRequestPayload:
    """Create an experiment-level review package from the indexed primary run."""

    symbol: str | None = None
    workflow_id: str | None = None
    title: str | None = None
    create_package: bool = True


@dataclass(frozen=True, slots=True)
class ExperimentReviewPackageResponsePayload:
    """Experiment-level review package response."""

    review: dict[str, Any] = field(default_factory=dict)







