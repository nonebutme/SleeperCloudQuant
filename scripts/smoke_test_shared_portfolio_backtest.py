"""Smoke test for Stage 62 shared-cash portfolio backtests."""

from __future__ import annotations

import os
import time
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from app.services.shared_portfolio_service import SharedPortfolioService
    from app.services.strategy_service import StrategyService

    suffix = f"{os.getpid()}_{time.time_ns()}"
    runtime_store = SqliteRuntimeStore(Path("tmp") / f"shared_portfolio_runtime_{suffix}.sqlite3")
    strategy_service = StrategyService(Path("tmp") / f"shared_portfolio_strategies_{suffix}.sqlite3")
    strategy = strategy_service.save_version(
        strategy_id=f"stage62_rotation_{suffix}",
        name="Stage 62 rotation smoke",
        source_code='''def generate_target_weights(bars, parameters):
    return [1.0 if index in (0, 1) else 0.0 for index in range(len(bars))]
''',
        parameters={},
    )
    service = SharedPortfolioService(
        FakeCanonicalMarketService(),
        strategy_service,
        runtime_store,
        Path("tmp") / f"shared_portfolio_tasks_{suffix}.sqlite3",
    )
    task = service.create_task(
        task_id=f"stage62-smoke-{suffix}",
        name="Stage 62 shared account",
        strategy_id=strategy["strategy_id"],
        strategy_version=strategy["latest_version"],
        symbols=["000001", "600000"],
        market="",
        start_date="2020-01-02",
        end_date="2020-01-07",
        adjustment="raw",
        benchmark="000300.XSHG",
        initial_cash=100_000,
        parameters={},
        max_workers=1,
        symbol_limit=0,
        max_positions=2,
        portfolio_exposure=0.9,
        commission_rate=0.0003,
        min_commission=5,
        tax_rate=0.001,
        slippage_rate=0.0005,
    )
    service.start_task(task["task_id"], wait=False)
    observed_intermediate = False
    for _ in range(80):
        snapshot = service.get_task(task["task_id"])
        progress = snapshot.get("progress") or {}
        if snapshot.get("status") == "running" and 0 < int(progress.get("processed") or 0) < int(progress.get("total") or 0):
            observed_intermediate = True
            break
        if snapshot.get("status") in {"completed", "partial_completed", "failed"}:
            break
        time.sleep(0.02)
    completed = service.start_task(task["task_id"], wait=True)
    if not observed_intermediate:
        raise SystemExit("shared portfolio smoke failed: no intermediate stock progress was observable")
    final_progress = completed.get("progress") or {}
    if int(final_progress.get("processed") or 0) != 2 or float(final_progress.get("percent") or 0) != 100.0:
        raise SystemExit(f"shared portfolio smoke failed: final progress mismatch: {final_progress}")
    if completed["status"] != "completed":
        raise SystemExit(f"shared portfolio smoke failed: {completed}")
    run_id = completed["run_id"]
    run = runtime_store.fetch_backtest_run(run_id)
    accounts = list(runtime_store.fetch_backtest_accounts(run_id))
    trades = list(runtime_store.fetch_backtest_trades(run_id))
    positions = list(runtime_store.fetch_backtest_positions(run_id))
    yearly_returns = list(runtime_store.fetch_backtest_yearly_returns(run_id))
    metrics = {
        row["metric_name"]: row.get("metric_value") if row.get("metric_value") is not None else row.get("metric_text")
        for row in runtime_store.fetch_backtest_metrics(run_id)
    }
    if run is None or run["status"] != "completed":
        raise SystemExit("shared portfolio smoke failed: standard run was not persisted")
    if len(accounts) != 4 or not trades or not any(str(row["side"]).upper() == "SELL" for row in trades):
        raise SystemExit("shared portfolio smoke failed: account/trade artifacts missing")
    if min(float(row["cash"]) for row in accounts) < -0.01:
        raise SystemExit("shared portfolio smoke failed: shared cash became negative")
    if any(float(row["quantity"]) % 100 for row in trades):
        raise SystemExit("shared portfolio smoke failed: non-board-lot trade detected")
    holdings_by_date: dict[str, set[str]] = {}
    for row in positions:
        holdings_by_date.setdefault(str(row["snapshot_time"]), set()).add(str(row["order_book_id"]))
    if any(len(symbols) > 2 for symbols in holdings_by_date.values()):
        raise SystemExit("shared portfolio smoke failed: max_positions exceeded")
    if completed["summary"].get("statistics_scope") != "single_shared_account":
        raise SystemExit("shared portfolio smoke failed: aggregation scope mismatch")
    sell_count = sum(1 for row in trades if str(row.get("side") or "").upper() == "SELL")
    if int(metrics.get("trade_count") or 0) != sell_count or int(metrics.get("trade_fill_count") or 0) != len(trades):
        raise SystemExit("shared portfolio smoke failed: realized trade/fill counts are inconsistent")
    if metrics.get("benchmark_return") is None or metrics.get("excess_return") is None:
        raise SystemExit("shared portfolio smoke failed: aligned benchmark metrics missing")
    if not yearly_returns or yearly_returns[0].get("benchmark_return") in (None, 0.0):
        raise SystemExit("shared portfolio smoke failed: yearly benchmark return is not real")
    raw_result = dict(run.get("raw_result") or {})
    if len(raw_result.get("benchmark_curve") or []) != len(accounts) or len(raw_result.get("excess_curve") or []) != len(accounts):
        raise SystemExit("shared portfolio smoke failed: benchmark/excess curves are not aligned")
    raw_positions = raw_result.get("positions") or []
    if raw_positions and not all(row.get("avg_price") is not None and row.get("weight") is not None for row in raw_positions):
        raise SystemExit("shared portfolio smoke failed: position cost/weight evidence missing")
    print("shared portfolio backtest smoke test passed")


class FakeCanonicalMarketService:
    def list_a_share_symbols(self, *, market: str = "", limit: int = 100, offset: int = 0):
        rows = [
            {"symbol": "000001", "rqalpha_symbol": "000001.XSHE", "name": "Ping An Bank", "market": "SZSE", "listing_status": "current"},
            {"symbol": "600000", "rqalpha_symbol": "600000.XSHG", "name": "Pudong Bank", "market": "SSE", "listing_status": "current"},
        ]
        page = rows[offset : offset + limit]
        return {"status": "ready", "total": len(rows), "items": page}

    def get_a_share_price_history(self, *, symbol: str, adjustment: str, start_date: str, end_date: str):
        time.sleep(0.12)
        base = 10.0 if symbol == "000001" else 20.0
        return [
            {"date": date, "open": base + index, "high": base + index + 0.5, "low": base + index - 0.5, "close": base + index, "volume": 1_000_000}
            for index, date in enumerate(("2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"))
        ]


if __name__ == "__main__":
    main()
