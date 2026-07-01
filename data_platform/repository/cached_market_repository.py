"""Cache-first repository wrapper for market data reads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from data_platform.repository.contracts import MarketDataRepository
from data_platform.storage.sqlite_metadata_store import SqliteMetadataStore


class CachedMarketDataRepository(MarketDataRepository):
    """Read price history from SQLite cache before hitting the upstream provider."""

    def __init__(
        self,
        upstream: MarketDataRepository,
        store: SqliteMetadataStore,
    ) -> None:
        self._upstream = upstream
        self._store = store

    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        self._store.ensure_schema()
        cache_key = self._build_price_cache_key(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        cached = self._store.fetch_market_data_cache(cache_key=cache_key)
        if cached is not None:
            return cached

        rows = self._upstream.fetch_price_history(
            symbol,
            start_date=start_date,
            end_date=end_date,
        )
        self._store.upsert_market_data_cache(
            cache_key=cache_key,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            rows=rows,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        return rows

    def fetch_index_components(
        self,
        index_code: str,
        date: str | None = None,
    ) -> Sequence[str]:
        return self._upstream.fetch_index_components(index_code, date=date)

    def fetch_financial_indicators(
        self,
        symbol: str,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return self._upstream.fetch_financial_indicators(symbol, report_date=report_date)

    def fetch_trading_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> Sequence[str]:
        return self._upstream.fetch_trading_calendar(start_date, end_date)

    @staticmethod
    def _build_price_cache_key(
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> str:
        raw = f"price_history|{symbol}|{start_date or ''}|{end_date or ''}"
        return sha256(raw.encode("utf-8")).hexdigest()
