"""Smoke test for stage 34 strategy research task model."""

from __future__ import annotations

import json
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    return dispatch_request(app, method=method, path=path, body=body)


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
                "task_id": "stage34-research-smoke",
                "strategy_id": "moving_average_strategy",
                "strategy_version": "v1",
                "name": "阶段34研究任务 smoke",
                "symbols": ["000001.XSHE", "600000.XSHG"],
                "start_date": "2020-01-01",
                "end_date": "2020-01-10",
                "benchmark": "000300.XSHG",
                "parameters": {"short_window": 3, "long_window": 6, "position_size": 0.8},
            },
        )
        task = payload.get("task", {})
        if status != 200 or task.get("status") != "draft_ready" or task.get("task_id") != "stage34-research-smoke":
            raise SystemExit("stage34 smoke failed: task not created")
        if task.get("parameters", {}).get("short_window") != 3 or not task.get("parameter_schema"):
            raise SystemExit("stage34 smoke failed: parameters/schema missing")
        if len(task.get("indicator_plan", [])) < 2 or len(task.get("signal_preview", [])) < 2:
            raise SystemExit("stage34 smoke failed: indicator plan or signal preview missing")
        if task.get("research_outputs", {}).get("ready_for_backtest") is not True:
            raise SystemExit("stage34 smoke failed: task not marked backtest-ready")

        status, payload = _dispatch(app, "GET", "/api/backtest/research-tasks")
        if status != 200 or "stage34-research-smoke" not in {item.get("task_id") for item in payload.get("tasks", [])}:
            raise SystemExit("stage34 smoke failed: task list missing created task")

        status, payload = _dispatch(app, "GET", "/api/backtest/research-tasks/stage34-research-smoke")
        if status != 200 or payload.get("task", {}).get("strategy_id") != "moving_average_strategy":
            raise SystemExit("stage34 smoke failed: task detail invalid")
        print("stage34 strategy research task smoke test passed")
    finally:
        if original_tasks is None:
            if task_path.exists():
                task_path.unlink()
        else:
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(original_tasks, encoding="utf-8")


if __name__ == "__main__":
    main()