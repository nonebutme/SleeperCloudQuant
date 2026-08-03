"""Isolated task-deletion regression; never touches project databases."""

from __future__ import annotations

import gc
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.a_share_sync_scheduler import AShareSyncScheduler  # noqa: E402
from data_platform.storage.market_panorama_store import MarketPanoramaStore  # noqa: E402


def insert_sync_job(database: Path, job_id: str, status: str) -> None:
    now = "2026-08-01T00:00:00+00:00"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO market_incremental_sync_jobs (
                job_id, mode, status, target_trade_date, symbol_scope,
                adjustments_json, created_at, updated_at
            ) VALUES (?, 'manual', ?, '2026-07-30', '000001.XSHE', '[\"raw\"]', ?, ?)""",
            (job_id, status, now, now),
        )
        connection.execute(
            """INSERT INTO market_incremental_sync_items (
                job_id, symbol, adjustment, start_date, end_date, status, updated_at
            ) VALUES (?, '000001.XSHE', 'raw', '2026-07-30', '2026-07-30', 'completed', ?)""",
            (job_id, now),
        )


def main() -> None:
    with TemporaryDirectory(prefix="scq-task-delete-") as temp:
        root = Path(temp)
        scheduler = AShareSyncScheduler(root / "scheduler.sqlite3", provider=object())
        scheduler.ensure_schema()
        insert_sync_job(scheduler.database_path, "delete-me", "published")
        result = scheduler.delete_job("delete-me")
        assert result["status"] == "deleted" and result["market_data_deleted"] is False
        assert scheduler.get_job("delete-me")["status"] == "not_found"

        insert_sync_job(scheduler.database_path, "keep-running", "running")
        try:
            scheduler.delete_job("keep-running")
        except ValueError as error:
            assert "cannot be deleted" in str(error)
        else:
            raise AssertionError("running sync task deletion was not blocked")

        panorama = MarketPanoramaStore(root / "panorama.sqlite3")
        panorama.create_job("panorama-delete", ["industry_board_daily"], "2026-07-30", [])
        assert panorama.delete_job("panorama-delete")["status"] == "deleted"
        assert panorama.get_job("panorama-delete")["status"] == "not_found"

        panorama.create_job("panorama-running", ["industry_board_daily"], "2026-07-30", [])
        panorama.start_job("panorama-running")
        try:
            panorama.delete_job("panorama-running")
        except ValueError as error:
            assert "cannot be deleted" in str(error)
        else:
            raise AssertionError("running panorama task deletion was not blocked")

        del panorama, scheduler
        gc.collect()

    print("data-center task deletion smoke passed")


if __name__ == "__main__":
    main()