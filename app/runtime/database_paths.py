"""Authoritative local database paths for the formal runtime."""

from __future__ import annotations

import os
from pathlib import Path


def backtest_runtime_database_path() -> Path:
    """Return the formal backtest/result database path."""

    return Path(os.environ.get("SCQ_BACKTEST_RUNTIME_DB_PATH", "var/runtime/backtest_results.sqlite3"))
