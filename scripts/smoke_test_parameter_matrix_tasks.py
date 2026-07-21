"""Smoke test for stage 44 parameter matrix task execution."""

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
    matrix_path = Path("var/runtime/parameter_matrix_tasks.json")
    index_path = Path("var/runtime/backtest_experiment_index.json")
    original_matrix = matrix_path.read_text(encoding="utf-8") if matrix_path.exists() else None
    original_index = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        status, payload = _dispatch(
            app,
            "POST",
            "/api/backtest/parameter-matrix-tasks",
            {
                "task_id": "stage44-matrix-smoke",
                "run_id_prefix": "stage44-matrix",
                "strategy_name": "moving_average_strategy",
                "strategy_id": "moving_average_strategy",
                "strategy_version": "v1",
                "symbol": "000001.XSHE",
                "benchmark": "000300.XSHG",
                "start_date": "2020-01-01",
                "end_date": "2020-01-10",
                "base_parameters": {"position_size": 1.0},
                "parameter_grid": {"short_window": [2, 3], "long_window": [4, 5]},
                "max_runs": 4,
            },
        )
        task = payload.get("task", {})
        if status != 200 or task.get("status") != "draft_ready" or len(task.get("planned_combinations", [])) != 4:
            raise SystemExit("stage44 smoke failed: matrix task not created")

        status, payload = _dispatch(app, "POST", "/api/backtest/parameter-matrix-tasks/stage44-matrix-smoke/run", {})
        result = payload.get("result", {})
        rows = result.get("rows", [])
        if status != 200 or result.get("status") != "completed" or result.get("completed_count") != 4 or len(rows) != 4:
            raise SystemExit("stage44 smoke failed: matrix task run invalid")
        if rows[0].get("rank") != 1 or not result.get("best_run_id") or not result.get("best_parameters"):
            raise SystemExit("stage44 smoke failed: matrix ranking invalid")
        scores = [row.get("score") for row in rows]
        if scores != sorted(scores, reverse=True):
            raise SystemExit("stage44 smoke failed: matrix rows not sorted")

        status, payload = _dispatch(app, "GET", "/api/backtest/parameter-matrix-tasks/stage44-matrix-smoke")
        if status != 200 or payload.get("task", {}).get("last_execution", {}).get("best_run_id") != result.get("best_run_id"):
            raise SystemExit("stage44 smoke failed: task detail missing execution")

        status, payload = _dispatch(app, "GET", "/api/backtest/experiments/index/stage44-matrix")
        experiment = payload.get("experiment", {})
        if status != 200 or experiment.get("primary_run_id") != result.get("best_run_id") or "parameter_matrix" not in experiment.get("tags", []):
            raise SystemExit("stage44 smoke failed: experiment index invalid")

        status, payload = _dispatch(app, "GET", "/api/backtest/results/stage44-matrix/portfolio-panel")
        portfolio = payload.get("result", {})
        if status != 200 or portfolio.get("summary", {}).get("run_count") != 4:
            raise SystemExit("stage44 smoke failed: portfolio panel invalid")

        print("stage44 parameter matrix smoke test passed")
    finally:
        if original_matrix is None:
            if matrix_path.exists():
                matrix_path.unlink()
        else:
            matrix_path.parent.mkdir(parents=True, exist_ok=True)
            matrix_path.write_text(original_matrix, encoding="utf-8")
        if original_index is None:
            if index_path.exists():
                index_path.unlink()
        else:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(original_index, encoding="utf-8")


if __name__ == "__main__":
    main()
