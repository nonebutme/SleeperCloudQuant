"""Replay service implementation for phase-1 reporting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from .run_results_reader import BacktestRunDetail


class ReplayRepository(Protocol):
    """Minimal repository protocol needed by the replay service."""

    def fetch_price_history(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        """Return historical price rows for replay rendering."""


@dataclass(frozen=True, slots=True)
class BacktestReplayDetail:
    """Replay dataset for one traded symbol."""

    symbol: str
    start_date: str
    end_date: str
    price_rows: Sequence[Mapping[str, Any]]
    trade_rows: Sequence[Mapping[str, Any]]


class ReplayService:
    """Compose K-line style replay data from result detail and market history."""

    def __init__(self, repository: ReplayRepository) -> None:
        self._repository = repository

    def list_replay_symbols(self, detail: BacktestRunDetail) -> list[str]:
        """Return sorted symbols that can be replayed for the current run."""

        symbols = {
            str(row.get("order_book_id") or "").strip()
            for row in [*detail.trades, *detail.positions]
            if str(row.get("order_book_id") or "").strip()
        }
        if not symbols and detail.run.get("universe"):
            symbols.add(str(detail.run["universe"]))
        return sorted(symbols)

    def build_trade_replay(
        self,
        detail: BacktestRunDetail,
        *,
        symbol: str,
        lookback_days: int = 20,
        lookahead_days: int = 20,
    ) -> BacktestReplayDetail:
        """Return normalized replay rows for one traded symbol."""

        relevant_trades = [
            self._normalize_trade_row(row)
            for row in detail.trades
            if str(row.get("order_book_id") or "") == symbol
        ]
        replay_start = self._resolve_start_date(
            detail=detail,
            trades=relevant_trades,
            lookback_days=lookback_days,
        )
        replay_end = self._resolve_end_date(
            detail=detail,
            trades=relevant_trades,
            lookahead_days=lookahead_days,
        )
        price_rows = self._normalize_price_rows(
            self._repository.fetch_price_history(
                symbol,
                start_date=replay_start,
                end_date=replay_end,
            )
        )
        return BacktestReplayDetail(
            symbol=symbol,
            start_date=replay_start,
            end_date=replay_end,
            price_rows=price_rows,
            trade_rows=relevant_trades,
        )

    def _resolve_start_date(
        self,
        *,
        detail: BacktestRunDetail,
        trades: Sequence[Mapping[str, Any]],
        lookback_days: int,
    ) -> str:
        trade_dates = [_parse_date(str(row.get("trade_time") or "")) for row in trades]
        valid_trade_dates = [value for value in trade_dates if value is not None]
        if valid_trade_dates:
            return (min(valid_trade_dates) - timedelta(days=lookback_days)).isoformat()
        return str(detail.run.get("start_date") or "")

    def _resolve_end_date(
        self,
        *,
        detail: BacktestRunDetail,
        trades: Sequence[Mapping[str, Any]],
        lookahead_days: int,
    ) -> str:
        trade_dates = [_parse_date(str(row.get("trade_time") or "")) for row in trades]
        valid_trade_dates = [value for value in trade_dates if value is not None]
        if valid_trade_dates:
            return (max(valid_trade_dates) + timedelta(days=lookahead_days)).isoformat()
        return str(detail.run.get("end_date") or "")

    @staticmethod
    def _normalize_trade_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
        trade_time = str(row.get("trade_time") or "")
        return {
            "trade_time": trade_time,
            "trade_date": trade_time[:10],
            "order_book_id": row.get("order_book_id"),
            "side": row.get("side"),
            "price": _coerce_float(row.get("price")),
            "quantity": _coerce_float(row.get("quantity")),
            "amount": _coerce_float(row.get("amount")),
        }

    @staticmethod
    def _normalize_price_rows(
        rows: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        normalized_rows: list[Mapping[str, Any]] = []
        for row in rows:
            price_date = _pick_price_date(row)
            if not price_date:
                continue
            close = _coerce_float(row.get("close"))
            normalized_rows.append(
                {
                    "date": price_date,
                    "open": _coerce_float(row.get("open"), fallback=close),
                    "high": _coerce_float(row.get("high"), fallback=close),
                    "low": _coerce_float(row.get("low"), fallback=close),
                    "close": close,
                    "volume": _coerce_float(row.get("volume")),
                }
            )
        return sorted(normalized_rows, key=lambda item: item["date"])


def _pick_price_date(row: Mapping[str, Any]) -> str:
    for key in ("date", "datetime", "time"):
        value = row.get(key)
        if value in (None, ""):
            continue
        return str(value)[:10]
    return ""


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _coerce_float(value: Any, *, fallback: float = 0.0) -> float:
    if value in (None, ""):
        return fallback
    return float(value)
