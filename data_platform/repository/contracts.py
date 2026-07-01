"""Repository contracts for phase-1 market data access."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any


class MarketDataRepository(ABC):
    """Minimal repository interface for phase-1 market data reads."""

    @abstractmethod
    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        """Return historical price rows for a symbol."""

    @abstractmethod
    def fetch_index_components(
        self,
        index_code: str,
        date: str | None = None,
    ) -> Sequence[str]:
        """Return index components for the given date."""

    @abstractmethod
    def fetch_financial_indicators(
        self,
        symbol: str,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        """Return financial indicator rows for a symbol."""

    @abstractmethod
    def fetch_trading_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> Sequence[str]:
        """Return trading dates between the given bounds."""
