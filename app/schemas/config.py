"""Configuration center response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ConfigStatusResponsePayload:
    """Configuration status shown by the Web MVP."""

    status: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BacktestProfilesResponsePayload:
    """Backtest profile listing shown by the Web MVP."""

    profiles: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfigRuntimeDraftSaveRequestPayload:
    """Save editable runtime configuration fields from the Web MVP."""

    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfigRuntimeDraftSaveResponsePayload:
    """Result of saving one local runtime configuration draft."""

    status: str
    draft: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfigMarketProviderPreflightRequestPayload:
    """Run a non-persistent market provider connectivity and mapping preflight."""

    symbol: str = "000001.XSHE"
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigMarketProviderPreflightResponsePayload:
    """Result of one market provider preflight."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfigMarketProviderSyncTaskCreateRequestPayload:
    """Create one local market provider sync task."""

    symbols: list[str] = field(default_factory=lambda: ["000001.XSHE"])
    start_date: str = "2020-01-01"
    end_date: str = "2020-01-02"
    interval_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class ConfigMarketProviderSyncTaskListResponsePayload:
    """List local market provider sync tasks."""

    tasks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ConfigMarketProviderSyncTaskResponsePayload:
    """Result of one local market provider sync task action."""

    task: dict[str, Any] = field(default_factory=dict)
@dataclass(frozen=True, slots=True)
class ConfigAShareSchedulerConfigureRequestPayload:
    """Configure the persistent application-local A-share scheduler."""

    enabled: bool = False
    run_time: str = "18:15"
    timezone_name: str = "Asia/Shanghai"
    adjustments: list[str] = field(default_factory=lambda: ["raw", "qfq", "hfq"])


@dataclass(frozen=True, slots=True)
class ConfigAShareSyncJobCreateRequestPayload:
    """Create one canonical A-share incremental release job."""

    target_trade_date: str = ""
    symbols: list[str] = field(default_factory=list)
    all_current: bool = False
    adjustments: list[str] = field(default_factory=lambda: ["raw", "qfq", "hfq"])
    run_now: bool = False


@dataclass(frozen=True, slots=True)
class ConfigAShareSchedulerResponsePayload:
    """Scheduler status or job action response."""

    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfigAShareSyncJobListResponsePayload:
    """List canonical A-share incremental release jobs."""

    jobs: list[dict[str, Any]] = field(default_factory=list)
