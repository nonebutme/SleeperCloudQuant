"""Verify bounded staging, resumable publication, and storage gates."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from factor_lab.research_core import canonical_hash, distribution
    from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore

    with tempfile.TemporaryDirectory(
        prefix="scq-factor-streaming-", ignore_cleanup_errors=True,
    ) as directory:
        path = Path(directory) / "streaming.sqlite3"
        store = SqliteFactorResearchStore(path)
        task_id = "streaming-smoke-task"
        config = {
            "factor_id": "winner_proxy_low_120d", "factor_version": "v1",
            "factor_adjustment": "qfq",
        }
        context = {"data_version_id": "test-version"}
        snapshot = {"symbols": ["000001", "000002"]}
        task = store.create_task(
            task_id=task_id, config=config, context=context,
            context_hash=canonical_hash(context), preflight={},
            data_version_id="test-version", quality_report_id="test-quality",
            pool_snapshot=snapshot,
        )
        rows = [
            _row("2024-01-02", "000001", 1.0),
            _row("2024-01-02", "000002", 2.0),
            _row("2024-01-03", "000001", 3.0),
        ]
        store.append_observations(task_id, rows)
        store.append_observations(task_id, rows)
        store.add_universe_counts(task_id, {"2024-01-02": 2, "2024-01-03": 1}, batch_offset=0)
        store.add_universe_counts(task_id, {"2024-01-02": 2, "2024-01-03": 1}, batch_offset=0)
        if store.observation_count(task_id) != 3:
            raise SystemExit("streaming smoke failed: idempotent observation append")
        if store.fetch_universe_counts(task_id) != {"2024-01-02": 2, "2024-01-03": 1}:
            raise SystemExit("streaming smoke failed: idempotent universe batches")
        for trade_date in store.observation_dates(task_id):
            daily = store.fetch_observations_for_date(task_id, trade_date)
            for row in daily:
                row["processed_value"] = row["raw_value"]
                row["aligned_value"] = row["raw_value"]
                row["evidence"] = {"streaming": True}
            store.update_processed_observations(task_id, daily)
        actual_distribution = store.processed_distribution(task_id)
        expected_distribution = distribution([1.0, 2.0, 3.0])
        for field in ("count", "mean", "std", "min", "p01", "median", "p99", "max"):
            if abs(float(actual_distribution[field]) - float(expected_distribution[field])) > 1e-12:
                raise SystemExit(f"streaming smoke failed: distribution {field}")

        task = store.get_task(task_id)
        snapshot_hash = task["snapshots"][0]["content_hash"]
        values = [
            {"trade_date": row["trade_date"], "symbol": row["symbol"],
             "value": row["processed_value"], "aligned_value": row["aligned_value"]}
            for row in store.fetch_observations(task_id)
        ]
        identity = {
            "factor_id": "winner_proxy_low_120d", "factor_version": "v1",
            "source_task_id": task_id, "context_hash": task["context_hash"],
            "data_version_id": "test-version", "quality_report_id": "test-quality",
            "adjustment": "qfq", "pool_snapshot_hash": snapshot_hash,
            "start_date": "2024-01-02", "end_date": "2024-01-03", "row_count": 3,
        }
        expected_hash = canonical_hash({"identity": identity, "values": values})
        artifact_id = f"factor-artifact-{expected_hash[:20]}"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                """INSERT INTO factor_artifacts (
                       artifact_id, factor_id, factor_version, source_task_id,
                       context_hash, data_version_id, quality_report_id, adjustment,
                       pool_snapshot_hash, start_date, end_date, status, row_count,
                       content_hash, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'publishing', ?, ?, ?)""",
                (artifact_id, identity["factor_id"], identity["factor_version"], task_id,
                 identity["context_hash"], identity["data_version_id"],
                 identity["quality_report_id"], identity["adjustment"],
                 identity["pool_snapshot_hash"], identity["start_date"],
                 identity["end_date"], identity["row_count"], expected_hash,
                 "2026-08-18T00:00:00+00:00"),
            )
            first = values[0]
            connection.execute(
                """INSERT INTO factor_artifact_values
                   (artifact_id, trade_date, symbol, value, aligned_value)
                   VALUES (?, ?, ?, ?, ?)""",
                (artifact_id, first["trade_date"], first["symbol"],
                 first["value"], first["aligned_value"]),
            )
            connection.commit()
        artifact = store.publish_artifact(task_id)
        if artifact["status"] != "research_ready" or artifact["row_count"] != 3:
            raise SystemExit("streaming smoke failed: resumable artifact publication")
        if artifact["content_hash"] != expected_hash:
            raise SystemExit("streaming smoke failed: legacy canonical hash compatibility")
        ready_gate = store.storage_headroom(reserve_bytes=1)
        blocked_gate = store.storage_headroom(reserve_bytes=ready_gate["free_bytes"] + 1)
        if ready_gate["status"] != "ready" or blocked_gate["status"] != "blocked":
            raise SystemExit("streaming smoke failed: storage headroom gate")
        checkpoint = store.checkpoint_wal(truncate=True)
        if checkpoint["busy"] != 0:
            raise SystemExit("streaming smoke failed: WAL checkpoint busy")
    print("factor research streaming smoke test passed")


def _row(trade_date: str, symbol: str, value: float) -> dict[str, object]:
    return {
        "trade_date": trade_date, "symbol": symbol, "raw_value": value,
        "forward_returns": {"5": value / 100.0}, "industry": "测试行业",
    }


if __name__ == "__main__":
    main()
