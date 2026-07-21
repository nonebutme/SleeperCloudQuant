"""Stage 67 smoke test for bounded full-market screening scheduling."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from _project_bootstrap import ensure_project_root_on_sys_path


class FakeMarketDataService:
    def list_a_share_symbols(self, *, market: str, limit: int, offset: int):
        rows = [
            {
                "symbol": f"{index:06d}",
                "rqalpha_symbol": f"{index:06d}.XSHE",
                "name": f"股票{index}",
                "market": "SZSE",
                "listing_status": "current",
            }
            for index in range(1, 13)
        ]
        page = rows[offset : offset + limit]
        return {"total": len(rows), "items": page}


class FakeRuntimeStore:
    def fetch_backtest_trades(self, run_id: str):
        return [{"side": "BUY", "quantity": 100, "price": 10.0}]


class BlockingBacktestService:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.lock = threading.Lock()

    def run_once(self, request):
        with self.lock:
            self.calls += 1
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("stage67 scheduler release timeout")
        time.sleep(0.02)
        return SimpleNamespace(
            metrics={"total_returns": 0.1, "annualized_returns": 0.1}
        )


def wait_for(service, task_id: str, status: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = service.get_task(task_id)
        if task["status"] == status:
            return task
        time.sleep(0.02)
    raise SystemExit(
        f"stage67 smoke failed: task {task_id} did not reach {status}"
    )


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.services import IndependentScreeningService, StrategyService

    token = uuid4().hex
    strategy_service = StrategyService(
        Path("tmp") / f"stage67-strategy-{token}.sqlite3",
        legacy_drafts_path=Path("tmp") / "missing-stage67-drafts.json",
    )
    backtest_service = BlockingBacktestService()
    service = IndependentScreeningService(
        backtest_service,
        FakeMarketDataService(),
        strategy_service,
        FakeRuntimeStore(),
        Path("tmp") / f"stage67-screening-{token}.sqlite3",
    )
    task = service.create_task(
        task_id="stage67-bounded-scheduler",
        name="阶段67有界调度",
        strategy_id="buy_and_hold",
        strategy_version="v1",
        symbols=[],
        market="",
        start_date="2026-01-01",
        end_date="2026-01-31",
        adjustment="raw",
        benchmark="000300.XSHG",
        initial_cash=100_000,
        parameters={"position_size": 0.5},
        max_workers=2,
        retry_count=0,
        symbol_limit=0,
        scheduler_batch_size=4,
    )
    assert task["progress"]["total"] == 12
    assert task["execution"] == {
        "scheduler": "bounded_dynamic_batches",
        "requested_workers": 2,
        "effective_workers": 2,
        "batch_size": 4,
    }

    service.start_task(task["task_id"])
    if not backtest_service.started.wait(timeout=2):
        raise SystemExit("stage67 smoke failed: scheduler did not start")
    requested = service.control_task(task["task_id"], "pause")
    assert requested["status"] == "pause_requested"
    backtest_service.release.set()
    paused = wait_for(service, task["task_id"], "paused")
    while service._threads[task["task_id"]].is_alive():
        time.sleep(0.01)
    assert paused["progress"]["processed"] == 4
    assert paused["progress"]["remaining"] == 8
    assert backtest_service.calls == 4

    completed = service.start_task(task["task_id"], wait=True)
    assert completed["status"] == "completed"
    assert completed["progress"]["processed"] == 12
    assert completed["progress"]["entered"] == 12
    assert completed["progress"]["throughput_per_minute"] > 0
    assert completed["progress"]["estimated_remaining_seconds"] is None

    canceled_task = service.create_task(
        task_id="stage67-cancel-ready",
        name="阶段67取消",
        strategy_id="buy_and_hold",
        strategy_version="v1",
        symbols=[],
        market="",
        start_date="2026-01-01",
        end_date="2026-01-31",
        adjustment="raw",
        benchmark="000300.XSHG",
        initial_cash=100_000,
        parameters={},
        max_workers=0,
        retry_count=0,
        symbol_limit=5,
        scheduler_batch_size=0,
    )
    canceled = service.control_task(canceled_task["task_id"], "cancel")
    assert canceled["status"] == "canceled"
    assert canceled["progress"]["canceled"] == 5
    assert canceled["progress"]["percent"] == 100.0
    assert canceled["summary"] == {}

    print("stage67 full-market backtest scheduler smoke test passed")


if __name__ == "__main__":
    main()