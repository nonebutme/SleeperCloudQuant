"""Run an explicitly non-decision Fujing V7 factor research pilot."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


FACTORS = (
    "winner_proxy_low_120d",
    "winner_proxy_high_120d",
    "winner_proxy_spread_120d",
    "causal_trough_event_16d",
    "amplitude_ratio_1d",
)
EXCLUDED_PREFIXES = ("688", "689", "8", "43", "83", "87", "92", "900", "200")
DATA_VERSION_ID = "scq-20260810-045e17a46a731835"
PILOT_REVISION = "governed-universe-689-raw-v5"


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.factor_analysis_service import FactorAnalysisService
    from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--market-database", default="var/market/a_share_market.sqlite3")
    parser.add_argument("--research-database", default="var/runtime/factor_research.sqlite3")
    parser.add_argument("--symbol-limit", type=int, default=50)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    market_path = Path(args.market_database).resolve()
    symbols = _pilot_symbols(market_path, max(5, min(args.symbol_limit, 200)))
    preview = {
        "status": "ready_to_apply" if not args.apply else "running",
        "policy": "development_pilot_not_for_threshold_or_oos_decision",
        "data_version_id": DATA_VERSION_ID,
        "requested_range": {"start_date": "2023-01-03", "end_date": "2024-12-31"},
        "symbol_count": len(symbols),
        "symbols_hash_basis": symbols,
        "factors": list(FACTORS),
    }
    if not args.apply:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    store = SqliteFactorResearchStore(Path(args.research_database))
    service = FactorAnalysisService(
        market_database_path=market_path,
        research_store=store,
    )
    tasks = []
    for factor_id in FACTORS:
        task_id = f"fujing-v7-pilot-{factor_id}-2023-2024-{PILOT_REVISION}"
        task = service.get_task(task_id)
        if task.get("status") == "not_found":
            task = service.create_task({
                "task_id": task_id,
                "name": f"拂经V7开发链路试运行：{factor_id}",
                "factor_id": factor_id,
                "pool_type": "all_a",
                "universe_policy": "fujing_v7_point_in_time",
                "symbols": symbols,
                "start_date": "2023-01-03",
                "end_date": "2024-12-31",
                "pool_as_of_date": "2024-12-31",
                "factor_adjustment": "qfq",
                "outcome_adjustment": "qfq",
                "forward_horizons": [5, 20],
                "preprocessing": {
                    "winsor_mad": 0.0,
                    "industry_neutral": False,
                    # V7 consumes fixed business-scale thresholds. Both
                    # cross-sectional winsorization and standardization must be
                    # disabled so governed `value` equals the calculator output.
                    "standardize": False,
                },
                "group_count": 5,
                "cost_assumption": {"one_side_rate": 0.001},
                "data_version_id": DATA_VERSION_ID,
            })
        if task.get("status") != "completed":
            task = service.start_task(task_id, wait=True)
        artifact = store.resolve_artifact(factor_id)
        tasks.append({
            "factor_id": factor_id,
            "task_id": task_id,
            "task_status": task.get("status"),
            "report_id": task.get("report_id"),
            "artifact_id": artifact.get("artifact_id"),
            "artifact_status": artifact.get("status"),
            "artifact_start_date": artifact.get("start_date"),
            "artifact_end_date": artifact.get("end_date"),
            "artifact_row_count": artifact.get("row_count"),
            "error": task.get("error"),
        })
        if task.get("status") != "completed" or artifact.get("status") != "ready":
            break
    print(json.dumps({**preview, "status": "completed", "tasks": tasks}, ensure_ascii=False, indent=2))


def _pilot_symbols(path: Path, limit: int) -> list[str]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT DISTINCT p.symbol FROM market_daily_prices p
            WHERE p.adjustment='qfq' AND p.trade_date BETWEEN '2023-01-03' AND '2024-12-31'
              AND EXISTS (
                  SELECT 1 FROM security_master_intervals s
                  WHERE s.symbol=p.symbol AND s.is_active=1
                    AND s.valid_from<='2023-01-03'
                    AND COALESCE(s.valid_to,s.valid_from)>='2024-12-31'
                    AND s.risk_warning=0
              )
            ORDER BY p.symbol LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    eligible = [
        str(row["symbol"])
        for row in rows
        if not str(row["symbol"]).startswith(EXCLUDED_PREFIXES)
    ]
    return eligible[:limit]


if __name__ == "__main__":
    main()
