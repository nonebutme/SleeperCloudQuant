"""SQLite-backed storage for minimal factor results."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from factor_lab.models import FactorDefinition, FactorValue


class SqliteFactorStore:
    """Persist minimal factor values into the shared local SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_factor_values(
        self,
        *,
        definition: FactorDefinition,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        rows: list[FactorValue],
    ) -> str:
        stored_at = _utc_now()
        scope_start = start_date or ""
        scope_end = end_date or ""
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM factor_result_cache
                WHERE factor_id = ?
                  AND symbol = ?
                  AND start_date = ?
                  AND end_date = ?
                """,
                (definition.factor_id, symbol, scope_start, scope_end),
            )
            connection.executemany(
                """
                INSERT INTO factor_result_cache (
                    factor_id,
                    factor_name,
                    factor_version,
                    symbol,
                    trade_date,
                    factor_value,
                    start_date,
                    end_date,
                    stored_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        definition.factor_id,
                        definition.name,
                        definition.version,
                        row.symbol,
                        row.trade_date,
                        row.value,
                        scope_start,
                        scope_end,
                        stored_at,
                    )
                    for row in rows
                ],
            )
            connection.commit()
        return stored_at

    def fetch_factor_values(
        self,
        *,
        factor_id: str,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[FactorValue]:
        scope_start = start_date or ""
        scope_end = end_date or ""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT factor_id, symbol, trade_date, factor_value
                FROM factor_result_cache
                WHERE factor_id = ?
                  AND symbol = ?
                  AND start_date = ?
                  AND end_date = ?
                ORDER BY trade_date
                """,
                (factor_id, symbol, scope_start, scope_end),
            ).fetchall()
        return [
            FactorValue(
                factor_id=str(row["factor_id"]),
                symbol=str(row["symbol"]),
                trade_date=str(row["trade_date"]),
                value=float(row["factor_value"]),
            )
            for row in rows
        ]

    def fetch_factor_rankings(
        self,
        *,
        factor_id: str,
        trade_date: str,
        start_date: str | None,
        end_date: str | None,
        limit: int,
        descending: bool,
    ) -> list[FactorValue]:
        scope_start = start_date or ""
        scope_end = end_date or ""
        order_by = "DESC" if descending else "ASC"
        sql = f"""
            SELECT factor_id, symbol, trade_date, factor_value
            FROM factor_result_cache
            WHERE factor_id = ?
              AND trade_date = ?
              AND start_date = ?
              AND end_date = ?
            ORDER BY factor_value {order_by}, symbol ASC
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(
                sql,
                (factor_id, trade_date, scope_start, scope_end, limit),
            ).fetchall()
        return [
            FactorValue(
                factor_id=str(row["factor_id"]),
                symbol=str(row["symbol"]),
                trade_date=str(row["trade_date"]),
                value=float(row["factor_value"]),
            )
            for row in rows
        ]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS factor_result_cache (
                    factor_id TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    factor_version TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    factor_value REAL NOT NULL,
                    start_date TEXT NOT NULL DEFAULT '',
                    end_date TEXT NOT NULL DEFAULT '',
                    stored_at TEXT NOT NULL,
                    PRIMARY KEY (factor_id, symbol, trade_date, start_date, end_date)
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
