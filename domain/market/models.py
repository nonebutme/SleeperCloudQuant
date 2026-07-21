"""Minimal market-domain models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Stock:
    """Minimal stock identifier model."""

    symbol: str
    name: str | None = None
    exchange: str | None = None


@dataclass(frozen=True, slots=True)
class Bar:
    """Minimal OHLCV row used by services and schemas."""

    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class MarketSyncSummary:
    """Minimal summary for one explicit market-data sync action."""

    dataset: str
    status: str
    started_at: str
    finished_at: str
    row_count: int
    symbol: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    cache_key: str | None = None
    source_trace: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketCacheStatus:
    """Minimal cache status snapshot for one dataset."""

    dataset: str
    cache_key: str | None
    row_count: int
    created_at: str | None
    symbol: str | None = None
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True, slots=True)
class MarketSyncStatus:
    """Minimal read model for the latest sync and cache state of one dataset."""

    dataset: str
    latest_run: MarketSyncSummary | None
    cache_status: MarketCacheStatus | None



