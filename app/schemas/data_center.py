"""Stage-86 data-center request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DataCenterObjectResponse:
    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DataCenterListResponse:
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DataCenterRoutesUpdateRequest:
    routes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DataCenterSourceUpdateRequest:
    enabled: bool | None = None
    requests_per_minute: int | None = None
    concurrency: int | None = None
    retry_count: int | None = None


@dataclass(frozen=True, slots=True)
class DataCenterRouteTestRequest:
    route_id: str = ""
    live: bool = False


@dataclass(frozen=True, slots=True)
class DataCenterSyncRequest:
    dataset: str = "a_share_daily"
    dataset_id: str = ""
    target_trade_date: str = ""
    start_trade_date: str = ""
    symbols: list[str] = field(default_factory=list)
    all_current: bool = False
    adjustments: list[str] = field(default_factory=lambda: ["raw", "qfq", "hfq"])
    mode: str = "incremental"
    run_now: bool = False
    preview_token: str = ""
    selected_shards: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DataCenterReferenceRefreshRequest:
    target_trade_date: str = ""
    preview_token: str = ""


@dataclass(frozen=True, slots=True)
class DataCenterIndexSnapshotSyncRequest:
    index_codes: list[str] = field(default_factory=lambda: [
        "000300.XSHG", "000905.XSHG", "000852.XSHG",
    ])
    operator: str = "local-user"
    authorization_confirmed: bool = False
    authorization_reference: str = ""

@dataclass(frozen=True, slots=True)
class DataCenterRetryRequest:
    run_now: bool = False


@dataclass(frozen=True, slots=True)
class DataCenterQualityIssueQuery:
    status: str = ""
    severity: str = ""
    dataset: str = ""
    source_task_id: str = ""
    source: str = ""
    symbol: str = ""
    rule_id: str = ""
    date_from: str = ""
    date_to: str = ""
    limit: int = 100


@dataclass(frozen=True, slots=True)
class DataCenterQualityScanRequest:
    dataset: str = "a_share_daily"
    date_from: str = ""
    date_to: str = ""
    scope: str = "all_current"
    symbols: list[str] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=lambda: ["raw", "qfq", "hfq"])
    rules: list[str] = field(default_factory=lambda: [
        "missing_open_day", "ohlcv_validity", "adjustment_date_consistency",
        "trading_status_semantics",
    ])
    run_now: bool = False


@dataclass(frozen=True, slots=True)
class DataCenterQualityRefetchRequest:
    run_now: bool = False


@dataclass(frozen=True, slots=True)
class DataCenterTradingStatusRepairRequest:
    preview_token: str = ""
    operator: str = "local-user"


@dataclass(frozen=True, slots=True)
class DataCenterTradingStatusBatchPreviewRequest:
    scope: str = "all_symbols"


@dataclass(frozen=True, slots=True)
class DataCenterTradingStatusBatchResumeRequest:
    confirmation: str = ""


@dataclass(frozen=True, slots=True)
class DataCenterTradingStatusBatchRequest:
    expected_candidate_set_hash: str = ""
    run_id: str = ""
    operator: str = ""
    confirmation: str = ""
    max_writes: int = 100
    scope: str = ""
    authorized_total_writes: int = 0
    commit_batch_size: int = 1_000
    authorization_reference: str = ""


@dataclass(frozen=True, slots=True)
class DataCenterTradingStatusClosureRecheckRequest:
    expected_base_version_id: str = ""
    expected_base_manifest_hash: str = ""
    expected_change_set_hash: str = ""


@dataclass(frozen=True, slots=True)
class DataCenterTradingStatusIssueReconciliationRequest:
    scan_id: str = ""
    expected_issue_set_hash: str = ""
    operator: str = ""
    reason: str = ""
    confirmation: str = ""


@dataclass(frozen=True, slots=True)
class DataCenterCorrectionPublishRequest:
    expected_base_version_id: str = ""
    expected_base_manifest_hash: str = ""
    expected_change_set_hash: str = ""
    expected_quality_report_id: str = ""
    expected_quality_report_hash: str = ""
    operator: str = ""
    authorization_reference: str = ""
    confirmation: str = ""


@dataclass(frozen=True, slots=True)
class DataCenterQualityBulkRequest:
    issue_ids: list[str] = field(default_factory=list)
    action: str = ""
    reason: str = ""
    operator: str = "local-user"
    run_now: bool = False
    corrections: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DataCenterDispositionRequest:
    action: str = ""
    reason: str = ""
    operator: str = "local-user"
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DataCenterAssetQuery:
    version_id: str = ""


@dataclass(frozen=True, slots=True)
class DataCenterProbeQuery:
    source_id: str = ""
    route_id: str = ""
    limit: int = 100


@dataclass(frozen=True, slots=True)
class DataCenterReleaseReadinessQuery:
    version_id: str = ""


@dataclass(frozen=True, slots=True)
class DataCenterPublishRequest:
    task_id: str = ""
