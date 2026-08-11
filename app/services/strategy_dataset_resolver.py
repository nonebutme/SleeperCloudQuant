"""Resolve declared strategy datasets into point-in-time bar attachments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.services.strategy_dataset_validation import validate_strategy_data_contract

SUPPORTED_RUNTIME_DATASETS = frozenset({
    "a_share_daily",
    "index_daily",
    "a_share_catalog",
    "trade_calendar",
    "trading_status",
    "corporate_actions",
})


class IndexDatasetReader(Protocol):
    def fetch_index_price_history(
        self,
        index_symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]: ...


class StrategyDatasetResolver:
    """Attach supported governed datasets without changing target-weights-v1."""

    def __init__(self, index_reader: IndexDatasetReader, market_reader: Any | None = None) -> None:
        self._index_reader = index_reader
        self._market_reader = market_reader

    def preview(
        self,
        dataset_id: str,
        *,
        symbol: str = "000001.XSHE",
        start_date: str = "",
        end_date: str = "",
        adjustment: str = "raw",
        limit: int = 100,
    ) -> dict[str, Any]:
        bounded_limit = min(max(int(limit), 1), 200)
        if dataset_id == "a_share_daily" and self._market_reader is not None:
            rows = self._market_reader.fetch_price_history(
                symbol, start_date, end_date, adjustment=adjustment
            )
        elif dataset_id == "index_daily":
            rows = self._index_reader.fetch_index_price_history(
                symbol or "000300.XSHG", start_date=start_date or None, end_date=end_date or None
            )
        elif dataset_id == "a_share_catalog" and self._market_reader is not None:
            item = self._market_reader.fetch_symbol(symbol)
            rows = [item] if item else []
        elif dataset_id == "trade_calendar":
            rows = self._index_reader.fetch_trade_calendar(start_date or None, end_date or None)
        elif dataset_id == "trading_status":
            rows = self._index_reader.fetch_trading_status_history(
                symbol, start_date=start_date or None, end_date=end_date or None
            )
        elif dataset_id == "corporate_actions":
            rows = self._index_reader.fetch_corporate_action_history(
                symbol, start_date=start_date or None, end_date=end_date or None
            )
        else:
            raise RuntimeError(f"dataset preview adapter is unavailable: {dataset_id}")
        normalized = [dict(row) for row in rows[:bounded_limit]]
        return {
            "dataset_id": dataset_id,
            "status": "ready",
            "read_only": True,
            "rows": normalized,
            "row_count": len(normalized),
            "limit": bounded_limit,
        }

    def resolve(
        self,
        source_code: str,
        bars: Sequence[Mapping[str, Any]],
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        validation = validate_strategy_data_contract(source_code)
        if not validation["ok"]:
            raise ValueError(f"strategy dataset requirements are invalid: {validation['issues']}")
        dataset_ids = list(validation["requirements"]["dataset_ids"])
        normalized = [dict(row) for row in bars]
        evidence: list[dict[str, Any]] = []
        for dataset_id in dataset_ids:
            if dataset_id == "a_share_daily":
                for row in normalized:
                    row.setdefault("datasets", {})[dataset_id] = dict(row)
                evidence.append({"dataset_id": dataset_id, "status": "bound", "mode": "base_bars"})
                continue
            if dataset_id == "index_daily":
                self._attach_index_daily(normalized, parameters, evidence)
                continue
            if dataset_id == "a_share_catalog":
                self._attach_catalog(normalized, evidence)
                continue
            if dataset_id == "trade_calendar":
                self._attach_trade_calendar(normalized, evidence)
                continue
            if dataset_id == "trading_status":
                self._attach_trading_status(normalized, evidence)
                continue
            if dataset_id == "corporate_actions":
                self._attach_corporate_actions(normalized, evidence)
                continue
            raise RuntimeError(f"dataset runtime adapter is unavailable: {dataset_id}")
        return {"bars": normalized, "evidence": evidence, "validation": validation}

    def _attach_catalog(self, bars: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        symbol = _bar_symbol(bars)
        item = self._market_reader.fetch_symbol(symbol) if self._market_reader is not None else None
        if item is None:
            raise RuntimeError(f"a_share_catalog has no security-master row for {symbol}")
        for bar in bars:
            bar.setdefault("datasets", {})["a_share_catalog"] = dict(item)
        evidence.append({"dataset_id": "a_share_catalog", "status": "bound", "mode": "security_master", "symbol": symbol, "matched_rows": 1})

    def _attach_trade_calendar(self, bars: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        rows = self._index_reader.fetch_trade_calendar(min(dates) if dates else None, max(dates) if dates else None)
        self._attach_rows_by_date(bars, "trade_calendar", rows, evidence, required=True)

    def _attach_trading_status(self, bars: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        rows = self._index_reader.fetch_trading_status_history(_bar_symbol(bars), min(dates) if dates else None, max(dates) if dates else None)
        self._attach_rows_by_date(bars, "trading_status", rows, evidence, required=True)

    def _attach_corporate_actions(self, bars: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        rows = self._index_reader.fetch_corporate_action_history(_bar_symbol(bars), min(dates) if dates else None, max(dates) if dates else None)
        by_date: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_date.setdefault(_bar_date(row), []).append(dict(row))
        for bar in bars:
            bar.setdefault("datasets", {})["corporate_actions"] = by_date.get(_bar_date(bar), [])
        evidence.append({"dataset_id": "corporate_actions", "status": "bound", "mode": "announced_point_in_time_events", "matched_rows": len(rows), "requested_rows": len(bars)})

    @staticmethod
    def _attach_rows_by_date(
        bars: list[dict[str, Any]],
        dataset_id: str,
        rows: Sequence[Mapping[str, Any]],
        evidence: list[dict[str, Any]],
        *,
        required: bool,
    ) -> None:
        by_date = {_bar_date(row): dict(row) for row in rows if _bar_date(row)}
        matched = 0
        for bar in bars:
            value = by_date.get(_bar_date(bar))
            bar.setdefault("datasets", {})[dataset_id] = value
            matched += value is not None
        evidence.append({"dataset_id": dataset_id, "status": "bound" if matched else "unavailable", "mode": "point_in_time_same_trade_date", "matched_rows": matched, "requested_rows": len(bars)})
        if required and bars and matched < len(bars):
            raise RuntimeError(f"{dataset_id} coverage is incomplete: matched {matched} of {len(bars)} rows")

    def _attach_index_daily(
        self,
        bars: list[dict[str, Any]],
        parameters: Mapping[str, Any],
        evidence: list[dict[str, Any]],
    ) -> None:
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        index_symbol = str(parameters.get("index_symbol") or "000300.XSHG")
        rows = self._index_reader.fetch_index_price_history(
            index_symbol,
            start_date=min(dates) if dates else None,
            end_date=max(dates) if dates else None,
        )
        by_date = {_bar_date(row): dict(row) for row in rows if _bar_date(row)}
        matched = 0
        for bar in bars:
            value = by_date.get(_bar_date(bar))
            bar.setdefault("datasets", {})["index_daily"] = value
            matched += value is not None
        evidence.append(
            {
                "dataset_id": "index_daily",
                "status": "bound" if matched else "unavailable",
                "mode": "point_in_time_same_trade_date",
                "index_symbol": index_symbol,
                "matched_rows": matched,
                "requested_rows": len(bars),
            }
        )
        if bars and not matched:
            raise RuntimeError(f"index_daily has no rows for {index_symbol} in requested window")


def _bar_date(row: Mapping[str, Any]) -> str:
    return str(row.get("date") or row.get("trade_date") or row.get("event_date") or "")[:10]


def _bar_symbol(bars: Sequence[Mapping[str, Any]]) -> str:
    if not bars:
        return ""
    return str(bars[0].get("symbol") or bars[0].get("order_book_id") or "")
