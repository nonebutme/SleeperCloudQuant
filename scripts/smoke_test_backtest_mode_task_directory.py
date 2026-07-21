"""Smoke verification for the Stage 66 dual-mode backtest task directory."""

from __future__ import annotations

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.api.backtest import list_backtest_mode_tasks
from app.schemas.backtest import BacktestModeTaskDirectoryQueryPayload


class _TaskService:
    def __init__(self, tasks: list[dict[str, object]]) -> None:
        self._tasks = tasks

    def list_tasks(self, *, limit: int = 50) -> list[dict[str, object]]:
        return self._tasks[:limit]


def main() -> None:
    independent = {
        "task_id": "stage66-screening",
        "status": "completed",
        "config": {
            "name": "全市场独立选股",
            "strategy_id": "distribution_strategy",
            "strategy_version": "v3",
            "source_sha256": "screening-sha",
            "date_window": {"start_date": "2020-01-01", "end_date": "2020-12-31"},
            "adjustment": "qfq",
        },
        "progress": {"total": 3, "processed": 3, "entered": 2, "failed": 0, "percent": 100.0},
        "created_at": "2026-07-20T09:00:00+08:00",
        "updated_at": "2026-07-21T09:00:00+08:00",
    }
    shared = {
        "task_id": "stage66-portfolio",
        "status": "partial_completed",
        "config": {
            "name": "共享资金池组合",
            "strategy_id": "portfolio_strategy",
            "strategy_version": "v2",
            "source_sha256": "portfolio-sha",
            "date_window": {"start_date": "2021-01-01", "end_date": "2021-12-31"},
            "adjustment": "raw",
        },
        "universe_count": 2,
        "run_id": "stage66-portfolio-run",
        "summary": {"excluded": [{"symbol": "000002.XSHE"}]},
        "created_at": "2026-07-20T10:00:00+08:00",
        "updated_at": "2026-07-21T10:00:00+08:00",
    }
    independent_service = _TaskService([independent])
    portfolio_service = _TaskService([shared])

    response = list_backtest_mode_tasks(
        independent_service,
        portfolio_service,
        BacktestModeTaskDirectoryQueryPayload(limit=20),
    )
    assert response.summary["task_count"] == 2
    assert response.summary["mode_counts"] == {
        "shared-portfolio": 1,
        "independent-screening": 1,
    }
    assert response.tasks[0]["task_id"] == "stage66-portfolio"
    assert response.tasks[0]["progress"]["percent"] == 100.0
    assert response.tasks[0]["links"]["report"].endswith("/shared-portfolio/stage66-portfolio")

    filtered = list_backtest_mode_tasks(
        independent_service,
        portfolio_service,
        BacktestModeTaskDirectoryQueryPayload(
            mode="independent-screening",
            status="completed",
            strategy_id="distribution_strategy",
            search="全市场",
        ),
    )
    assert len(filtered.tasks) == 1
    task = filtered.tasks[0]
    assert task["strategy_binding"]["strategy_version"] == "v3"
    assert task["strategy_binding"]["source_sha256"] == "screening-sha"
    assert task["progress"] == {
        "processed": 3,
        "total": 3,
        "percent": 100.0,
        "entered": 2,
        "failed": 0,
        "canceled": 0,
        "elapsed_seconds": 0.0,
        "throughput_per_minute": 0.0,
        "estimated_remaining_seconds": None,
    }
    assert task["links"]["run"].endswith("/independent-screening-tasks/stage66-screening/run")
    assert task["links"]["report"].endswith("/independent-screening/stage66-screening")

    no_match = list_backtest_mode_tasks(
        independent_service,
        portfolio_service,
        BacktestModeTaskDirectoryQueryPayload(search="missing-task"),
    )
    assert no_match.tasks == []
    assert no_match.summary["task_count"] == 0
    print("Stage 66 dual-mode backtest task directory smoke test passed.")


if __name__ == "__main__":
    main()