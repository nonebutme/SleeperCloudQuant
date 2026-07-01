"""Service-layer facade for formal market-data queries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from data_platform import MarketDataRepository
from domain.market.models import Bar


class MarketDataService:
    """Expose market-data reads through service-facing domain objects."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def get_price_history(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Bar]:
        rows = self._repository.fetch_price_history(
            symbol,
            start_date=start_date,
            end_date=end_date,
        )
        return [self._to_bar(symbol=symbol, row=row) for row in rows]

    def get_trading_calendar(self, *, start_date: str, end_date: str) -> list[str]:
        return list(self._repository.fetch_trading_calendar(start_date, end_date))

    @staticmethod
    def _to_bar(*, symbol: str, row: dict[str, Any] | Any) -> Bar:
        payload = dict(row)
        return Bar(
            symbol=symbol,
            date=str(payload.get("date") or ""),
            open=float(payload.get("open") or 0.0),
            high=float(payload.get("high") or 0.0),
            low=float(payload.get("low") or 0.0),
            close=float(payload.get("close") or 0.0),
            volume=float(payload.get("volume") or 0.0),
        )
