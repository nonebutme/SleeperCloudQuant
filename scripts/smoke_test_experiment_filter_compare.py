"""Smoke test for stage 42 experiment filtering, tagging, and comparison."""

from __future__ import annotations

import json
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    path_only, _, query = path.partition("?")
    return dispatch_request(app, method=method, path=path_only, query_string=query, body=body)


def _create_and_run_task(app, task_id: str, prefix: str) -> None:
    status, payload = _dispatch(
        app,
        "POST",
        "/api/backtest/research-tasks",
        {
            "task_id": task_id,
            "strategy_id": "moving_average_strategy",
            "strategy_version": "v1",
            "name": f"{task_id} experiment",
            "symbols": ["000001.XSHE", "000002.XSHE"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-10",
            "benchmark": "000300.XSHG",
            "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
        },
    )
    if status != 200 or payload.get("task", {}).get("status") != "draft_ready":
        raise SystemExit(f"stage42 smoke failed: task {task_id} not created")
    status, payload = _dispatch(app, "POST", f"/api/backtest/research-tasks/{task_id}/run", {"run_id_prefix": prefix, "initial_cash": 1000000})
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit(f"stage42 smoke failed: task {task_id} not completed")


def main() -> None:
    ensure_project_root_on_sys_path()
    task_path = Path("var/runtime/strategy_research_tasks.json")
    index_path = Path("var/runtime/backtest_experiment_index.json")
    original_tasks = task_path.read_text(encoding="utf-8") if task_path.exists() else None
    original_index = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        _create_and_run_task(app, "stage42-filter-a", "stage42-filter-a")
        _create_and_run_task(app, "stage42-filter-b", "stage42-filter-b")

        status, payload = _dispatch(app, "GET", "/api/backtest/experiments?tag=research_task&search=stage42-filter")
        experiments = payload.get("experiments", [])
        if status != 200 or len(experiments) < 2 or payload.get("summary", {}).get("count", 0) < 2:
            raise SystemExit("stage42 smoke failed: filtered list invalid")

        status, payload = _dispatch(app, "POST", "/api/backtest/experiments/index/stage42-filter-a/update", {"status": "reviewed", "tags": ["reviewed", "candidate"], "review_note": "stage42 smoke"})
        updated = payload.get("experiment", {})
        if status != 200 or updated.get("status") != "reviewed" or "candidate" not in updated.get("tags", []):
            raise SystemExit("stage42 smoke failed: update invalid")

        status, payload = _dispatch(app, "GET", "/api/backtest/experiments?tag=candidate&status=reviewed")
        if status != 200 or not any(item.get("experiment_id") == "stage42-filter-a" for item in payload.get("experiments", [])):
            raise SystemExit("stage42 smoke failed: tag/status filter invalid")

        status, payload = _dispatch(app, "POST", "/api/backtest/experiments/compare", {"experiment_ids": ["stage42-filter-a", "stage42-filter-b"]})
        result = payload.get("result", {})
        if status != 200 or result.get("status") != "ready" or result.get("matched_count") != 2 or not result.get("best_experiment_id"):
            raise SystemExit("stage42 smoke failed: compare invalid")
        if not all("review_link" in row for row in result.get("rows", [])):
            raise SystemExit("stage42 smoke failed: compare review links missing")

        status, payload = _dispatch(app, "POST", "/api/backtest/experiments/index/stage42-filter-b/update", {"archived": True})
        if status != 200 or payload.get("experiment", {}).get("status") != "archived":
            raise SystemExit("stage42 smoke failed: archive invalid")

        status, payload = _dispatch(app, "GET", "/api/backtest/experiments?search=stage42-filter-b")
        if status != 200 or payload.get("experiments"):
            raise SystemExit("stage42 smoke failed: archived experiment should be hidden by default")
        status, payload = _dispatch(app, "GET", "/api/backtest/experiments?search=stage42-filter-b&include_archived=true")
        if status != 200 or not payload.get("experiments"):
            raise SystemExit("stage42 smoke failed: archived include filter invalid")

        print("stage42 experiment filter/tag/compare smoke test passed")
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
