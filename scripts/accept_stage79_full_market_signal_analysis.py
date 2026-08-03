"""Accept and persist Stage 79 cross-sectional evidence for one real task."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.runtime.demo_registry import build_demo_service_registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--expected-universe", type=int, required=True)
    args = parser.parse_args()

    registry = build_demo_service_registry()
    service = registry.independent_screening_service
    task = service.get_task(args.task_id)
    if task.get("status") not in {"completed", "partial_failed"}:
        raise AssertionError(f"task is not finished: {task.get('status')}")
    if int(task.get("progress", {}).get("total") or 0) != args.expected_universe:
        raise AssertionError("unexpected universe size")

    started = time.perf_counter()
    analysis = service.persist_signal_analysis(args.task_id)
    cold_seconds = time.perf_counter() - started
    started = time.perf_counter()
    cached = service.build_signal_analysis(args.task_id)
    warm_seconds = time.perf_counter() - started
    persisted = service.get_task(args.task_id).get("summary", {}).get("signal_analysis")
    if persisted != analysis or cached != analysis:
        raise AssertionError("persisted/cached analysis differs from computed evidence")

    ic = dict(analysis.get("ic_analysis") or {})
    layered = dict(analysis.get("layered_returns") or {})
    signal = dict(analysis.get("signal_summary") or {})
    layered_series = list(layered.get("series") or [])
    if ic.get("status") != "ready":
        raise AssertionError(f"IC is not ready: {ic.get('status')}")
    if layered.get("status") != "ready":
        raise AssertionError(f"layered returns are not ready: {layered.get('status')}")
    if warm_seconds >= 5:
        raise AssertionError(f"persisted report reload exceeded 5 seconds: {warm_seconds:.3f}")

    print(json.dumps({
        "task_id": args.task_id,
        "task_status": task.get("status"),
        "progress": task.get("progress"),
        "cold_seconds": cold_seconds,
        "persisted_reload_seconds": warm_seconds,
        "price_row_count": analysis.get("price_row_count"),
        "signal_summary": signal,
        "ic_summary": {
            key: ic.get(key)
            for key in (
                "mean", "stddev", "icir", "newey_west_t", "rank_mean",
                "positive_ratio", "period_count", "minimum_cross_section_size",
                "maximum_cross_section_size",
            )
        },
        "layered_summary": {
            "period_count": layered.get("period_count"),
            "minimum_cross_section_size": min(
                (int(row["sample_size"]) for row in layered_series), default=0
            ),
            "maximum_cross_section_size": max(
                (int(row["sample_size"]) for row in layered_series), default=0
            ),
            "monotonicity": layered.get("monotonicity"),
            "monotonicity_p_value": layered.get("monotonicity_p_value"),
            "long_short_annualized": layered.get("long_short_annualized"),
            "long_short_max_drawdown": layered.get("long_short_max_drawdown"),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
