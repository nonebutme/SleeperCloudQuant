"""Smoke test for stage 41 experiment review package flow."""

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
                "task_id": "stage41-review-smoke",
                "strategy_id": "moving_average_strategy",
                "strategy_version": "v1",
                "name": "stage41 experiment review smoke",
                "symbols": ["000001.XSHE", "000002.XSHE"],
                "start_date": "2020-01-01",
                "end_date": "2020-01-10",
                "benchmark": "000300.XSHG",
                "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
            },
        )
        if status != 200 or payload.get("task", {}).get("status") != "draft_ready":
            raise SystemExit("stage41 smoke failed: task not created")

        status, payload = _dispatch(app, "POST", "/api/backtest/research-tasks/stage41-review-smoke/run", {"run_id_prefix": "stage41-review", "initial_cash": 1000000})
        result = payload.get("result", {})
        if status != 200 or result.get("status") != "completed" or result.get("run_id_prefix") != "stage41-review":
            raise SystemExit("stage41 smoke failed: research task run invalid")

        status, payload = _dispatch(app, "POST", "/api/reporting/experiments/stage41-review/review-package", {"title": "Stage 41 review package", "create_package": True})
        review = payload.get("review", {})
        if status != 200 or review.get("status") != "review_ready":
            raise SystemExit("stage41 smoke failed: review not ready")
        if review.get("primary_run_id") != "stage41-review-001":
            raise SystemExit("stage41 smoke failed: primary run mismatch")
        package = review.get("report_package", {})
        if not package.get("package_id") or not package.get("manifest"):
            raise SystemExit("stage41 smoke failed: report package missing")
        if "html" not in review.get("export_links", {}) or "strategy_evaluation" not in review.get("review_links", {}):
            raise SystemExit("stage41 smoke failed: review links missing")
        if not review.get("strategy_evaluation") or not review.get("run_detail"):
            raise SystemExit("stage41 smoke failed: report analysis payload missing")

        package_id = package.get("package_id")
        status, payload = _dispatch(app, "GET", f"/api/reporting/report-packages/{package_id}/export?format=html")
        exported = payload.get("export", {})
        if status != 200 or "Stage 41 review package" not in exported.get("content", ""):
            raise SystemExit("stage41 smoke failed: review package export invalid")

        print("stage41 experiment review package smoke test passed")
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
