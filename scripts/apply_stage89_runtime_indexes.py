"""Create Stage 89 runtime query indexes without changing business rows."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime.database_paths import backtest_runtime_database_path


INDEXES = (
    ("idx_backtest_runs_active_created", "backtest_runs", "deleted_at, created_at DESC, run_id DESC"),
    ("idx_backtest_logs_run_id", "backtest_logs", "run_id, id"),
    ("idx_backtest_trades_run_id", "backtest_trades", "run_id, id"),
    ("idx_backtest_trades_run_side_time", "backtest_trades", "run_id, side, trade_time"),
    ("idx_backtest_positions_run_id", "backtest_positions", "run_id, id"),
    ("idx_backtest_positions_run_snapshot", "backtest_positions", "run_id, snapshot_time"),
    ("idx_backtest_accounts_run_id", "backtest_accounts", "run_id, id"),
    ("idx_backtest_accounts_run_snapshot", "backtest_accounts", "run_id, snapshot_time"),
)


def main() -> None:
    database_path = backtest_runtime_database_path()
    if not database_path.exists():
        raise SystemExit(f"runtime database does not exist: {database_path}")
    connection = sqlite3.connect(database_path, timeout=60)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for index_name, table_name, columns in INDEXES:
            if table_name not in tables:
                raise RuntimeError(f"required table is missing: {table_name}")
            print(f"[stage89] ensuring {index_name}", flush=True)
            connection.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                f'ON "{table_name}" ({columns})'
            )
            connection.commit()
        connection.execute("PRAGMA optimize")
        connection.commit()
        print(f"[stage89] runtime indexes ready count={len(INDEXES)}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
