"""Smoke test for stage 39 result pagination, exports, and experiment grouping."""

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
    original_tasks = task_path.read_text(encoding="utf-8") if task_path.exists() else None
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        status, payload = _dispatch(
            app,
            "POST",
            "/api/backtest/research-tasks",
            {
                "task_id": "stage39-export-smoke",
                "strategy_id": "moving_average_strategy",
                "strategy_version": "v1",
                "name": "stage39 pagination export smoke",
                "symbols": ["000001.XSHE", "000002.XSHE"],
                "start_date": "2020-01-01",
                "end_date": "2020-01-10",
                "benchmark": "000300.XSHG",
                "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
            },
        )
        if status != 200 or payload.get("task", {}).get("status") != "draft_ready":
            raise SystemExit("stage39 smoke failed: task not created")

        status, payload = _dispatch(app, "POST", "/api/backtest/research-tasks/stage39-export-smoke/run", {"run_id_prefix": "stage39-export", "initial_cash": 1000000})
        result = payload.get("result", {})
        if status != 200 or result.get("status") != "completed" or result.get("run_count") != 2:
            raise SystemExit("stage39 smoke failed: task run invalid")

        status, payload = _dispatch(app, "GET", "/api/backtest/results/stage39-export-001/table?table=trades&offset=0&limit=2&export_format=json")
        table = payload.get("result", {})
        if status != 200 or table.get("table") != "trades" or table.get("limit") != 2 or len(table.get("rows", [])) > 2:
            raise SystemExit("stage39 smoke failed: paginated table invalid")
        if table.get("total", 0) < len(table.get("rows", [])) or "has_next" not in table:
            raise SystemExit("stage39 smoke failed: pagination metadata missing")

        status, payload = _dispatch(app, "GET", "/api/backtest/results/stage39-export-001/table?table=trades&offset=0&limit=2&export_format=csv")
        export = payload.get("result", {})
        if status != 200 or export.get("content_type") != "text/csv" or "trade_time" not in str(export.get("content")):
            raise SystemExit("stage39 smoke failed: csv export invalid")

        status, payload = _dispatch(app, "GET", "/api/backtest/experiments/stage39-export/panel")
        experiment = payload.get("result", {})
        if status != 200 or experiment.get("summary", {}).get("run_count") != 2 or len(experiment.get("rows", [])) != 2:
            raise SystemExit("stage39 smoke failed: experiment panel invalid")
        if experiment.get("portfolio_panel_path") != "/api/backtest/results/stage39-export/portfolio-panel":
            raise SystemExit("stage39 smoke failed: portfolio panel path invalid")
        print("stage39 result pagination/export smoke test passed")
    finally:
        if original_tasks is None:
            if task_path.exists():
                task_path.unlink()
        else:
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(original_tasks, encoding="utf-8")


if __name__ == "__main__":
    main()

