"""Smoke test for stage 35 running a research task through the backtest engine."""

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
                "task_id": "stage35-run-smoke",
                "strategy_id": "moving_average_strategy",
                "strategy_version": "v1",
                "name": "阶段35研究任务执行 smoke",
                "symbols": ["000001.XSHE"],
                "start_date": "2020-01-01",
                "end_date": "2020-01-10",
                "benchmark": "000300.XSHG",
                "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
            },
        )
        if status != 200 or payload.get("task", {}).get("status") != "draft_ready":
            raise SystemExit("stage35 smoke failed: research task not created")

        status, payload = _dispatch(app, "POST", "/api/backtest/research-tasks/stage35-run-smoke/run", {"run_id_prefix": "stage35-smoke", "initial_cash": 1000000})
        result = payload.get("result", {})
        if status != 200 or result.get("status") != "completed" or result.get("run_count") != 1:
            raise SystemExit("stage35 smoke failed: research task run did not complete")
        rows = result.get("results", [])
        metrics = rows[0].get("metrics", {}) if rows else {}
        if not rows or rows[0].get("run_id") != "stage35-smoke-001" or "total_returns" not in metrics or "max_drawdown" not in metrics:
            raise SystemExit("stage35 smoke failed: result metrics or run_id invalid")
        if rows[0].get("trade_artifacts", {}).get("reporting_run_id") != "stage35-smoke-001":
            raise SystemExit("stage35 smoke failed: trade artifact binding missing")

        status, payload = _dispatch(app, "GET", "/api/backtest/research-tasks/stage35-run-smoke")
        task = payload.get("task", {})
        if status != 200 or task.get("status") != "backtest_completed" or task.get("last_execution", {}).get("run_ids") != ["stage35-smoke-001"]:
            raise SystemExit("stage35 smoke failed: research task detail missing execution binding")
        print("stage35 research task backtest run smoke test passed")
    finally:
        if original_tasks is None:
            if task_path.exists():
                task_path.unlink()
        else:
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(original_tasks, encoding="utf-8")


if __name__ == "__main__":
    main()