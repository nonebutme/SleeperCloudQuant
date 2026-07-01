"""Market request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.market.models import Bar


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


@dataclass(frozen=True, slots=True)
class MarketTradingCalendarQuery:
    """Minimal request payload for one trading-calendar query."""

    start_date: str
    end_date: str


@dataclass(frozen=True, slots=True)
class MarketTradingCalendarResponse:
    """Minimal response payload for one trading-calendar query."""

    days: list[str] = field(default_factory=list)
