"""Smoke test for stage 40 experiment index and report links."""

from __future__ import annotations

import json
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    path_only, _, query = path.partition("?")
    return dispatch_request(app, method=method, path=path_only, query_string=query, body=body)


def main() -> None:
    ensure_project_root_on_sys_path()
    task_path = Path("var/runtime/strategy_research_tasks.json")
    index_path = Path("var/runtime/backtest_experiment_index.json")
    original_tasks = task_path.read_text(encoding="utf-8") if task_path.exists() else None
    original_index = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        status, payload = _dispatch(
            app,
            "POST",
            "/api/backtest/research-tasks",
            {
                "task_id": "stage40-index-smoke",
                "strategy_id": "moving_average_strategy",
                "strategy_version": "v1",
                "name": "stage40 experiment index smoke",
                "symbols": ["000001.XSHE", "000002.XSHE"],
                "start_date": "2020-01-01",
                "end_date": "2020-01-10",
                "benchmark": "000300.XSHG",
                "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
            },
        )
        if status != 200 or payload.get("task", {}).get("status") != "draft_ready":
            raise SystemExit("stage40 smoke failed: task not created")

        status, payload = _dispatch(app, "POST", "/api/backtest/research-tasks/stage40-index-smoke/run", {"run_id_prefix": "stage40-index", "initial_cash": 1000000})
        result = payload.get("result", {})
        if status != 200 or result.get("status") != "completed" or result.get("run_id_prefix") != "stage40-index":
            raise SystemExit("stage40 smoke failed: task run invalid")

        status, payload = _dispatch(app, "GET", "/api/backtest/experiments")
        experiments = payload.get("experiments", [])
        indexed = next((item for item in experiments if item.get("experiment_id") == "stage40-index"), None)
        if status != 200 or indexed is None:
            raise SystemExit("stage40 smoke failed: auto index missing")
        links = indexed.get("report_links", {})
        if links.get("portfolio_panel") != "/api/backtest/results/stage40-index/portfolio-panel" or "strategy_evaluation" not in links:
            raise SystemExit("stage40 smoke failed: report links missing")

        status, payload = _dispatch(app, "GET", "/api/backtest/experiments/index/stage40-index")
        if status != 200 or payload.get("experiment", {}).get("primary_run_id") != "stage40-index-001":
            raise SystemExit("stage40 smoke failed: index detail invalid")

        status, payload = _dispatch(app, "POST", "/api/backtest/experiments", {"experiment_id": "stage40-manual", "run_id_prefix": "stage40-index", "name": "manual stage40", "tags": ["manual", "stage40"], "primary_run_id": "stage40-index-001"})
        manual = payload.get("experiment", {})
        if status != 200 or manual.get("experiment_id") != "stage40-manual" or "trades_export_csv" not in manual.get("report_links", {}):
            raise SystemExit("stage40 smoke failed: manual index invalid")
        print("stage40 experiment index smoke test passed")
    finally:
        if original_tasks is None:
            if task_path.exists():
                task_path.unlink()
        else:
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(original_tasks, encoding="utf-8")
        if original_index is None:
            if index_path.exists():
                index_path.unlink()
        else:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(original_index, encoding="utf-8")


if __name__ == "__main__":
    main()
