"""Smoke test for stage 38 trade attribution and risk metrics."""

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
                "task_id": "stage38-risk-smoke",
                "strategy_id": "moving_average_strategy",
                "strategy_version": "v1",
                "name": "stage38 trade risk smoke",
                "symbols": ["000001.XSHE", "000002.XSHE"],
                "start_date": "2020-01-01",
                "end_date": "2020-01-10",
                "benchmark": "000300.XSHG",
                "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
            },
        )
        if status != 200 or payload.get("task", {}).get("status") != "draft_ready":
            raise SystemExit("stage38 smoke failed: research task not created")

        status, payload = _dispatch(
            app,
            "POST",
            "/api/backtest/research-tasks/stage38-risk-smoke/run",
            {"run_id_prefix": "stage38-risk", "initial_cash": 1000000},
        )
        result = payload.get("result", {})
        if status != 200 or result.get("status") != "completed" or result.get("run_count") != 2:
            raise SystemExit("stage38 smoke failed: research task run invalid")

        status, payload = _dispatch(app, "GET", "/api/backtest/results/stage38-risk-001/panel")
        panel = payload.get("result", {})
        if status != 200 or panel.get("status") != "completed":
            raise SystemExit("stage38 smoke failed: single panel invalid")
        for key in ("trade_attribution", "risk_metrics", "exposure_summary"):
            if key not in panel or not isinstance(panel[key], dict):
                raise SystemExit(f"stage38 smoke failed: {key} missing")
        if panel["trade_attribution"].get("trade_count") != panel.get("summary", {}).get("trade_count"):
            raise SystemExit("stage38 smoke failed: trade attribution count mismatch")
        if "max_drawdown" not in panel["risk_metrics"] or "holding_count" not in panel["exposure_summary"]:
            raise SystemExit("stage38 smoke failed: risk/exposure fields missing")

        status, payload = _dispatch(app, "GET", "/api/backtest/results/stage38-risk/portfolio-panel")
        portfolio = payload.get("result", {})
        if status != 200 or portfolio.get("summary", {}).get("run_count") != 2:
            raise SystemExit("stage38 smoke failed: portfolio panel invalid")
        if "trade_attribution" not in portfolio or "risk_metrics" not in portfolio:
            raise SystemExit("stage38 smoke failed: portfolio attribution/risk missing")
        if portfolio["trade_attribution"].get("trade_count", 0) <= 0:
            raise SystemExit("stage38 smoke failed: portfolio trade count invalid")
        print("stage38 trade attribution and risk metrics smoke test passed")
    finally:
        if original_tasks is None:
            if task_path.exists():
                task_path.unlink()
        else:
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(original_tasks, encoding="utf-8")


if __name__ == "__main__":
    main()
