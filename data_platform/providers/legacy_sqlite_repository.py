"""Read-only market-data repository backed by a legacy SQLite cache."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from data_platform.providers.ricequant_repository import normalize_price_history_rows, normalize_trading_calendar
from data_platform.repository.contracts import MarketDataRepository


class LegacySQLiteMarketDataRepository(MarketDataRepository):
    """Read price history from SleeperCloudQuant-old style market_data_cache."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    @property
    def database_path(self) -> Path:
        return self._database_path

    def is_available(self) -> bool:
        return self._database_path.is_file()

    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        if not self.is_available():
            return []

        cache_row = self._fetch_best_cache_row(symbol=symbol, start_date=start_date, end_date=end_date)
        if cache_row is None:
            return []

        rows = _decode_rows(cache_row["rows_json"])
        return [
            row
            for row in normalize_price_history_rows(rows)
            if _within_date_window(str(row.get("date") or ""), start_date=start_date, end_date=end_date)
        ]

    def fetch_index_components(
        self,
        index_code: str,
        date: str | None = None,
    ) -> Sequence[str]:
        return []

    def fetch_financial_indicators(
        self,
        symbol: str,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return []

    def fetch_trading_calendar(self, start_date: str, end_date: str) -> Sequence[str]:
        if not self.is_available():
            return []

        days: set[str] = set()
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT rows_json
                FROM market_data_cache
                WHERE start_date <= ? AND end_date >= ?
                ORDER BY end_date DESC, start_date ASC
                LIMIT 20
                """,
                (end_date, start_date),
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            for item in _decode_rows(row["rows_json"]):
                day = str(item.get("date") or "")[:10]
                if _within_date_window(day, start_date=start_date, end_date=end_date):
                    days.add(day)
        return normalize_trading_calendar(sorted(days))

    def _fetch_best_cache_row(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> Mapping[str, Any] | None:
        start_bound = start_date or "0000-01-01"
        end_bound = end_date or "9999-12-31"
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT symbol, start_date, end_date, rows_json
                FROM market_data_cache
                WHERE symbol = ? AND start_date <= ? AND end_date >= ?
                ORDER BY end_date DESC, start_date ASC
                LIMIT 1
                """,
                (symbol, start_bound, end_bound),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def _decode_rows(raw_json: str) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, Mapping)]


def _within_date_window(day: str, *, start_date: str | None, end_date: str | None) -> bool:
    if not day:
        return False
    if start_date and day < start_date:
        return False
    if end_date and day > end_date:
        return False
    return True

