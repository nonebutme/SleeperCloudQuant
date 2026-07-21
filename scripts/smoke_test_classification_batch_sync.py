"""Smoke test the resumable classification sync state machine."""

from __future__ import annotations
import time

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from data_platform import ClassificationHistoryStore

    store = ClassificationHistoryStore("tmp/stage64_sync_state_smoke.sqlite3")
    job_id = f"stage64-state-smoke-{time.time_ns()}"
    prepared = store.prepare_sync_job(job_id, ["000001", "600000", "000001.XSHE"], observed_at="2026-07-18T00:00:00+00:00")
    if prepared != 2 or store.list_sync_symbols(job_id) != ["000001", "600000"]:
        raise SystemExit("classification batch smoke failed: prepare/dedup mismatch")
    store.mark_sync_state(job_id, "000001", status="completed", attempt_count=1, interval_count=3, updated_at="2026-07-18T00:01:00+00:00")
    store.mark_sync_state(job_id, "600000", status="failed", attempt_count=3, error_message="provider timeout", updated_at="2026-07-18T00:01:00+00:00")
    summary = store.sync_job_summary(job_id)
    if summary["by_status"]["completed"]["count"] != 1 or summary["by_status"]["failed"]["count"] != 1:
        raise SystemExit("classification batch smoke failed: summary mismatch")
    if store.list_sync_symbols(job_id) != ["600000"]:
        raise SystemExit("classification batch smoke failed: failed resume queue mismatch")
    print("stage64 classification batch sync smoke test passed")


if __name__ == "__main__":
    main()
