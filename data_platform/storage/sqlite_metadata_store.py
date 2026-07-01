"""SQLite-backed metadata store for phase-1 market-data caching."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class SqliteMetadataStore:
    """Persist cached price-history rows for the phase-1 data platform."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    @property
    def database_path(self) -> Path:
        """Return the SQLite database path."""

        return self._database_path

    def ensure_schema(self) -> None:
        """Create only the cache tables needed by the phase-1 data platform."""

        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_data_cache (
                    cache_key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    start_date TEXT,
                    end_date TEXT,
                    rows_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_market_data_cache_symbol
                ON market_data_cache(symbol, start_date, end_date);
                """
            )

    def fetch_market_data_cache(
        self,
        *,
        cache_key: str,
    ) -> Sequence[Mapping[str, Any]] | None:
        """Return cached price-history rows if present."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT rows_json
                FROM market_data_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["rows_json"]))

    def upsert_market_data_cache(
        self,
        *,
        cache_key: str,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        rows: Sequence[Mapping[str, Any]],
        created_at: str,
    ) -> None:
        """Insert or replace cached price-history rows."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_data_cache (
                    cache_key,
                    symbol,
                    start_date,
                    end_date,
                    rows_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    symbol = excluded.symbol,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    rows_json = excluded.rows_json,
                    created_at = excluded.created_at
                """,
                (
                    cache_key,
                    symbol,
                    start_date,
                    end_date,
                    self._dump_rows(rows),
                    created_at,
                ),
            )

    @contextmanager
    def _connect(self) -> Any:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _dump_rows(rows: Sequence[Mapping[str, Any]]) -> str:
        return json.dumps([dict(row) for row in rows], ensure_ascii=False)
