"""Smoke test real strategy-exposure IC and Q1-Q5 evidence construction."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


class FakeStrategyService:
    def resolve_version(self, strategy_id, strategy_version):
        return {
            "strategy_id": strategy_id,
            "latest_version": strategy_version or "v1",
            "source_sha256": "signal-analysis-smoke",
            "execution_contract": "daily_close",
        }


class FakeMarketDataService:
    def __init__(self) -> None:
        self.symbols = [f"00000{index}" for index in range(1, 6)]
        start = date(2026, 1, 5)
        self.dates = [(start + timedelta(days=index)).isoformat() for index in range(6)]

    def list_a_share_symbols(self, *, market, limit, offset):
        rows = [
            {
                "symbol": symbol,
                "rqalpha_symbol": f"{symbol}.XSHE",
                "name": symbol,
                "market": "SZSE",
                "listing_status": "current",
            }
            for symbol in self.symbols
        ]
        return {"total": len(rows), "items": rows[offset : offset + limit]}

    def get_a_share_daily_prices(
        self,
        *,
        symbol,
        adjustment,
        start_date,
        end_date,
        limit,
        offset,
    ):
        rank = int(str(symbol)[-1])
        closes = [100.0]
        for step in range(5):
            daily_return = (rank if step < 4 else 6 - rank) * 0.002
            closes.append(closes[-1] * (1.0 + daily_return))
        rows = [
            {"date": trade_date, "close": close}
            for trade_date, close in zip(self.dates, closes)
        ]
        rows.reverse()
        return {
            "status": "ready",
            "total": len(rows),
            "rows": rows[offset : offset + limit],
        }


class FakeRuntimeStore:
    def __init__(self, market: FakeMarketDataService) -> None:
        self.market = market

    @staticmethod
    def _symbol(run_id: str) -> str:
        return run_id.rsplit("-", 1)[-1]

    def fetch_backtest_positions(self, run_id):
        weight = int(self._symbol(run_id)[-1]) / 10.0
        return [
            {
                "snapshot_time": f"{trade_date}T15:00:00+08:00",
                "market_value": weight * 1_000_000,
            }
            for trade_date in self.market.dates
        ]

    def fetch_backtest_accounts(self, run_id):
        return [
            {
                "snapshot_time": f"{trade_date}T15:00:00+08:00",
                "total_value": 1_000_000,
            }
            for trade_date in self.market.dates
        ]


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.independent_screening_service import IndependentScreeningService

    database_path = Path("tmp/independent_signal_analysis_smoke.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{database_path}{suffix}")
        if candidate.exists():
            candidate.unlink()
    market = FakeMarketDataService()
    runtime = FakeRuntimeStore(market)
    service = IndependentScreeningService(
        None,
        market,
        FakeStrategyService(),
        runtime,
        database_path=database_path,
    )
    task_id = "signal-analysis-smoke"
    service.create_task(
        task_id=task_id,
        name="signal analysis smoke",
        strategy_id="moving_average_strategy",
        strategy_version="v1",
        symbols=market.symbols,
        market="ALL",
        start_date=market.dates[0],
        end_date=market.dates[-1],
        adjustment="qfq",
        benchmark="000300.XSHG",
        initial_cash=1_000_000,
        parameters={},
        max_workers=1,
        retry_count=0,
        symbol_limit=5,
    )
    with service._connect() as connection:
        for symbol in market.symbols:
            connection.execute(
                """
                UPDATE screening_items
                SET status='completed', entered=1, run_id=?, metrics_json='{}'
                WHERE task_id=? AND symbol=?
                """,
                (f"{task_id}-{symbol}", task_id, symbol),
            )
        connection.execute(
            "UPDATE screening_tasks SET status='completed', updated_at=? WHERE task_id=?",
            ("2026-01-10T15:00:00+08:00", task_id),
        )
        connection.commit()

    analysis = service.build_signal_analysis(task_id)
    ic = analysis["ic_analysis"]
    layers = analysis["layered_returns"]
    signal = analysis["signal_summary"]
    if analysis.get("status") != "ready" or ic.get("status") != "ready":
        raise SystemExit("independent signal smoke failed: IC evidence unavailable")
    if ic.get("period_count") != 5 or abs(float(ic.get("mean")) - 0.6) > 1e-9:
        raise SystemExit("independent signal smoke failed: IC sequence mismatch")
    if ic.get("newey_west_t") is None or ic.get("rank_mean") != 0.6:
        raise SystemExit("independent signal smoke failed: robust/rank IC missing")
    if layers.get("status") != "ready" or len(layers.get("series") or []) != 5:
        raise SystemExit("independent signal smoke failed: Q1-Q5 evidence missing")
    if float(layers.get("q1_annualized")) <= float(layers.get("q5_annualized")):
        raise SystemExit("independent signal smoke failed: Q1/Q5 ordering mismatch")
    if signal.get("total_signal_stock_count") != 5 or signal.get("average_per_period") != 5:
        raise SystemExit("independent signal smoke failed: signal summary mismatch")
    print("independent strategy-exposure signal analysis smoke passed")


if __name__ == "__main__":
    main()
