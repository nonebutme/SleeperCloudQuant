"""Service-layer facade for formal market-data queries."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from data_platform import MarketDataRepository
from domain.market.models import Bar, MarketCacheStatus, MarketSyncStatus, MarketSyncSummary


CORE_A_SHARE_INDICES = (
    {"index_symbol": "000001", "qualified_symbol": "000001.XSHG", "name": "上证指数", "market": "SSE"},
    {"index_symbol": "399001", "qualified_symbol": "399001.XSHE", "name": "深证成指", "market": "SZSE"},
    {"index_symbol": "899050", "qualified_symbol": "899050.BSE", "name": "北证50", "market": "BSE"},
    {"index_symbol": "000300", "qualified_symbol": "000300.XSHG", "name": "沪深300", "market": "SSE"},
    {"index_symbol": "399006", "qualified_symbol": "399006.XSHE", "name": "创业板指", "market": "SZSE"},
    {"index_symbol": "000688", "qualified_symbol": "000688.XSHG", "name": "科创50", "market": "SSE"},
)


@runtime_checkable
class MarketDataSyncProtocol(Protocol):
    """Optional sync capability implemented by cache-aware repositories."""

    def sync_price_history(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        ...

    def sync_trading_calendar(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        ...

    def get_sync_status(self, *, dataset: str) -> dict[str, Any]:
        ...

    def fetch_local_price_bars(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def get_local_price_bar_status(self, *, symbol: str | None = None) -> dict[str, Any]:
        ...

    def inspect_local_price_bar_quality(self, *, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        ...

    def repair_local_price_bar_gaps(self, *, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        ...

    def get_local_market_data_browser(self, *, symbol: str | None = None, start_date: str | None = None, end_date: str | None = None, limit: int = 120) -> dict[str, Any]:
        ...

    def get_local_price_bar_assets(self, *, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        ...


class MarketDataService:
    """Expose market-data reads through service-facing domain objects."""

    def __init__(
        self,
        repository: MarketDataRepository,
        a_share_repository: Any | None = None,
        governance_repository: Any | None = None,
        panorama_service: Any | None = None,
    ) -> None:
        self._repository = repository
        self._a_share_repository = a_share_repository
        self._governance_repository = governance_repository
        self._panorama_service = panorama_service

    def get_market_panorama(
        self,
        *,
        trade_date: str,
        symbol: str = "",
        asset_type: str = "stock",
    ) -> dict[str, Any]:
        if self._panorama_service is None:
            return {
                "status": "unavailable",
                "requested_trade_date": trade_date,
                "reason": "market_panorama_service_not_configured",
                "datasets": {},
            }
        return dict(
            self._panorama_service.get_panorama(
                trade_date=trade_date,
                symbol=symbol,
                asset_type=asset_type,
            )
        )

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

    def get_a_share_overview(self) -> dict[str, Any]:
        if self._a_share_repository is None:
            return {"status": "unavailable", "read_only": True}
        return dict(self._a_share_repository.get_overview())

    def list_a_share_symbols(
        self,
        *,
        query: str = "",
        market: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if self._a_share_repository is None:
            return {"status": "unavailable", "total": 0, "items": [], "read_only": True}
        return dict(
            self._a_share_repository.list_symbols(
                query=query,
                market=market,
                limit=int(limit),
                offset=int(offset),
            )
        )

    def get_a_share_daily_prices(
        self,
        *,
        symbol: str,
        adjustment: str = "raw",
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        if self._a_share_repository is None:
            return {"status": "unavailable", "symbol": symbol, "total": 0, "rows": [], "read_only": True}
        return dict(
            self._a_share_repository.fetch_daily_prices(
                symbol=symbol,
                adjustment=adjustment,
                start_date=start_date,
                end_date=end_date,
                limit=int(limit),
                offset=int(offset),
            )
        )

    def list_index_symbols(self) -> dict[str, Any]:
        stored_rows = (
            self._governance_repository.list_index_price_assets()
            if self._governance_repository is not None
            and hasattr(self._governance_repository, "list_index_price_assets")
            else []
        )
        stored = {str(row.get("index_symbol")): dict(row) for row in stored_rows}
        items = []
        for definition in CORE_A_SHARE_INDICES:
            coverage = stored.get(definition["index_symbol"], {})
            row_count = int(coverage.get("row_count") or 0)
            items.append({
                **definition,
                **coverage,
                "row_count": row_count,
                "status": "ready" if row_count > 0 else "pending",
            })
        known = {item["index_symbol"] for item in items}
        items.extend(
            {
                **row,
                "qualified_symbol": str(row["index_symbol"]),
                "name": str(row["index_symbol"]),
                "market": "UNKNOWN",
                "status": "ready",
            }
            for row in stored_rows
            if str(row.get("index_symbol")) not in known
        )
        return {
            "status": "ready",
            "source": "canonical_a_share_sqlite",
            "dataset": "market_index_daily_prices",
            "items": items,
        }

    def get_index_daily_prices(
        self,
        *,
        index_symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        if self._governance_repository is None or not hasattr(
            self._governance_repository, "fetch_index_daily_prices"
        ):
            return {
                "status": "unavailable",
                "index_symbol": index_symbol,
                "total": 0,
                "rows": [],
                "read_only": True,
            }
        return dict(self._governance_repository.fetch_index_daily_prices(
            index_symbol=index_symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        ))

    def get_a_share_price_history(
        self,
        *,
        symbol: str,
        adjustment: str = "raw",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return ascending canonical A-share bars for portfolio backtests."""

        if self._governance_repository is not None and hasattr(
            self._governance_repository, "fetch_index_price_history"
        ):
            index_rows = self._governance_repository.fetch_index_price_history(
                symbol,
                start_date=start_date,
                end_date=end_date,
            )
            if index_rows:
                return [dict(row) for row in index_rows]
        if self._a_share_repository is None or not hasattr(self._a_share_repository, "fetch_price_history"):
            return []
        return [
            dict(row)
            for row in self._a_share_repository.fetch_price_history(
                symbol,
                start_date=start_date,
                end_date=end_date,
                adjustment=adjustment,
            )
        ]
    def get_published_data_version(
        self,
        *,
        symbol: str,
        adjustment: str,
        start_date: str,
        end_date: str,
        benchmark: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the immutable canonical release before a backtest starts."""

        if self._governance_repository is None:
            return {"status": "unsupported", "reason": "governance_repository_not_configured"}
        return dict(
            self._governance_repository.resolve_published_data_version(
                symbol=symbol,
                adjustment=adjustment,
                start_date=start_date,
                end_date=end_date,
                benchmark=benchmark,
            )
        )

    def get_index_components(
        self,
        *,
        index_code: str,
        date: str | None = None,
    ) -> list[str]:
        return list(self._repository.fetch_index_components(index_code, date=date))

    def get_trading_calendar(self, *, start_date: str, end_date: str) -> list[str]:
        return list(self._repository.fetch_trading_calendar(start_date, end_date))

    def sync_price_history(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> MarketSyncSummary:
        if isinstance(self._repository, MarketDataSyncProtocol):
            payload = self._repository.sync_price_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            return _to_sync_summary(payload)

        rows = self._repository.fetch_price_history(
            symbol,
            start_date=start_date,
            end_date=end_date,
        )
        return _build_local_sync_summary(
            dataset="price_history",
            row_count=len(rows),
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def sync_trading_calendar(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> MarketSyncSummary:
        if isinstance(self._repository, MarketDataSyncProtocol):
            payload = self._repository.sync_trading_calendar(
                start_date=start_date,
                end_date=end_date,
            )
            return _to_sync_summary(payload)

        days = self._repository.fetch_trading_calendar(start_date, end_date)
        return _build_local_sync_summary(
            dataset="trading_calendar",
            row_count=len(days),
            start_date=start_date,
            end_date=end_date,
        )

    def get_local_price_bars(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        if isinstance(self._repository, MarketDataSyncProtocol):
            rows = self._repository.fetch_local_price_bars(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
            return [self._to_bar(symbol=symbol, row=row) for row in rows]
        return []

    def get_local_price_bar_status(self, *, symbol: str | None = None) -> dict[str, Any]:
        if isinstance(self._repository, MarketDataSyncProtocol):
            return dict(self._repository.get_local_price_bar_status(symbol=symbol))
        return {"row_count": 0, "min_date": None, "max_date": None, "last_synced_at": None}
    def inspect_local_price_bar_quality(self, *, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        if isinstance(self._repository, MarketDataSyncProtocol):
            return dict(self._repository.inspect_local_price_bar_quality(symbol=symbol, start_date=start_date, end_date=end_date))
        return {"dataset": "price_history", "symbol": symbol, "start_date": start_date, "end_date": end_date, "status": "unsupported", "missing_dates": [], "invalid_rows": []}

    def repair_local_price_bar_gaps(self, *, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        if isinstance(self._repository, MarketDataSyncProtocol):
            return dict(self._repository.repair_local_price_bar_gaps(symbol=symbol, start_date=start_date, end_date=end_date))
        return {"dataset": "price_history", "symbol": symbol, "start_date": start_date, "end_date": end_date, "status": "unsupported", "repair_count": 0, "repaired_rows": 0}
    def get_local_market_data_browser(
        self,
        *,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> dict[str, Any]:
        if isinstance(self._repository, MarketDataSyncProtocol):
            return dict(self._repository.get_local_market_data_browser(symbol=symbol, start_date=start_date, end_date=end_date, limit=limit))
        return {"dataset": "price_history", "symbols": [], "selected_symbol": symbol or "", "bars": [], "quality": {}, "sync_runs": []}
    def get_local_price_bar_assets(self, *, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        if isinstance(self._repository, MarketDataSyncProtocol):
            return dict(self._repository.get_local_price_bar_assets(symbol=symbol, limit=limit))
        return {"dataset": "price_history", "asset_count": 0, "generated_at": _utc_now(), "assets": [], "manifest": {}}
    def get_sync_status(self, *, dataset: str) -> MarketSyncStatus:
        normalized = _normalize_dataset(dataset)
        if isinstance(self._repository, MarketDataSyncProtocol):
            payload = self._repository.get_sync_status(dataset=normalized)
            return _to_sync_status(payload)
        return MarketSyncStatus(
            dataset=normalized,
            latest_run=None,
            cache_status=None,
        )

    def get_source_trace(self) -> dict[str, Any]:
        if hasattr(self._repository, "get_source_trace"):
            return dict(self._repository.get_source_trace())
        if hasattr(self._repository, "provider_status"):
            return {"repository": type(self._repository).__name__, "provider": self._repository.provider_status()}
        return {"repository": type(self._repository).__name__}

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


def _to_sync_summary(payload: Mapping[str, Any]) -> MarketSyncSummary:
    return MarketSyncSummary(
        dataset=str(payload.get("dataset") or "market_data"),
        status=str(payload.get("status") or "completed"),
        started_at=str(payload.get("started_at") or ""),
        finished_at=str(payload.get("finished_at") or payload.get("started_at") or ""),
        row_count=int(payload.get("row_count") or 0),
        symbol=_optional_str(payload.get("symbol")),
        start_date=_optional_str(payload.get("start_date")),
        end_date=_optional_str(payload.get("end_date")),
        cache_key=_optional_str(payload.get("cache_key")),
        source_trace=dict(payload.get("source_trace")) if isinstance(payload.get("source_trace"), Mapping) else {},
    )


def _to_sync_status(payload: Mapping[str, Any]) -> MarketSyncStatus:
    latest_run_payload = payload.get("latest_run")
    cache_status_payload = payload.get("cache_status")
    return MarketSyncStatus(
        dataset=str(payload.get("dataset") or "market_data"),
        latest_run=_to_sync_summary(latest_run_payload) if isinstance(latest_run_payload, Mapping) else None,
        cache_status=_to_cache_status(cache_status_payload) if isinstance(cache_status_payload, Mapping) else None,
    )


def _to_cache_status(payload: Mapping[str, Any]) -> MarketCacheStatus:
    return MarketCacheStatus(
        dataset=str(payload.get("dataset") or "market_data"),
        cache_key=_optional_str(payload.get("cache_key")),
        row_count=int(payload.get("row_count") or 0),
        created_at=_optional_str(payload.get("created_at")),
        symbol=_optional_str(payload.get("symbol")),
        start_date=_optional_str(payload.get("start_date")),
        end_date=_optional_str(payload.get("end_date")),
    )


def _normalize_dataset(dataset: str) -> str:
    return str(dataset).strip().lower().replace("-", "_")


def _build_local_sync_summary(
    *,
    dataset: str,
    row_count: int,
    symbol: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> MarketSyncSummary:
    finished_at = _utc_now()
    return MarketSyncSummary(
        dataset=dataset,
        status="completed",
        started_at=finished_at,
        finished_at=finished_at,
        row_count=row_count,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        cache_key=None,
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
