"""Smoke test for stage 37 portfolio-level backtest panel."""

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
                "task_id": "stage37-portfolio-smoke",
                "strategy_id": "moving_average_strategy",
                "strategy_version": "v1",
                "name": "阶段37组合面板 smoke",
                "symbols": ["000001.XSHE", "000002.XSHE"],
                "start_date": "2020-01-01",
                "end_date": "2020-01-10",
                "benchmark": "000300.XSHG",
                "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
            },
        )
        if status != 200 or payload.get("task", {}).get("status") != "draft_ready":
            raise SystemExit("stage37 smoke failed: research task not created")

        status, payload = _dispatch(app, "POST", "/api/backtest/research-tasks/stage37-portfolio-smoke/run", {"run_id_prefix": "stage37-portfolio", "initial_cash": 1000000})
        result = payload.get("result", {})
        if status != 200 or result.get("status") != "completed" or result.get("run_count") != 2:
            raise SystemExit("stage37 smoke failed: research task did not produce two runs")
        if result.get("run_id_prefix") != "stage37-portfolio":
            raise SystemExit("stage37 smoke failed: run_id_prefix missing")

        status, payload = _dispatch(app, "GET", "/api/backtest/results/stage37-portfolio/portfolio-panel")
        panel = payload.get("result", {})
        if status != 200 or panel.get("status") != "completed":
            raise SystemExit("stage37 smoke failed: portfolio panel not completed")
        if panel.get("summary", {}).get("run_count") != 2 or len(panel.get("rows", [])) != 2:
            raise SystemExit("stage37 smoke failed: portfolio rows invalid")
        metrics = panel.get("metrics", {})
        if "avg_total_returns" not in metrics or "worst_max_drawdown" not in metrics:
            raise SystemExit("stage37 smoke failed: aggregate metrics missing")
        if not isinstance(panel.get("equity_curve"), list) or not isinstance(panel.get("drawdown_curve"), list):
            raise SystemExit("stage37 smoke failed: curves missing")

        status, payload = _dispatch(app, "GET", "/api/backtest/results/stage37-portfolio-001/panel")
        single = payload.get("result", {})
        if status != 200 or "equity_curve" not in single or "drawdown_curve" not in single:
            raise SystemExit("stage37 smoke failed: single run curves missing")
        print("stage37 portfolio backtest panel smoke test passed")
    finally:
        if original_tasks is None:
            if task_path.exists():
                task_path.unlink()
        else:
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(original_tasks, encoding="utf-8")


if __name__ == "__main__":
    main()
