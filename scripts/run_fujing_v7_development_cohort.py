"""Run a governed pre-OOS Fujing V7 development cohort.

This is an intermediate scalability and parameter-research cohort. It must
not be presented as the point-in-time full-universe conclusion or as OOS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


DATA_VERSION_ID = "scq-20260810-045e17a46a731835"
DEVELOPMENT_START = "2015-01-05"
LAST_FACTOR_DATE = "2024-11-29"
DEVELOPMENT_OUTCOME_CUTOFF = "2024-12-31"
OOS_START = "2025-01-01"
FACTORS = (
    "winner_proxy_low_120d",
    "winner_proxy_high_120d",
    "winner_proxy_spread_120d",
    "causal_trough_event_16d",
    "amplitude_ratio_1d",
)
MAX_ESTIMATED_ROWS_PER_TASK = 750_000
TASK_REVISION = "2015-2024-raw-v2"


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.factor_analysis_service import FactorAnalysisService
    from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--market-database", default="var/market/a_share_market.sqlite3")
    parser.add_argument("--research-database", default="var/runtime/factor_research.sqlite3")
    parser.add_argument("--symbol-count", type=int, default=200)
    parser.add_argument("--factor", choices=FACTORS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    requested_count = max(20, min(int(args.symbol_count), 500))
    store = SqliteFactorResearchStore(Path(args.research_database))
    service = FactorAnalysisService(
        market_database_path=Path(args.market_database), research_store=store,
    )
    base = _config(FACTORS[0], symbols=[])
    full_preflight = service.preflight(base)
    if full_preflight.get("status") != "ready":
        raise SystemExit(json.dumps(full_preflight, ensure_ascii=False, indent=2))
    full_symbols = list(full_preflight["pool_snapshot"]["symbols"])
    symbols = _evenly_spaced(full_symbols, min(requested_count, len(full_symbols)))
    trade_date_count = int(full_preflight["evidence"]["trade_date_count"])
    estimated_rows = len(symbols) * trade_date_count
    if estimated_rows > MAX_ESTIMATED_ROWS_PER_TASK:
        raise SystemExit(
            f"development cohort exceeds memory safety gate: {estimated_rows} > "
            f"{MAX_ESTIMATED_ROWS_PER_TASK} estimated rows"
        )
    outcome_boundary = service._trade_dates(LAST_FACTOR_DATE, DEVELOPMENT_OUTCOME_CUTOFF)
    if len(outcome_boundary) <= 20:
        raise SystemExit("development factor end does not leave 20 trading-day outcome coverage")
    selected_factors = (args.factor,) if args.factor else FACTORS
    result = {
        "status": "ready_to_apply" if not args.apply else "running",
        "policy": "development_cohort_not_full_universe_not_oos",
        "data_version_id": DATA_VERSION_ID,
        "universe_policy": "fujing_v7_point_in_time",
        "full_point_in_time_union_symbols": len(full_symbols),
        "cohort_symbol_count": len(symbols),
        "selection": "deterministic_even_spacing_over_sorted_governed_union",
        "symbols_sha256": hashlib.sha256(
            json.dumps(symbols, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "symbol_sample": {"first": symbols[:5], "last": symbols[-5:]},
        "factor_window": {"start_date": DEVELOPMENT_START, "end_date": LAST_FACTOR_DATE},
        "development_outcome_cutoff": DEVELOPMENT_OUTCOME_CUTOFF,
        "sealed_oos_candidate": {"start_date": OOS_START, "status": "not_viewed"},
        "estimated_rows_per_task_upper_bound": estimated_rows,
        "row_safety_gate": MAX_ESTIMATED_ROWS_PER_TASK,
        "factors": list(selected_factors),
    }
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    tasks = []
    for factor_id in selected_factors:
        task_id = f"fujing-v7-development-cohort-{len(symbols)}-{factor_id}-{TASK_REVISION}"
        task = service.get_task(task_id)
        if task.get("status") == "not_found":
            task = service.create_task({**_config(factor_id, symbols=symbols), "task_id": task_id})
        if task.get("status") != "completed":
            task = service.start_task(task_id, wait=True)
        artifact = store.resolve_artifact(factor_id)
        tasks.append({
            "factor_id": factor_id,
            "task_id": task_id,
            "task_status": task.get("status"),
            "artifact_id": artifact.get("artifact_id"),
            "artifact_status": artifact.get("status"),
            "artifact_row_count": artifact.get("row_count"),
            "error": task.get("error"),
        })
        if task.get("status") != "completed":
            break
    print(json.dumps({**result, "status": "completed", "tasks": tasks}, ensure_ascii=False, indent=2))


def _config(factor_id: str, *, symbols: list[str]) -> dict[str, object]:
    return {
        "name": f"拂经V7开发队列：{factor_id}",
        "factor_id": factor_id,
        "pool_type": "all_a",
        "universe_policy": "fujing_v7_point_in_time",
        "symbols": symbols,
        "start_date": DEVELOPMENT_START,
        "end_date": LAST_FACTOR_DATE,
        "pool_as_of_date": LAST_FACTOR_DATE,
        "factor_adjustment": "qfq",
        "outcome_adjustment": "qfq",
        "forward_horizons": [5, 20],
        "preprocessing": {
            "winsor_mad": 0.0,
            "industry_neutral": False,
            "standardize": False,
        },
        "group_count": 5,
        "cost_assumption": {"one_side_rate": 0.001},
        "data_version_id": DATA_VERSION_ID,
    }


def _evenly_spaced(items: list[str], count: int) -> list[str]:
    if count >= len(items):
        return list(items)
    if count <= 1:
        return items[:count]
    indices = {round(index * (len(items) - 1) / (count - 1)) for index in range(count)}
    return [items[index] for index in sorted(indices)]


if __name__ == "__main__":
    main()
