"""Run the approved isolated 500-symbol streaming WINNER pilot.

The pilot is development-only, ends before the sealed OOS boundary, and must
never write to the formal factor-research database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


DATA_VERSION_ID = "scq-20260810-045e17a46a731835"
FACTOR_ID = "winner_proxy_low_120d"
START_DATE = "2015-01-05"
END_DATE = "2024-11-29"
OUTCOME_CUTOFF = "2024-12-31"
OOS_START = "2025-01-01"
SYMBOL_COUNT = 500
RESERVE_BYTES = 80 * 1024**3
ESTIMATED_BYTES_PER_ROW = 4096
BASELINE_TASK_ID = (
    "fujing-v7-development-cohort-200-winner_proxy_low_120d-2015-2024-raw-v2"
)
PILOT_TASK_ID = "fujing-v7-streaming-pilot-500-winner-low-2015-2024-v1"


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.factor_analysis_service import FactorAnalysisService
    from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--market-database", default="var/market/a_share_market.sqlite3")
    parser.add_argument(
        "--formal-research-database", default="var/runtime/factor_research.sqlite3"
    )
    parser.add_argument(
        "--pilot-research-database",
        default="var/pilots/fujing_v7_streaming_winner_500.sqlite3",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    market_path = Path(args.market_database).resolve()
    formal_path = Path(args.formal_research_database).resolve()
    pilot_path = Path(args.pilot_research_database).resolve()
    if pilot_path == formal_path:
        raise SystemExit("pilot database must be isolated from the formal research database")

    baseline_symbols = _baseline_symbols(formal_path)
    store = SqliteFactorResearchStore(pilot_path)
    service = FactorAnalysisService(market_database_path=market_path, research_store=store)
    full_preflight = service.preflight(_config([]))
    if full_preflight.get("status") != "ready":
        raise SystemExit(json.dumps(full_preflight, ensure_ascii=False, indent=2))
    full_symbols = list(full_preflight["pool_snapshot"]["symbols"])
    symbols = _extend_cohort(baseline_symbols, full_symbols, SYMBOL_COUNT)
    task_preflight = service.preflight(_config(symbols))
    if task_preflight.get("status") != "ready":
        raise SystemExit(json.dumps(task_preflight, ensure_ascii=False, indent=2))
    estimated_rows = len(symbols) * int(task_preflight["evidence"]["trade_date_count"])
    headroom = store.storage_headroom(
        reserve_bytes=RESERVE_BYTES,
        estimated_additional_bytes=estimated_rows * ESTIMATED_BYTES_PER_ROW,
    )
    preview = {
        "status": "ready_to_apply" if not args.apply else "running",
        "policy": "isolated_streaming_single_factor_pre_oos_pilot",
        "factor_id": FACTOR_ID,
        "data_version_id": DATA_VERSION_ID,
        "factor_window": {"start_date": START_DATE, "end_date": END_DATE},
        "sealed_oos": {"start_date": OOS_START, "status": "not_viewed"},
        "symbol_count": len(symbols),
        "baseline_symbol_count": len(baseline_symbols),
        "symbols_sha256": hashlib.sha256(
            json.dumps(symbols, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "estimated_rows_upper_bound": estimated_rows,
        "estimated_bytes_per_row": ESTIMATED_BYTES_PER_ROW,
        "storage_headroom": headroom,
        "pilot_database": str(pilot_path),
        "formal_database_access": "read_only_comparison_only",
    }
    if headroom["status"] != "ready":
        raise SystemExit(json.dumps({**preview, "status": "blocked"}, ensure_ascii=False, indent=2))
    if not args.apply:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    formal_before = _file_identity(formal_path)
    task = service.get_task(PILOT_TASK_ID)
    if task.get("status") == "not_found":
        task = service.create_task({**_config(symbols), "task_id": PILOT_TASK_ID})
    if task.get("status") != "completed":
        task = service.start_task(PILOT_TASK_ID, wait=True)
    artifact = next(
        (
            item for item in store.list_artifacts(factor_id=FACTOR_ID, limit=20)
            if item.get("source_task_id") == PILOT_TASK_ID
        ),
        {"status": "not_found"},
    )
    comparison = _compare_baseline(formal_path, store.database_path, artifact)
    checkpoint = store.checkpoint_wal(truncate=True)
    formal_after = _file_identity(formal_path)
    result = {
        **preview,
        "status": "completed" if task.get("status") == "completed" else "failed",
        "task": {
            "task_id": PILOT_TASK_ID,
            "status": task.get("status"),
            "report_id": task.get("report_id"),
            "progress": task.get("progress"),
            "error": task.get("error"),
        },
        "artifact": artifact,
        "baseline_comparison": comparison,
        "formal_database_unchanged": formal_before == formal_after,
        "formal_database_identity_before": formal_before,
        "formal_database_identity_after": formal_after,
        "wal_checkpoint": checkpoint,
        "final_storage_headroom": store.storage_headroom(reserve_bytes=RESERVE_BYTES),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _config(symbols: list[str]) -> dict[str, object]:
    return {
        "name": "拂经V7流式隔离试点：WINNER low 120d",
        "factor_id": FACTOR_ID,
        "pool_type": "all_a",
        "universe_policy": "fujing_v7_point_in_time",
        "symbols": symbols,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "pool_as_of_date": END_DATE,
        "factor_adjustment": "qfq",
        "outcome_adjustment": "qfq",
        "forward_horizons": [5, 20],
        "preprocessing": {
            "winsor_mad": 0.0, "industry_neutral": False, "standardize": False,
        },
        "group_count": 5,
        "cost_assumption": {"one_side_rate": 0.001},
        "data_version_id": DATA_VERSION_ID,
    }


def _baseline_symbols(path: Path) -> list[str]:
    if not path.exists():
        return []
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        row = connection.execute(
            """SELECT payload_json FROM factor_research_snapshots
               WHERE task_id=? AND snapshot_type='pool' LIMIT 1""",
            (BASELINE_TASK_ID,),
        ).fetchone()
    if row is None:
        return []
    return [str(item) for item in json.loads(row[0]).get("symbols") or []]


def _extend_cohort(baseline: list[str], universe: list[str], count: int) -> list[str]:
    eligible = sorted(set(universe))
    selected = [item for item in baseline if item in set(eligible)]
    remaining = [item for item in eligible if item not in set(selected)]
    needed = max(0, count - len(selected))
    if needed and remaining:
        indices = {
            round(index * (len(remaining) - 1) / max(1, needed - 1))
            for index in range(needed)
        }
        selected.extend(remaining[index] for index in sorted(indices))
    return sorted(set(selected))[:count]


def _compare_baseline(
    formal_path: Path, pilot_path: Path, artifact: dict[str, object],
) -> dict[str, object]:
    artifact_id = str(artifact.get("artifact_id") or "")
    if not formal_path.exists() or not artifact_id:
        return {"status": "unavailable", "reason": "baseline_or_pilot_artifact_missing"}
    formal_uri = f"file:{formal_path.as_posix()}?mode=ro"
    pilot_uri = f"file:{pilot_path.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(formal_uri, uri=True)) as formal, closing(
        sqlite3.connect(pilot_uri, uri=True)
    ) as pilot:
        baseline_artifact = formal.execute(
            "SELECT artifact_id FROM factor_artifacts WHERE source_task_id=?",
            (BASELINE_TASK_ID,),
        ).fetchone()
        if baseline_artifact is None:
            return {"status": "unavailable", "reason": "baseline_artifact_missing"}
        left = formal.execute(
            """SELECT trade_date, symbol, value, aligned_value
               FROM factor_artifact_values WHERE artifact_id=?
               ORDER BY trade_date, symbol""", (baseline_artifact[0],),
        )
        right = pilot.execute(
            """SELECT trade_date, symbol, value, aligned_value
               FROM factor_artifact_values WHERE artifact_id=?
               ORDER BY trade_date, symbol""", (artifact_id,),
        )
        matched = mismatched = 0
        right_row = right.fetchone()
        for left_row in left:
            left_key = (left_row[0], left_row[1])
            while right_row is not None and (right_row[0], right_row[1]) < left_key:
                right_row = right.fetchone()
            if right_row is None or (right_row[0], right_row[1]) != left_key:
                continue
            matched += 1
            if left_row[2:] != right_row[2:]:
                mismatched += 1
    return {
        "status": "passed" if matched > 0 and mismatched == 0 else "failed",
        "matched_rows": matched,
        "mismatched_rows": mismatched,
        "comparison": "exact_value_and_aligned_value",
    }


def _file_identity(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


if __name__ == "__main__":
    main()
