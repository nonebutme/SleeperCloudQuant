"""Fail-closed immutable access for formal A-share source verification."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

from data_platform.storage.a_share_market_store import AShareMarketStore


FORMAL_SOURCE_DATABASE_ENV = "SCQ_FORMAL_SOURCE_A_SHARE_CANONICAL_DB_PATH"


def resolve_formal_source_database_path() -> Path:
    """Resolve the explicitly authorized formal source database path."""

    configured = str(os.environ.get(FORMAL_SOURCE_DATABASE_ENV) or "").strip()
    if not configured:
        raise RuntimeError(
            f"{FORMAL_SOURCE_DATABASE_ENV} is required for formal source verification"
        )
    path = Path(configured)
    if not path.is_absolute():
        raise RuntimeError(f"{FORMAL_SOURCE_DATABASE_ENV} must be an absolute path")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise RuntimeError(f"formal source database is not a file: {resolved}")
    return resolved


def connect_immutable_a_share_database(path: str | Path) -> sqlite3.Connection:
    """Open SQLite with immutable read-only URI semantics and query-only enforcement."""

    resolved = Path(path).resolve(strict=True)
    if not resolved.is_file():
        raise RuntimeError(f"formal source database is not a file: {resolved}")
    encoded_path = quote(resolved.as_posix(), safe="/:")
    connection = sqlite3.connect(
        f"file:{encoded_path}?mode=ro&immutable=1",
        uri=True,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        query_only = int(connection.execute("PRAGMA query_only").fetchone()[0])
        if query_only != 1:
            raise RuntimeError("SQLite query_only enforcement is unavailable")
        return connection
    except BaseException:
        connection.close()
        raise


class ImmutableAShareMarketStore(AShareMarketStore):
    """AShareMarketStore facade that cannot obtain a writable connection."""

    def ensure_schema(self) -> None:
        raise sqlite3.OperationalError(
            "formal source verification forbids schema initialization"
        )

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if not read_only:
            raise sqlite3.OperationalError(
                "formal source verification forbids writable SQLite connections"
            )
        return connect_immutable_a_share_database(self.database_path)

    @staticmethod
    def _mark_read_only(payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        result["read_only"] = True
        result["connection_mode"] = "mode=ro&immutable=1"
        result["query_only"] = True
        return result

    def get_overview(self) -> dict[str, Any]:
        return self._mark_read_only(super().get_overview())

    def list_symbols(
        self,
        *,
        query: str = "",
        market: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        return self._mark_read_only(
            super().list_symbols(
                query=query,
                market=market,
                limit=limit,
                offset=offset,
            )
        )

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
        return self._mark_read_only(
            super().fetch_daily_prices(
                symbol=symbol,
                adjustment=adjustment,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            )
        )
