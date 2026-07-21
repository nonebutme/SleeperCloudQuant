"""Smoke test for stage 61 independent-capital concurrent screening."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from _project_bootstrap import ensure_project_root_on_sys_path


class FakeMarketDataService:
    def list_a_share_symbols(self, *, market: str, limit: int, offset: int):
        rows = [
            {"symbol": "000001", "rqalpha_symbol": "000001.XSHE", "name": "一号", "market": "SZSE", "listing_status": "current"},
            {"symbol": "000002", "rqalpha_symbol": "000002.XSHE", "name": "二号", "market": "SZSE", "listing_status": "current"},
            {"symbol": "600000", "rqalpha_symbol": "600000.XSHG", "name": "三号", "market": "SSE", "listing_status": "current"},
            {"symbol": "600001", "rqalpha_symbol": "600001.XSHG", "name": "历史", "market": "SSE", "listing_status": "historical_or_unlisted"},
        ]
        if market:
            rows = [row for row in rows if row["market"] == market]
        page = rows[offset : offset + limit]
        return {"total": len(rows), "items": page}


class FakeRuntimeStore:
    def fetch_backtest_trades(self, run_id: str):
        if run_id.endswith("000002"):
            return []
        return [{"side": "BUY", "quantity": 100, "price": 10.0}]


class FakeBacktestService:
    def __init__(self) -> None:
        self.attempts: dict[str, int] = {}

    def run_once(self, request):
        symbol = request.symbol.split(".", 1)[0]
        self.attempts[symbol] = self.attempts.get(symbol, 0) + 1
        if symbol == "600000" and self.attempts[symbol] == 1:
            raise RuntimeError("retry probe")
        total_return = {"000001": 0.20, "000002": -0.50, "600000": 0.10}[symbol]
        return SimpleNamespace(metrics={"total_returns": total_return, "annualized_returns": total_return})


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.services import IndependentScreeningService, StrategyService

    token = uuid4().hex
    strategy_service = StrategyService(
        Path("tmp") / f"stage61-strategy-{token}.sqlite3",
        legacy_drafts_path=Path("tmp") / "missing-stage61-drafts.json",
    )
    backtest_service = FakeBacktestService()
    service = IndependentScreeningService(
        backtest_service,
        FakeMarketDataService(),
        strategy_service,
        FakeRuntimeStore(),
        Path("tmp") / f"stage61-screening-{token}.sqlite3",
    )
    task = service.create_task(
        task_id="stage61-screening-smoke",
        name="阶段61独立选股 smoke",
        strategy_id="buy_and_hold",
        strategy_version="v1",
        symbols=[],
        market="",
        start_date="2026-01-01",
        end_date="2026-01-31",
        adjustment="qfq",
        benchmark="000300.XSHG",
        initial_cash=100_000,
        parameters={"position_size": 0.5},
        max_workers=3,
        retry_count=1,
        symbol_limit=0,
    )
    if task["progress"]["total"] != 3 or task["config"]["source_sha256"] == "":
        raise SystemExit("stage61 smoke failed: current universe/hash snapshot invalid")

    completed = service.start_task(task["task_id"], wait=True)
    progress = completed["progress"]
    if completed["status"] != "completed" or progress["entered"] != 2 or progress["no_entry"] != 1 or progress["failed"] != 0:
        raise SystemExit("stage61 smoke failed: screening funnel mismatch")
    if backtest_service.attempts.get("600000") != 2:
        raise SystemExit("stage61 smoke failed: retry did not execute")
    summary = completed["summary"]
    if summary["statistics_scope"] != "entered_symbols_only" or summary["performance"]["average_total_returns"] != 0.15:
        raise SystemExit("stage61 smoke failed: entered-only statistics mismatch")
    entered = service.list_items(task["task_id"], entered_only=True, limit=10)["items"]
    if {item["symbol"] for item in entered} != {"000001", "600000"}:
        raise SystemExit("stage61 smoke failed: entered item filter mismatch")
    restarted = IndependentScreeningService(
        backtest_service,
        FakeMarketDataService(),
        strategy_service,
        FakeRuntimeStore(),
        service._database_path,
    )
    if restarted.get_task(task["task_id"])["status"] != "completed":
        raise SystemExit("stage61 smoke failed: task persistence mismatch")

    print("stage61 independent screening backtest smoke test passed")


if __name__ == "__main__":
    main()
