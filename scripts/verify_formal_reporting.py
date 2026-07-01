"""Minimal verification script for the formal reporting chain."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from reporting import BatchComparisonService, RunResultsReader


class FakeReportingStore:
    """Deterministic in-memory store used only by the local verification script."""

    def __init__(self) -> None:
        self._run = {
            "run_id": "phase1-demo-run-001",
            "strategy_name": "moving_average_strategy",
            "strategy_id": "ma_strategy_v1",
            "benchmark": "000300.XSHG",
            "universe": "000001.XSHE",
            "start_date": "2020-01-01",
            "end_date": "2020-12-31",
            "status": "completed",
            "created_at": "2020-01-01T09:30:00+08:00",
            "completed_at": "2020-12-31T15:00:00+08:00",
            "parameters": {
                "short_window": 5,
                "long_window": 20,
            },
        }
        self._research_run = {
            "run_id": "phase1-batch-001",
            "strategy_name": "default_a_share",
            "status": "completed",
            "started_at": "2020-01-01T09:30:00+08:00",
            "finished_at": "2020-12-31T15:00:00+08:00",
            "parameters": {
                "profile": "default_a_share",
                "request_count": 1,
                "success_count": 1,
                "failure_count": 0,
                "run_ids": ["phase1-demo-run-001"],
                "failures": [],
            },
        }

    def fetch_backtest_run(self, run_id: str) -> Mapping[str, Any] | None:
        return self._run if run_id == self._run["run_id"] else None

    def fetch_backtest_metrics(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {"metric_name": "annualized_returns", "metric_value": 0.1234, "metric_text": None},
            {"metric_name": "total_returns", "metric_value": 0.2345, "metric_text": None},
            {"metric_name": "max_drawdown", "metric_value": -0.0567, "metric_text": None},
            {"metric_name": "sharpe", "metric_value": 1.89, "metric_text": None},
        ]

    def fetch_backtest_logs(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "recorded_at": "2020-01-01T09:31:00+08:00",
                "level": "INFO",
                "stage": "startup",
                "message": "fake reporting store initialized",
            }
        ]

    def fetch_backtest_trades(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "trade_time": "2020-02-03T10:00:00+08:00",
                "order_book_id": "000001.XSHE",
                "side": "BUY",
                "price": 10.2,
                "quantity": 100.0,
                "amount": 1020.0,
            },
            {
                "trade_time": "2020-03-03T10:00:00+08:00",
                "order_book_id": "000001.XSHE",
                "side": "SELL",
                "price": 11.0,
                "quantity": 100.0,
                "amount": 1100.0,
            },
        ]

    def fetch_backtest_positions(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "snapshot_time": "2020-02-03T15:00:00+08:00",
                "order_book_id": "000001.XSHE",
                "quantity": 100.0,
                "market_value": 1020.0,
                "notes": {},
            }
        ]

    def fetch_backtest_accounts(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "snapshot_time": "2020-02-03T15:00:00+08:00",
                "total_value": 1001020.0,
                "market_value": 1020.0,
                "cash": 1000000.0,
                "unit_net_value": 1.00102,
                "notes": {"account_type": "portfolio"},
            }
        ]

    def fetch_backtest_yearly_returns(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        if run_id != self._run["run_id"]:
            return []
        return [
            {
                "year": "2020",
                "portfolio_return": 0.2345,
                "benchmark_return": 0.1567,
                "excess_return": 0.0778,
            }
        ]

    def fetch_research_run(self, run_id: str) -> Mapping[str, Any] | None:
        return self._research_run if run_id == self._research_run["run_id"] else None



def main() -> None:
    store = FakeReportingStore()
    reader = RunResultsReader(store)
    detail = reader.get_run_detail("phase1-demo-run-001")
    if detail is None:
        raise SystemExit("formal reporting verification failed: missing run detail")

    account_chart = reader.build_account_value_chart(detail)
    trade_chart = reader.build_trade_activity_chart(detail)
    yearly_chart = reader.build_yearly_return_chart(detail)

    if not account_chart:
        raise SystemExit("formal reporting verification failed: account chart empty")
    if not trade_chart:
        raise SystemExit("formal reporting verification failed: trade chart empty")
    if not yearly_chart:
        raise SystemExit("formal reporting verification failed: yearly chart empty")

    comparison_service = BatchComparisonService(store)
    summary = comparison_service.summarize_experiment("phase1-batch-001")
    if summary is None:
        raise SystemExit("formal reporting verification failed: batch summary missing")
    if not summary.rows:
        raise SystemExit("formal reporting verification failed: batch rows empty")

    print("formal reporting verification passed")


if __name__ == "__main__":
    main()
