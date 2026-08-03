"""Canonical local SQLite storage for normalized A-share daily data."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from data_platform.providers.a_share_sqlite_repository import (
    AMOUNT, AMPLITUDE, CHANGE_AMOUNT, CHANGE_PCT, CLOSE, DATE, HIGH, LOW, OPEN,
    SYMBOL, TABLES, TURNOVER_RATE, VOLUME, _market, _normalize_adjustment,
    _normalize_symbol, _rqalpha_symbol,
)


class AShareMarketStore:
    """Read and update the project-owned, deduplicated A-share database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def ensure_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = NORMAL;
                CREATE TABLE IF NOT EXISTS market_symbols (
                    symbol TEXT PRIMARY KEY,
                    rqalpha_symbol TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    market TEXT NOT NULL,
                    listing_status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_daily_prices (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    adjustment TEXT NOT NULL CHECK (adjustment IN ('raw', 'qfq', 'hfq')),
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    amount REAL,
                    amplitude REAL,
                    change_pct REAL,
                    change_amount REAL,
                    turnover_rate REAL,
                    source TEXT NOT NULL,
                    source_rowid INTEGER,
                    imported_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, trade_date, adjustment)
                );
                CREATE INDEX IF NOT EXISTS idx_market_daily_date_adjustment
                    ON market_daily_prices (trade_date, adjustment);
                CREATE TABLE IF NOT EXISTS market_sync_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_sync_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    symbol TEXT,
                    adjustment TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    rows_written INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                );
                """
            )

    def is_available(self) -> bool:
        if not self.database_path.is_file():
            return False
        try:
            with closing(self._connect(read_only=True)) as connection:
                return connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_daily_prices'"
                ).fetchone() is not None
        except sqlite3.Error:
            return False

    def has_daily_data(self) -> bool:
        if not self.is_available():
            return False
        with closing(self._connect(read_only=True)) as connection:
            return connection.execute("SELECT 1 FROM market_daily_prices LIMIT 1").fetchone() is not None

    def upsert_symbols(self, rows: Iterable[Mapping[str, Any]]) -> int:
        now = _utc_now()
        payload = []
        for row in rows:
            symbol = _normalize_symbol(str(row.get("symbol") or row.get("code") or ""))
            payload.append((
                symbol, _rqalpha_symbol(symbol), str(row.get("name") or ""),
                _market(symbol), str(row.get("listing_status") or "current"),
                str(row.get("source") or "akshare"), now,
            ))
        if not payload:
            return 0
        self.ensure_schema()
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                INSERT INTO market_symbols
                    (symbol, rqalpha_symbol, name, market, listing_status, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    rqalpha_symbol=excluded.rqalpha_symbol,
                    name=CASE WHEN excluded.name <> '' THEN excluded.name ELSE market_symbols.name END,
                    market=excluded.market,
                    listing_status=excluded.listing_status,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                payload,
            )
        return len(payload)

    def replace_current_symbols(self, rows: Iterable[Mapping[str, Any]]) -> int:
        """Replace the current listing set while preserving historical catalog rows."""
        now = _utc_now()
        payload = []
        for row in rows:
            symbol = _normalize_symbol(str(row.get("symbol") or row.get("code") or ""))
            payload.append((
                symbol, _rqalpha_symbol(symbol), str(row.get("name") or ""),
                _market(symbol), "current", str(row.get("source") or "akshare"), now,
            ))
        if not payload:
            return 0
        self.ensure_schema()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE market_symbols
                   SET listing_status='historical_or_unlisted', updated_at=?
                   WHERE listing_status='current'""",
                (now,),
            )
            connection.executemany(
                """
                INSERT INTO market_symbols
                    (symbol, rqalpha_symbol, name, market, listing_status, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    rqalpha_symbol=excluded.rqalpha_symbol,
                    name=CASE WHEN excluded.name <> '' THEN excluded.name ELSE market_symbols.name END,
                    market=excluded.market,
                    listing_status='current',
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                payload,
            )
        return len(payload)

    def list_sync_targets(
        self,
        *,
        adjustment: str,
        end_date: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List current symbols whose selected adjustment is behind end_date."""
        mode = _normalize_adjustment(adjustment)
        sql = """
            SELECT symbol, name, market, latest_date
            FROM (
                SELECT s.symbol, s.name, s.market,
                       (SELECT MAX(p.trade_date)
                        FROM market_daily_prices p
                        WHERE p.symbol=s.symbol AND p.adjustment=?) AS latest_date
                FROM market_symbols s
                WHERE s.listing_status='current'
            )
            WHERE latest_date IS NULL OR latest_date < ?
            ORDER BY symbol
        """
        values: list[Any] = [mode, str(end_date)]
        if limit is not None:
            sql += " LIMIT ?"
            values.append(max(1, int(limit)))
        with closing(self._connect(read_only=True)) as connection:
            return [dict(row) for row in connection.execute(sql, values).fetchall()]
    def upsert_daily_prices(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        adjustment: str,
        source: str,
    ) -> int:
        mode = _normalize_adjustment(adjustment)
        now = _utc_now()
        payload = []
        for row in rows:
            payload.append((
                _normalize_symbol(str(row.get("symbol") or "")),
                str(row.get("date") or row.get("trade_date") or ""),
                mode, _number(row.get("open")), _number(row.get("high")),
                _number(row.get("low")), _number(row.get("close")),
                _number(row.get("volume")), _number(row.get("amount")),
                _number(row.get("amplitude")), _number(row.get("change_pct")),
                _number(row.get("change_amount")), _number(row.get("turnover_rate")),
                source, row.get("source_rowid"), now,
            ))
        if not payload:
            return 0
        self.ensure_schema()
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                INSERT INTO market_daily_prices
                    (symbol, trade_date, adjustment, open, high, low, close, volume, amount,
                     amplitude, change_pct, change_amount, turnover_rate, source, source_rowid, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trade_date, adjustment) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                    volume=excluded.volume, amount=excluded.amount, amplitude=excluded.amplitude,
                    change_pct=excluded.change_pct, change_amount=excluded.change_amount,
                    turnover_rate=excluded.turnover_rate, source=excluded.source,
                    source_rowid=excluded.source_rowid, imported_at=excluded.imported_at
                """,
                payload,
            )
        return len(payload)

    def import_legacy(
        self,
        source_path: str | Path,
        *,
        adjustments: Iterable[str] = ("raw", "qfq", "hfq"),
        batch_size: int = 20_000,
        max_batches: int | None = None,
        progress: Any | None = None,
    ) -> dict[str, Any]:
        """Resume a rowid-ordered import; later duplicate rows replace earlier rows."""
        self.ensure_schema()
        source = Path(source_path)
        source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
        result: dict[str, Any] = {"source": str(source.resolve()), "adjustments": {}}
        with closing(sqlite3.connect(source_uri, uri=True)) as legacy:
            legacy.row_factory = sqlite3.Row
            legacy.execute("PRAGMA query_only = ON")
            current = legacy.execute("SELECT code, name FROM stock_list ORDER BY code").fetchall()
            current_codes = {str(row["code"]).zfill(6) for row in current}
            self.upsert_symbols(
                {"symbol": row["code"], "name": row["name"], "listing_status": "current",
                 "source": "legacy_stockmarket_sqlite"}
                for row in current
            )
            for mode_value in adjustments:
                mode = _normalize_adjustment(mode_value)
                table = TABLES[mode]
                checkpoint_key = f"legacy_migration:{source.resolve()}:{mode}:rowid"
                checkpoint = int(self._get_state(checkpoint_key) or 0)
                batches = 0
                read_rows = 0
                while max_batches is None or batches < max_batches:
                    rows = legacy.execute(
                        f"""
                        SELECT rowid AS source_rowid, "{SYMBOL}" AS symbol, "{DATE}" AS trade_date,
                               "{OPEN}" AS open_price, "{HIGH}" AS high_price, "{LOW}" AS low_price,
                               "{CLOSE}" AS close_price, "{VOLUME}" AS volume, "{AMOUNT}" AS amount,
                               "{AMPLITUDE}" AS amplitude, "{CHANGE_PCT}" AS change_pct,
                               "{CHANGE_AMOUNT}" AS change_amount, "{TURNOVER_RATE}" AS turnover_rate
                        FROM "{table}" WHERE rowid > ? ORDER BY rowid LIMIT ?
                        """,
                        (checkpoint, max(1, int(batch_size))),
                    ).fetchall()
                    if not rows:
                        break
                    normalized = [
                        {
                            "symbol": row["symbol"], "date": row["trade_date"],
                            "open": row["open_price"], "high": row["high_price"],
                            "low": row["low_price"], "close": row["close_price"],
                            "volume": row["volume"], "amount": row["amount"],
                            "amplitude": row["amplitude"], "change_pct": row["change_pct"],
                            "change_amount": row["change_amount"],
                            "turnover_rate": row["turnover_rate"],
                            "source_rowid": row["source_rowid"],
                        }
                        for row in rows
                    ]
                    self.upsert_daily_prices(
                        normalized, adjustment=mode, source="legacy_stockmarket_sqlite"
                    )
                    checkpoint = int(rows[-1]["source_rowid"])
                    self._set_state(checkpoint_key, str(checkpoint))
                    read_rows += len(rows)
                    batches += 1
                    if progress is not None:
                        progress(mode, read_rows, checkpoint)
                history_codes = {
                    str(row[0]).zfill(6)
                    for row in legacy.execute(f'SELECT DISTINCT "{SYMBOL}" FROM "{table}"')
                }
                self.upsert_symbols(
                    {"symbol": code,
                     "listing_status": "current" if code in current_codes else "historical_or_unlisted",
                     "source": "legacy_stockmarket_sqlite"}
                    for code in history_codes
                )
                result["adjustments"][mode] = {
                    "rows_read": read_rows,
                    "last_source_rowid": checkpoint,
                    "completed": not legacy.execute(
                        f'SELECT 1 FROM "{table}" WHERE rowid > ? LIMIT 1', (checkpoint,)
                    ).fetchone(),
                }
        return result

    def get_overview(self) -> dict[str, Any]:
        if not self.is_available():
            return {
                "status": "unavailable",
                "source": "canonical_a_share_sqlite",
                "read_only": False,
            }
        with closing(self._connect(read_only=True)) as connection:
            catalog_symbol_count = int(connection.execute(
                "SELECT COUNT(*) FROM market_symbols"
            ).fetchone()[0])
            current_symbol_count = int(connection.execute(
                "SELECT COUNT(*) FROM market_symbols WHERE listing_status='current'"
            ).fetchone()[0])
            historical_catalog_count = catalog_symbol_count - current_symbol_count

            published_version = None
            published_members: dict[str, sqlite3.Row] = {}
            has_versions = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='data_versions'
                """
            ).fetchone()
            if has_versions:
                published_version = connection.execute(
                    """
                    SELECT data_version_id, as_of_trade_date, quality_report_id
                    FROM data_versions WHERE status='published'
                    ORDER BY as_of_trade_date DESC, published_at DESC LIMIT 1
                    """
                ).fetchone()
                if published_version:
                    published_members = {
                        str(row["adjustment"]): row
                        for row in connection.execute(
                            """
                            SELECT adjustment, row_count, symbol_count,
                                   min_date, max_date, quality_status
                            FROM data_version_members
                            WHERE data_version_id=?
                              AND dataset='market_daily_prices'
                            """,
                            (published_version["data_version_id"],),
                        ).fetchall()
                    }

            raw_member = published_members.get("raw")
            history_count = (
                int(raw_member["symbol_count"] or 0)
                if raw_member is not None
                else int(connection.execute(
                    """
                    SELECT COUNT(DISTINCT symbol) FROM market_daily_prices
                    WHERE adjustment='raw'
                    """
                ).fetchone()[0])
            )
            adjustments = {}
            for mode in TABLES:
                member = published_members.get(mode)
                observed = connection.execute(
                    """
                    SELECT trade_date FROM market_daily_prices
                    WHERE adjustment=? ORDER BY trade_date DESC LIMIT 1
                    """,
                    (mode,),
                ).fetchone()
                observed_max_date = str(observed["trade_date"] or "") if observed else ""
                if member is not None:
                    row_count = int(member["row_count"] or 0)
                    symbol_count = int(member["symbol_count"] or 0)
                    min_date = member["min_date"]
                    max_date = str(member["max_date"] or "")
                    member_quality = str(member["quality_status"] or "")
                else:
                    row = connection.execute(
                        """
                        SELECT COUNT(*) AS rows, COUNT(DISTINCT symbol) AS symbols,
                               MIN(trade_date) AS min_date, MAX(trade_date) AS max_date
                        FROM market_daily_prices WHERE adjustment=?
                        """,
                        (mode,),
                    ).fetchone()
                    row_count = int(row["rows"] or 0)
                    symbol_count = int(row["symbols"] or 0)
                    min_date = row["min_date"]
                    max_date = str(row["max_date"] or "")
                    member_quality = ""
                stale_days = (
                    (date.today() - date.fromisoformat(max_date)).days
                    if max_date else None
                )
                fresh_current_symbol_count = int(connection.execute(
                    """
                    SELECT COUNT(DISTINCT p.symbol)
                    FROM market_daily_prices p
                    JOIN market_symbols s ON s.symbol=p.symbol
                    WHERE p.adjustment=? AND p.trade_date=?
                      AND s.listing_status='current'
                    """,
                    (mode, max_date),
                ).fetchone()[0]) if max_date else 0
                fresh_coverage_pct = (
                    fresh_current_symbol_count / current_symbol_count * 100
                    if current_symbol_count else 0.0
                )
                quality_status = (
                    "passed"
                    if member_quality in {"", "passed"}
                    and stale_days is not None
                    and stale_days <= 7
                    and fresh_coverage_pct >= 98.0
                    else "needs_attention"
                )
                adjustments[mode] = {
                    "table": "market_daily_prices",
                    "row_count": row_count,
                    "symbol_count": symbol_count,
                    "min_date": min_date,
                    "max_date": max_date,
                    "observed_max_date": observed_max_date,
                    "has_unpublished_observations": bool(
                        observed_max_date and observed_max_date > max_date
                    ),
                    "duplicate_row_count": 0,
                    "stale_days": stale_days,
                    "fresh_current_symbol_count": fresh_current_symbol_count,
                    "missing_current_symbol_count": max(
                        0, current_symbol_count - fresh_current_symbol_count
                    ),
                    "fresh_coverage_pct": round(fresh_coverage_pct, 4),
                    "quality_status": quality_status,
                }
        return {
            "status": "ready",
            "source": "canonical_a_share_sqlite",
            "provider": "akshare",
            "database_path": str(self.database_path.resolve()),
            "database_size_bytes": self.database_path.stat().st_size,
            "read_only": False,
            "published_data_version": (
                str(published_version["data_version_id"])
                if published_version else None
            ),
            "published_as_of_trade_date": (
                str(published_version["as_of_trade_date"])
                if published_version else None
            ),
            "catalog_symbol_count": catalog_symbol_count,
            "current_symbol_count": current_symbol_count,
            "current_symbol_duplicate_count": 0,
            "history_symbol_count": history_count,
            "history_only_symbol_count": historical_catalog_count,
            "markets": ["SSE", "SZSE", "BSE"],
            "adjustments": adjustments,
            "acceptance_scope": {
                "frequency": "daily",
                "start_date": adjustments["raw"]["min_date"],
                "end_date": adjustments["raw"]["max_date"],
                "includes_historical_symbols": True,
            },
        }
    def list_symbols(
        self, *, query: str = "", market: str = "", limit: int = 100, offset: int = 0,
    ) -> dict[str, Any]:
        if not self.is_available():
            return {"status": "unavailable", "total": 0, "items": [], "read_only": False}
        needle = str(query or "").strip()
        market_filter = str(market or "").strip().upper()
        filters = []
        values: list[Any] = []
        if needle:
            filters.append("(symbol LIKE ? OR name LIKE ?)")
            values.extend((f"%{needle}%", f"%{needle}%"))
        if market_filter:
            filters.append("market = ?")
            values.append(market_filter)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        page_limit = max(1, min(int(limit), 500))
        page_offset = max(0, int(offset))
        with closing(self._connect(read_only=True)) as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) FROM market_symbols {where}", values
            ).fetchone()[0])
            rows = connection.execute(
                f"""SELECT symbol, rqalpha_symbol, name, market, listing_status
                    FROM market_symbols {where} ORDER BY symbol LIMIT ? OFFSET ?""",
                (*values, page_limit, page_offset),
            ).fetchall()
        return {
            "status": "ready", "source": "canonical_a_share_sqlite", "read_only": False,
            "query": needle, "market": market_filter, "total": total,
            "limit": page_limit, "offset": page_offset, "items": [dict(row) for row in rows],
        }

    def fetch_daily_prices(
        self, *, symbol: str, adjustment: str = "raw",
        start_date: str | None = None, end_date: str | None = None,
        limit: int = 200, offset: int = 0,
    ) -> dict[str, Any]:
        code = _normalize_symbol(symbol)
        mode = _normalize_adjustment(adjustment)
        filters = ["symbol=?", "adjustment=?"]
        filters.append("NOT EXISTS (SELECT 1 FROM security_trading_status_daily s WHERE s.symbol=market_daily_prices.symbol AND s.trade_date=market_daily_prices.trade_date AND s.is_tradable=0)")
        values: list[Any] = [code, mode]
        if start_date:
            filters.append("trade_date>=?")
            values.append(str(start_date))
        if end_date:
            filters.append("trade_date<=?")
            values.append(str(end_date))
        where = " AND ".join(filters)
        page_limit = max(1, min(int(limit), 2000))
        page_offset = max(0, int(offset))
        quality: dict[str, Any] = {
            "status": "not_evaluated",
            "missing_count": None,
            "invalid_count": None,
        }
        with closing(self._connect(read_only=True)) as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) FROM market_daily_prices WHERE {where}", values
            ).fetchone()[0])
            rows = connection.execute(
                f"""SELECT trade_date AS date, open, high, low, close, volume, amount, amplitude,
                           change_pct, change_amount, turnover_rate, source, source_rowid
                    FROM market_daily_prices WHERE {where}
                    ORDER BY trade_date DESC LIMIT ? OFFSET ?""",
                (*values, page_limit, page_offset),
            ).fetchall()
            coverage_start_row = connection.execute(
                "SELECT MIN(trade_date) FROM market_daily_prices WHERE symbol=? AND adjustment=?",
                (code, mode),
            ).fetchone()
            coverage_start_date = coverage_start_row[0] if coverage_start_row else None
            if start_date and end_date:
                missing = connection.execute(
                    """
                    SELECT COUNT(*) AS count,
                           MIN(cal.trade_date) AS first_missing_date,
                           MAX(cal.trade_date) AS last_missing_date
                    FROM market_trade_calendar cal
                    WHERE cal.market='CN' AND cal.is_open=1
                      AND cal.trade_date BETWEEN ? AND ?
                      AND cal.trade_date >= MAX(
                          COALESCE((
                              SELECT MIN(effective_from) FROM security_lifecycle_events
                              WHERE symbol=? AND event_type='listed'
                          ), ?),
                          COALESCE((
                              SELECT MIN(first_price.trade_date) FROM market_daily_prices first_price
                              WHERE first_price.symbol=? AND first_price.adjustment=?
                          ), ?)
                      )
                      AND cal.trade_date < COALESCE((
                          SELECT MIN(effective_from)
                          FROM security_lifecycle_events
                          WHERE symbol=? AND event_type IN ('delisted','terminated')
                      ), '9999-12-31')
                      AND NOT EXISTS (
                          SELECT 1 FROM market_daily_prices p
                          WHERE p.symbol=? AND p.adjustment=?
                            AND p.trade_date=cal.trade_date
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM security_trading_status_daily s
                          WHERE s.symbol=? AND s.trade_date=cal.trade_date
                            AND s.is_tradable=0
                      )
                    """,
                    (str(start_date), str(end_date), code, str(start_date), code, mode,
                     str(start_date), code, code, mode, code),
                ).fetchone()
                invalid_count = int(connection.execute(
                    f"""SELECT COUNT(*) FROM market_daily_prices
                        WHERE {where} AND (
                            open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
                            OR high < MAX(open, close, low)
                            OR low > MIN(open, close, high)
                            OR volume < 0
                        )""",
                    values,
                ).fetchone()[0])
                missing_count = int(missing["count"] or 0)
                outside_coverage = bool(
                    coverage_start_date and str(end_date) < str(coverage_start_date)
                )
                quality = {
                    "status": (
                        "outside_coverage" if outside_coverage
                        else "passed" if missing_count == 0 and invalid_count == 0
                        else "needs_attention"
                    ),
                    "expected_count": None if outside_coverage else total + missing_count,
                    "stored_count": total,
                    "missing_count": None if outside_coverage else missing_count,
                    "first_missing_date": missing["first_missing_date"],
                    "last_missing_date": missing["last_missing_date"],
                    "coverage_start_date": coverage_start_date,
                    "invalid_count": invalid_count,
                }
        return {
            "status": "ready", "source": "canonical_a_share_sqlite", "provider": "akshare",
            "read_only": False, "symbol": code, "market": _market(code), "adjustment": mode,
            "start_date": start_date, "end_date": end_date, "total": total,
            "duplicate_rows_removed": 0, "limit": page_limit, "offset": page_offset,
            "quality": quality,
            "rows": [dict(row) for row in rows],
        }

    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        adjustment: str = "raw",
    ) -> list[dict[str, Any]]:
        """Return ascending OHLCV rows for the local backtest runtime."""

        code = _normalize_symbol(symbol)
        mode = _normalize_adjustment(adjustment)
        filters = ["symbol=?", "adjustment=?"]
        filters.append("NOT EXISTS (SELECT 1 FROM security_trading_status_daily s WHERE s.symbol=market_daily_prices.symbol AND s.trade_date=market_daily_prices.trade_date AND s.is_tradable=0)")
        values: list[Any] = [code, mode]
        if start_date:
            filters.append("trade_date>=?")
            values.append(str(start_date))
        if end_date:
            filters.append("trade_date<=?")
            values.append(str(end_date))
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"""SELECT trade_date AS date, open, high, low, close, volume,
                           amount, turnover_rate
                    FROM market_daily_prices
                    WHERE {' AND '.join(filters)}
                    ORDER BY trade_date""",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def _get_state(self, key: str) -> str | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT state_value FROM market_sync_state WHERE state_key=?", (key,)
            ).fetchone()
        return str(row[0]) if row else None

    def _set_state(self, key: str, value: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO market_sync_state (state_key, state_value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(state_key) DO UPDATE SET
                       state_value=excluded.state_value, updated_at=excluded.updated_at""",
                (key, value, _utc_now()),
            )

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            connection = sqlite3.connect(
                f"file:{self.database_path.resolve().as_posix()}?mode=ro", uri=True
            )
            connection.execute("PRAGMA query_only = ON")
        else:
            connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
