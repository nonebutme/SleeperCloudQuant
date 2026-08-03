"""Market request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.market.models import Bar, MarketSyncStatus, MarketSyncSummary


@dataclass(frozen=True, slots=True)
class MarketPanoramaQuery:
    """Read the point-in-time market panorama for one K-line trade date."""

    trade_date: str
    symbol: str = ""
    asset_type: str = "stock"


@dataclass(frozen=True, slots=True)
class MarketPanoramaResponse:
    """Market panorama response with per-dataset availability metadata."""

    panorama: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketPriceHistoryQuery:
    """Minimal request payload for one price-history query."""

    symbol: str
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True, slots=True)
class MarketPriceHistoryResponse:
    """Minimal response payload for one price-history query."""

    symbol: str
    rows: list[Bar] = field(default_factory=list)
    source_trace: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketTradingCalendarQuery:
    """Minimal request payload for one trading-calendar query."""

    start_date: str
    end_date: str


@dataclass(frozen=True, slots=True)
class MarketTradingCalendarResponse:
    """Minimal response payload for one trading-calendar query."""

    days: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MarketSyncPriceHistoryRequest:
    """Explicit sync request for one symbol price-history range."""

    symbol: str
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True, slots=True)
class MarketSyncTradingCalendarRequest:
    """Explicit sync request for one trading-calendar range."""

    start_date: str
    end_date: str


@dataclass(frozen=True, slots=True)
class MarketSyncResponse:
    """Minimal response payload for one market-data sync action."""

    summary: MarketSyncSummary


@dataclass(frozen=True, slots=True)
class MarketSyncStatusResponse:
    """Minimal response payload for one market-data sync-status query."""

    status: MarketSyncStatus






@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarsQuery:
    """Read normalized locally stored price bars for one symbol."""

    symbol: str
    start_date: str | None = None
    end_date: str | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarsResponse:
    """Local normalized price bar query response."""

    symbol: str
    rows: list[Bar] = field(default_factory=list)
    storage_status: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarStatusQuery:
    """Read normalized local price bar storage status."""

    symbol: str | None = None


@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarStatusResponse:
    """Normalized local price bar storage status response."""

    status: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarQualityQuery:
    """Inspect local price bar quality for one symbol/date window."""

    symbol: str
    start_date: str
    end_date: str


@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarQualityResponse:
    """Local price bar quality report response."""

    report: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarRepairRequest:
    """Repair local price bar gaps by resyncing missing date ranges."""

    symbol: str
    start_date: str
    end_date: str


@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarRepairResponse:
    """Local price bar gap repair response."""

    result: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarAssetsQuery:
    """Read local market price-bar assets and governance manifest."""

    symbol: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class MarketLocalPriceBarAssetsResponse:
    """Local market price-bar asset governance response."""

    assets: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class MarketDataBrowserQuery:
    """Read local market data browser payload."""

    symbol: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    limit: int = 120


@dataclass(frozen=True, slots=True)
class MarketDataBrowserResponse:
    """Local market data browser response."""

    browser: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AShareOverviewQuery:
    """Read the accepted A-share source database overview."""

    refresh: bool = False


@dataclass(frozen=True, slots=True)
class AShareOverviewResponse:
    """A-share source database overview response."""

    overview: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AShareSymbolsQuery:
    """Search the current and historical A-share symbol catalog."""

    query: str = ""
    market: str = ""
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class AShareSymbolsResponse:
    """Paginated A-share symbol catalog response."""

    catalog: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AShareDailyPricesQuery:
    """Read one A-share daily price window from the source database."""

    symbol: str
    adjustment: str = "raw"
    start_date: str | None = None
    end_date: str | None = None
    limit: int = 200
    offset: int = 0


@dataclass(frozen=True, slots=True)
class AShareDailyPricesResponse:
    """Paginated A-share daily price response."""

    daily: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexSymbolsQuery:
    """Read the governed local index catalog."""

    market: str = ""


@dataclass(frozen=True, slots=True)
class IndexSymbolsResponse:
    """Governed local index catalog response."""

    catalog: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexDailyPricesQuery:
    """Read one governed index daily-price window."""

    index_symbol: str
    start_date: str | None = None
    end_date: str | None = None
    limit: int = 200
    offset: int = 0


@dataclass(frozen=True, slots=True)
class IndexDailyPricesResponse:
    """Paginated governed index daily-price response."""

    daily: dict[str, Any] = field(default_factory=dict)
