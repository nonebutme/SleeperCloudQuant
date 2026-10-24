"""Read-only verification for Stage 89 runtime indexes and query plans."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime.database_paths import backtest_runtime_database_path
from scripts.apply_stage89_runtime_indexes import INDEXES


def main() -> None:
    database_path = backtest_runtime_database_path().resolve()
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        actual = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        expected = {item[0] for item in INDEXES}
        missing = sorted(expected - actual)
        if missing:
            raise RuntimeError(f"missing indexes: {missing}")
        plans = {
            "run_list": connection.execute(
                "EXPLAIN QUERY PLAN SELECT run_id FROM backtest_runs "
                "WHERE deleted_at IS NULL ORDER BY created_at DESC, run_id DESC LIMIT 100"
            ).fetchall(),
            "account_detail": connection.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM backtest_accounts "
                "WHERE run_id = ? ORDER BY id LIMIT 100",
                ("stage89-plan-probe",),
            ).fetchall(),
            "position_detail": connection.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM backtest_positions "
                "WHERE run_id = ? ORDER BY id LIMIT 100",
                ("stage89-plan-probe",),
            ).fetchall(),
        }
        if any("INDEX" not in str(plan).upper() for plan in plans.values()):
            raise RuntimeError(f"query plan did not use expected indexes: {plans}")
        result = connection.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"quick_check failed: {result}")
        print(f"[stage89] runtime index verification passed indexes={len(expected)}")
        for name, plan in plans.items():
            print(f"[stage89] {name}: {plan}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
