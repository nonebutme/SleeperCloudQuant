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
    ])
    run_now: bool = False


@dataclass(frozen=True, slots=True)
class DataCenterQualityRefetchRequest:
    run_now: bool = False


@dataclass(frozen=True, slots=True)
class DataCenterQualityBulkRequest:
    issue_ids: list[str] = field(default_factory=list)
    action: str = ""
    reason: str = ""
    operator: str = "local-user"
    run_now: bool = False


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
class DataCenterPublishRequest:
    task_id: str = ""
