"""Smoke test for Stage 62 shared-cash portfolio backtests."""

from __future__ import annotations

import os
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from app.services.shared_portfolio_service import SharedPortfolioService
    from app.services.strategy_service import StrategyService

    suffix = str(os.getpid())
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
        max_workers=2,
        symbol_limit=0,
        max_positions=2,
        portfolio_exposure=0.9,
        commission_rate=0.0003,
        min_commission=5,
        tax_rate=0.001,
        slippage_rate=0.0005,
    )
    completed = service.start_task(task["task_id"], wait=True)
    if completed["status"] != "completed":
        raise SystemExit(f"shared portfolio smoke failed: {completed}")
    run_id = completed["run_id"]
    run = runtime_store.fetch_backtest_run(run_id)
    accounts = list(runtime_store.fetch_backtest_accounts(run_id))
    trades = list(runtime_store.fetch_backtest_trades(run_id))
    positions = list(runtime_store.fetch_backtest_positions(run_id))
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
        base = 10.0 if symbol == "000001" else 20.0
        return [
            {"date": date, "open": base + index, "high": base + index + 0.5, "low": base + index - 0.5, "close": base + index, "volume": 1_000_000}
            for index, date in enumerate(("2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"))
        ]


if __name__ == "__main__":
    main()
