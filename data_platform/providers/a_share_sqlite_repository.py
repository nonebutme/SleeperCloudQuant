"""Read-only access to the accepted legacy A-share SQLite source."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date
from pathlib import Path
from typing import Any

TABLES = {"raw": "stock_hist", "qfq": "stock_hist_qfq", "hfq": "stock_hist_hfq"}
DATE = "\u65e5\u671f"
SYMBOL = "\u80a1\u7968\u4ee3\u7801"
OPEN = "\u5f00\u76d8"
CLOSE = "\u6536\u76d8"
HIGH = "\u6700\u9ad8"
LOW = "\u6700\u4f4e"
VOLUME = "\u6210\u4ea4\u91cf"
AMOUNT = "\u6210\u4ea4\u989d"
AMPLITUDE = "\u632f\u5e45"
CHANGE_PCT = "\u6da8\u8dcc\u5e45"
CHANGE_AMOUNT = "\u6da8\u8dcc\u989d"
TURNOVER_RATE = "\u6362\u624b\u7387"


class AShareSQLiteRepository:
    """Query stockmarket.db with mode=ro and expose normalized A-share records."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._overview: dict[str, Any] | None = None
        self._catalog: list[dict[str, Any]] | None = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return self.database_path.is_file()

    def get_overview(self) -> dict[str, Any]:
        if not self.is_available():
            return self._unavailable()
        with self._lock:
            if self._overview is None:
                self._overview = self._build_overview()
            return dict(self._overview)

    def list_symbols(
        self,
        *,
        query: str = "",
        market: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        needle = str(query or "").strip().lower()
        market_filter = str(market or "").strip().upper()
        items = [
            item
            for item in self._get_catalog()
            if (not needle or needle in item["symbol"].lower() or needle in item["name"].lower())
            and (not market_filter or item["market"] == market_filter)
        ]
        page_limit = max(1, min(int(limit), 500))
        page_offset = max(0, int(offset))
        return {
            "status": "ready" if self.is_available() else "unavailable",
            "source": "legacy_stockmarket_sqlite",
            "read_only": True,
            "query": needle,
            "market": market_filter,
            "total": len(items),
            "limit": page_limit,
            "offset": page_offset,
            "items": items[page_offset : page_offset + page_limit],
        }

    def fetch_daily_prices(
        self,
        *,
        symbol: str,
        adjustment: str = "raw",
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        code = _normalize_symbol(symbol)
        mode = _normalize_adjustment(adjustment)
        page_limit = max(1, min(int(limit), 2000))
        page_offset = max(0, int(offset))
        if not self.is_available():
            return {**self._unavailable(), "symbol": code, "adjustment": mode, "total": 0, "rows": []}
        filters = [f'"{SYMBOL}" = ?']
        values: list[Any] = [code]
        if start_date:
            filters.append(f'"{DATE}" >= ?')
            values.append(str(start_date))
        if end_date:
            filters.append(f'"{DATE}" <= ?')
            values.append(str(end_date))
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT rowid AS source_rowid, "{DATE}" AS trade_date,
                       "{OPEN}" AS open_price, "{CLOSE}" AS close_price,
                       "{HIGH}" AS high_price, "{LOW}" AS low_price,
                       "{VOLUME}" AS volume, "{AMOUNT}" AS amount,
                       "{AMPLITUDE}" AS amplitude, "{CHANGE_PCT}" AS change_pct,
                       "{CHANGE_AMOUNT}" AS change_amount, "{TURNOVER_RATE}" AS turnover_rate
                FROM "{TABLES[mode]}"
                WHERE {' AND '.join(filters)}
                ORDER BY "{DATE}" ASC, rowid ASC
                """,
                tuple(values),
            ).fetchall()
        finally:
            connection.close()
        by_date = {str(row["trade_date"]): row for row in rows}
        normalized = [_daily_payload(by_date[key]) for key in sorted(by_date, reverse=True)]
        return {
            "status": "ready",
            "source": "legacy_stockmarket_sqlite",
            "provider": "akshare",
            "read_only": True,
            "symbol": code,
            "market": _market(code),
            "adjustment": mode,
            "start_date": start_date,
            "end_date": end_date,
            "total": len(normalized),
            "duplicate_rows_removed": len(rows) - len(normalized),
            "limit": page_limit,
            "offset": page_offset,
            "rows": normalized[page_offset : page_offset + page_limit],
        }

    def _build_overview(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            current_count = int(connection.execute("SELECT COUNT(*) FROM stock_list").fetchone()[0])
            current_duplicates = int(
                connection.execute("SELECT COUNT(*) - COUNT(DISTINCT code) FROM stock_list").fetchone()[0]
            )
            adjustments = {mode: self._table_overview(connection, table) for mode, table in TABLES.items()}
        finally:
            connection.close()
        raw = adjustments["raw"]
        return {
            "status": "ready",
            "source": "legacy_stockmarket_sqlite",
            "provider": "akshare",
            "database_path": str(self.database_path.resolve()),
            "database_size_bytes": self.database_path.stat().st_size,
            "read_only": True,
            "current_symbol_count": current_count,
            "current_symbol_duplicate_count": current_duplicates,
            "history_symbol_count": raw["symbol_count"],
            "history_only_symbol_count": max(0, raw["symbol_count"] - current_count),
            "markets": ["SSE", "SZSE", "BSE"],
            "adjustments": adjustments,
            "acceptance_scope": {
                "frequency": "daily",
                "start_date": raw["min_date"],
                "end_date": raw["max_date"],
                "includes_historical_symbols": True,
            },
        }

    def _table_overview(self, connection: sqlite3.Connection, table: str) -> dict[str, Any]:
        row = connection.execute(
            f"""
            SELECT COUNT(*) AS row_count, COUNT(DISTINCT "{SYMBOL}") AS symbol_count,
                   MIN("{DATE}") AS min_date, MAX("{DATE}") AS max_date,
                   COUNT(*) - COUNT(DISTINCT "{SYMBOL}" || char(31) || "{DATE}") AS duplicate_row_count
            FROM "{table}"
            """
        ).fetchone()
        max_date = str(row["max_date"] or "")
        stale_days = (date.today() - date.fromisoformat(max_date)).days if max_date else None
        duplicates = int(row["duplicate_row_count"] or 0)
        return {
            "table": table,
            "row_count": int(row["row_count"] or 0),
            "symbol_count": int(row["symbol_count"] or 0),
            "min_date": row["min_date"],
            "max_date": row["max_date"],
            "duplicate_row_count": duplicates,
            "stale_days": stale_days,
            "quality_status": "passed" if duplicates == 0 and stale_days is not None and stale_days <= 7 else "needs_attention",
        }

    def _get_catalog(self) -> list[dict[str, Any]]:
        if not self.is_available():
            return []
        with self._lock:
            if self._catalog is not None:
                return list(self._catalog)
            connection = self._connect()
            try:
                current_rows = connection.execute("SELECT code, name FROM stock_list ORDER BY code").fetchall()
                history_rows = connection.execute(
                    f'SELECT DISTINCT "{SYMBOL}" AS symbol FROM stock_hist ORDER BY "{SYMBOL}"'
                ).fetchall()
            finally:
                connection.close()
            current = {str(row["code"]).zfill(6): str(row["name"] or "") for row in current_rows}
            codes = sorted(set(current) | {str(row["symbol"]).zfill(6) for row in history_rows})
            self._catalog = [
                {
                    "symbol": code,
                    "rqalpha_symbol": _rqalpha_symbol(code),
                    "name": current.get(code, ""),
                    "market": _market(code),
                    "listing_status": "current" if code in current else "historical_or_unlisted",
                }
                for code in codes
            ]
            return list(self._catalog)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.database_path.resolve().as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _unavailable(self) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "source": "legacy_stockmarket_sqlite",
            "database_path": str(self.database_path),
            "read_only": True,
        }


def _normalize_adjustment(value: str) -> str:
    mode = str(value or "raw").strip().lower()
    if mode not in TABLES:
        raise ValueError(f"unsupported adjustment: {mode}")
    return mode


def _normalize_symbol(value: str) -> str:
    code = str(value or "").strip().upper().split(".", 1)[0]
    if not code.isdigit() or len(code) > 6:
        raise ValueError("A-share symbol must be a numeric code with at most 6 digits")
    return code.zfill(6)


def _market(code: str) -> str:
    if code.startswith(("4", "8", "9")):
        return "BSE"
    return "SSE" if code.startswith("6") else "SZSE"


def _rqalpha_symbol(code: str) -> str:
    suffix = {"SSE": "XSHG", "SZSE": "XSHE", "BSE": "XBSE"}[_market(code)]
    return f"{code}.{suffix}"


def _daily_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "date": str(row["trade_date"]),
        "open": _number(row["open_price"]),
        "high": _number(row["high_price"]),
        "low": _number(row["low_price"]),
        "close": _number(row["close_price"]),
        "volume": _number(row["volume"]),
        "amount": _number(row["amount"]),
        "amplitude": _number(row["amplitude"]),
        "change_pct": _number(row["change_pct"]),
        "change_amount": _number(row["change_amount"]),
        "turnover_rate": _number(row["turnover_rate"]),
        "source_rowid": int(row["source_rowid"]),
        "source": "legacy_stockmarket_sqlite",
    }


def _number(value: Any) -> float | None:
    return None if value in (None, "") else float(value)
