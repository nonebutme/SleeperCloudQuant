"""Windows-safe SQLite implementation of the Strategy Manifest service."""

from __future__ import annotations

import sqlite3

from app.services.strategy_manifest_service import StrategyManifestService as _BaseService


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class SqliteStrategyManifestService(_BaseService):
    """Use a connection that closes at the end of every transaction context."""

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection

