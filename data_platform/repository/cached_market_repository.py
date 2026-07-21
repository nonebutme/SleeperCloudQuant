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
        self._last_source_trace: dict[str, Any] = {}

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
            self._record_source_trace(dataset="price_history", selected_source="cache", reason="cache_hit", row_count=len(cached), cache_key=cache_key)
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
            created_at=_utc_now(),
        )
        self._record_source_trace(dataset="price_history", selected_source="upstream", reason="cache_miss", row_count=len(rows), cache_key=cache_key)
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
        self._store.ensure_schema()
        cache_key = self._build_trading_calendar_cache_key(
            start_date=start_date,
            end_date=end_date,
        )
        cached = self._store.fetch_trading_calendar_cache(cache_key=cache_key)
        if cached is not None:
            self._record_source_trace(dataset="trading_calendar", selected_source="cache", reason="cache_hit", row_count=len(cached), cache_key=cache_key)
            return cached

        days = self._upstream.fetch_trading_calendar(start_date, end_date)
        self._store.upsert_trading_calendar_cache(
            cache_key=cache_key,
            start_date=start_date,
            end_date=end_date,
            days=days,
            created_at=_utc_now(),
        )
        self._record_source_trace(dataset="trading_calendar", selected_source="upstream", reason="cache_miss", row_count=len(days), cache_key=cache_key)
        return days

    def sync_price_history(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        self._store.ensure_schema()
        started_at = _utc_now()
        cache_key = self._build_price_cache_key(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        rows = self._upstream.fetch_price_history(
            symbol,
            start_date=start_date,
            end_date=end_date,
        )
        finished_at = _utc_now()
        self._store.upsert_market_data_cache(
            cache_key=cache_key,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            rows=rows,
            created_at=finished_at,
        )
        stored_bar_count = self._store.upsert_price_bars(
            symbol=symbol,
            rows=rows,
            source="explicit_sync",
            synced_at=finished_at,
        )
        self._store.insert_market_sync_run(
            dataset="price_history",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            status="completed",
            row_count=len(rows),
            cache_key=cache_key,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._record_source_trace(dataset="price_history", selected_source="upstream", reason="explicit_sync", row_count=len(rows), cache_key=cache_key)
        source_trace = self.get_source_trace()
        return {
            "dataset": "price_history",
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "status": "completed",
            "row_count": len(rows),
            "stored_bar_count": stored_bar_count,
            "cache_key": cache_key,
            "started_at": started_at,
            "finished_at": finished_at,
            "source_trace": source_trace,
        }

    def sync_trading_calendar(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        self._store.ensure_schema()
        started_at = _utc_now()
        cache_key = self._build_trading_calendar_cache_key(
            start_date=start_date,
            end_date=end_date,
        )
        days = self._upstream.fetch_trading_calendar(start_date, end_date)
        finished_at = _utc_now()
        self._store.upsert_trading_calendar_cache(
            cache_key=cache_key,
            start_date=start_date,
            end_date=end_date,
            days=days,
            created_at=finished_at,
        )
        self._store.insert_market_sync_run(
            dataset="trading_calendar",
            symbol=None,
            start_date=start_date,
            end_date=end_date,
            status="completed",
            row_count=len(days),
            cache_key=cache_key,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._record_source_trace(dataset="trading_calendar", selected_source="upstream", reason="explicit_sync", row_count=len(days), cache_key=cache_key)
        source_trace = self.get_source_trace()
        return {
            "dataset": "trading_calendar",
            "symbol": None,
            "start_date": start_date,
            "end_date": end_date,
            "status": "completed",
            "row_count": len(days),
            "cache_key": cache_key,
            "started_at": started_at,
            "finished_at": finished_at,
            "source_trace": source_trace,
        }

    def fetch_local_price_bars(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return self._store.fetch_price_bars(symbol=symbol, start_date=start_date, end_date=end_date, limit=limit)

    def get_local_price_bar_status(self, *, symbol: str | None = None) -> dict[str, Any]:
        return dict(self._store.fetch_price_bar_status(symbol=symbol))
    def inspect_local_price_bar_quality(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        return dict(self._store.inspect_price_bar_quality(symbol=symbol, start_date=start_date, end_date=end_date))

    def repair_local_price_bar_gaps(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        quality = self.inspect_local_price_bar_quality(symbol=symbol, start_date=start_date, end_date=end_date)
        repairs = []
        for item in quality.get("repair_plan", []):
            if not isinstance(item, Mapping):
                continue
            repairs.append(
                self.sync_price_history(
                    symbol=str(item.get("symbol") or symbol),
                    start_date=str(item.get("start_date") or start_date),
                    end_date=str(item.get("end_date") or end_date),
                )
            )
        repaired_rows = sum(int(item.get("stored_bar_count") or item.get("row_count") or 0) for item in repairs)
        after = self.inspect_local_price_bar_quality(symbol=symbol, start_date=start_date, end_date=end_date)
        return {
            "dataset": "price_history",
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "status": "completed" if repairs else "no_gaps",
            "repair_count": len(repairs),
            "repaired_rows": repaired_rows,
            "before": quality,
            "after": after,
            "repairs": repairs,
        }
    def get_local_market_data_browser(
        self,
        *,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> dict[str, Any]:
        symbols = [dict(row) for row in self._store.fetch_price_bar_symbols(limit=100)]
        selected_symbol = symbol or (str(symbols[0].get("symbol")) if symbols else "")
        bars = []
        quality: dict[str, Any] = {}
        if selected_symbol:
            bars = list(self.fetch_local_price_bars(symbol=selected_symbol, start_date=start_date, end_date=end_date, limit=limit))
            effective_start = start_date or (bars[0].get("date") if bars else None)
            effective_end = end_date or (bars[-1].get("date") if bars else None)
            if effective_start and effective_end:
                quality = self.inspect_local_price_bar_quality(symbol=selected_symbol, start_date=str(effective_start), end_date=str(effective_end))
        return {
            "dataset": "price_history",
            "symbols": symbols,
            "selected_symbol": selected_symbol,
            "bars": [dict(row) for row in bars],
            "quality": quality,
            "sync_runs": [dict(row) for row in self._store.fetch_market_sync_runs(dataset="price_history", symbol=selected_symbol or None, limit=20)],
        }
    def get_local_price_bar_assets(self, *, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        symbols = [dict(row) for row in self._store.fetch_price_bar_symbols(limit=limit)]
        if symbol:
            symbols = [row for row in symbols if str(row.get("symbol") or "") == symbol]
        assets = [self._build_local_price_bar_asset(row) for row in symbols]
        return {
            "dataset": "price_history",
            "asset_count": len(assets),
            "generated_at": _utc_now(),
            "assets": assets,
            "manifest": {
                "dataset": "price_history",
                "scope": "local_price_bars",
                "version_rule": "sha256(symbol|min_date|max_date|row_count|last_synced_at|source_counts|quality_status)[:16]",
                "storage": "market_price_bars + market_sync_runs",
                "boundaries": [
                    "只读取本地 SQLite 归一化行情表和同步日志",
                    "不触发外部 provider 请求",
                    "不写缓存、不修改行情数据",
                ],
                "verification": [
                    "python scripts/smoke_test_market_data_assets.py",
                    "python scripts/run_formal_verifications.py",
                ],
            },
        }

    def _build_local_price_bar_asset(self, row: Mapping[str, Any]) -> dict[str, Any]:
        symbol = str(row.get("symbol") or "")
        start_date = str(row.get("min_date") or "")
        end_date = str(row.get("max_date") or "")
        row_count = int(row.get("row_count") or 0)
        source_counts = dict(self._store.fetch_price_bar_source_counts(symbol=symbol)) if symbol else {}
        quality: dict[str, Any] = {}
        if symbol and start_date and end_date:
            quality = self.inspect_local_price_bar_quality(symbol=symbol, start_date=start_date, end_date=end_date)
        sync_runs = [dict(item) for item in self._store.fetch_market_sync_runs(dataset="price_history", symbol=symbol or None, limit=5)]
        latest_sync = sync_runs[0] if sync_runs else None
        quality_status = str(quality.get("status") or "unknown")
        version_input = "|".join([
            symbol,
            start_date,
            end_date,
            str(row_count),
            str(row.get("last_synced_at") or ""),
            repr(sorted(source_counts.items())),
            quality_status,
        ])
        data_version = sha256(version_input.encode("utf-8")).hexdigest()[:16]
        coverage_status = "empty" if row_count <= 0 else ("active" if start_date and end_date else "partial")
        return {
            "symbol": symbol,
            "dataset": "price_history",
            "row_count": row_count,
            "start_date": row.get("min_date"),
            "end_date": row.get("max_date"),
            "latest_synced_at": row.get("last_synced_at"),
            "coverage_status": coverage_status,
            "quality_status": quality_status,
            "missing_count": int(quality.get("missing_count") or 0),
            "invalid_count": int(quality.get("invalid_count") or 0),
            "duplicate_count": int(quality.get("duplicate_count") or 0),
            "source_counts": source_counts,
            "latest_sync_run": latest_sync,
            "sync_run_count_sampled": len(sync_runs),
            "data_version": data_version,
            "quality_summary": {
                "expected_count": quality.get("expected_count"),
                "stored_count": quality.get("stored_count"),
                "field_coverage": quality.get("field_coverage", {}),
            },
            "repair_hint": quality.get("repair_plan", []),
            "report_links": {
                "bars": f"/api/market/local-price-bars?symbol={symbol}",
                "quality": f"/api/market/local-price-bars/quality?symbol={symbol}&start_date={start_date}&end_date={end_date}",
                "browser": f"/api/market/data-browser?symbol={symbol}",
            },
        }
    def get_sync_status(self, *, dataset: str) -> dict[str, Any]:
        normalized = _normalize_dataset(dataset)
        latest_run = self._store.fetch_latest_market_sync_run(dataset=normalized)
        cache_status = None
        if latest_run is not None:
            cache_key = latest_run.get("cache_key")
            if cache_key not in (None, ""):
                if normalized == "price_history":
                    cache_status = self._store.fetch_market_data_cache_snapshot(cache_key=str(cache_key))
                elif normalized == "trading_calendar":
                    cache_status = self._store.fetch_trading_calendar_cache_snapshot(cache_key=str(cache_key))
        return {
            "dataset": normalized,
            "latest_run": dict(latest_run) if isinstance(latest_run, Mapping) else None,
            "cache_status": dict(cache_status) if isinstance(cache_status, Mapping) else None,
        }

    def get_source_trace(self) -> dict[str, Any]:
        upstream_trace: dict[str, Any]
        if hasattr(self._upstream, "get_source_trace"):
            upstream_trace = dict(self._upstream.get_source_trace())
        elif hasattr(self._upstream, "provider_status"):
            upstream_trace = {"provider": self._upstream.provider_status()}
        else:
            upstream_trace = {"repository": type(self._upstream).__name__}
        return {
            "repository": type(self).__name__,
            "last_call": dict(self._last_source_trace),
            "upstream": upstream_trace,
            "primary": upstream_trace.get("primary", {}),
            "fallback": upstream_trace.get("fallback", {}),
        }

    def _record_source_trace(self, *, dataset: str, selected_source: str, reason: str, row_count: int, cache_key: str) -> None:
        self._last_source_trace = {
            "dataset": dataset,
            "selected_source": selected_source,
            "reason": reason,
            "row_count": row_count,
            "cache_key": cache_key,
        }

    @staticmethod
    def _build_price_cache_key(
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> str:
        raw = f"price_history|{symbol}|{start_date or ''}|{end_date or ''}"
        return sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_trading_calendar_cache_key(*, start_date: str, end_date: str) -> str:
        raw = f"trading_calendar|{start_date}|{end_date}"
        return sha256(raw.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _normalize_dataset(dataset: str) -> str:
    return str(dataset).strip().lower().replace("-", "_")



