"""Synthetic orchestration benchmark for the Stage 67 bounded scheduler."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from _project_bootstrap import ensure_project_root_on_sys_path


class BenchmarkMarketDataService:
    def __init__(self, count: int) -> None:
        self.count = count

    def list_a_share_symbols(self, *, market: str, limit: int, offset: int):
        end = min(offset + limit, self.count)
        rows = [
            {
                "symbol": f"{index:06d}",
                "rqalpha_symbol": f"{index:06d}.XSHE",
                "name": f"Benchmark {index}",
                "market": "SZSE",
                "listing_status": "current",
            }
            for index in range(offset + 1, end + 1)
        ]
        return {"total": self.count, "items": rows}


class BenchmarkRuntimeStore:
    def fetch_backtest_trades(self, run_id: str):
        return [{"side": "BUY", "quantity": 100}]


class BenchmarkBacktestService:
    def run_once(self, request):
        return SimpleNamespace(
            metrics={"total_returns": 0.01, "annualized_returns": 0.01}
        )


def run_case(count: int) -> dict[str, float | int | str]:
    from app.services import IndependentScreeningService, StrategyService

    token = uuid4().hex
    strategy = StrategyService(
        Path("tmp") / f"stage67-benchmark-strategy-{token}.sqlite3",
        legacy_drafts_path=Path("tmp") / "missing-stage67-benchmark.json",
    )
    service = IndependentScreeningService(
        BenchmarkBacktestService(),
        BenchmarkMarketDataService(count),
        strategy,
        BenchmarkRuntimeStore(),
        Path("tmp") / f"stage67-benchmark-{count}-{token}.sqlite3",
    )
    started = time.perf_counter()
    task = service.create_task(
        task_id=f"stage67-benchmark-{count}",
        name=f"Stage 67 benchmark {count}",
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
        max_workers=8,
        retry_count=0,
        symbol_limit=0,
        scheduler_batch_size=32,
    )
    created = time.perf_counter()
    completed = service.start_task(task["task_id"], wait=True)
    finished = time.perf_counter()
    assert completed["status"] == "completed"
    assert completed["progress"]["processed"] == count
    execution_seconds = finished - created
    return {
        "symbols": count,
        "create_seconds": round(created - started, 4),
        "execute_seconds": round(execution_seconds, 4),
        "orchestration_symbols_per_second": round(
            count / execution_seconds if execution_seconds else 0.0, 2
        ),
        "workers": completed["execution"]["effective_workers"],
        "batch_size": completed["execution"]["batch_size"],
    }


def main() -> None:
    ensure_project_root_on_sys_path()
    results = [run_case(count) for count in (100, 1000, 5528)]
    print(json.dumps({"benchmark": "scheduler_only", "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()