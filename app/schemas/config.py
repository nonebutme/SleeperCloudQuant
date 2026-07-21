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
