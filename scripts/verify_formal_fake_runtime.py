"""Minimal verification script for the formal fake-runtime chain."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backtest_kernel import (
    RqalphaRicequantGateway,
    RunSingleBacktest,
    RunSingleBacktestRequest,
)
from config_center.providers.ricequant_config import RicequantConfig


class FakeRqalphaRuntime:
    """Deterministic runtime used only by the local verification script."""

    def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        strategy_name = str(payload.get("strategy_name") or "unknown_strategy")
        benchmark = str(payload.get("benchmark") or "000300.XSHG")
        start_date = str(payload.get("start_date") or "2020-01-01")
        end_date = str(payload.get("end_date") or "2020-12-31")
        run_id = str(payload.get("run_id") or "fake-run-id")
        parameters = payload.get("parameters")
        symbol = (
            str(parameters.get("symbol"))
            if isinstance(parameters, Mapping) and parameters.get("symbol")
            else "000001.XSHE"
        )
        return {
            "run_id": run_id,
            "strategy_name": strategy_name,
            "status": "completed",
            "start_date": start_date,
            "end_date": end_date,
            "benchmark": benchmark,
            "metrics": {
                "annualized_returns": 0.1234,
                "total_returns": 0.2345,
                "max_drawdown": -0.0567,
                "sharpe": 1.89,
            },
            "raw_result": {
                "engine": "script-fake-runtime",
                "symbol": symbol,
                "parameters": dict(parameters) if isinstance(parameters, Mapping) else {},
            },
        }



def main() -> None:
    gateway = RqalphaRicequantGateway(
        RicequantConfig(username="demo", password="demo"),
        runtime=FakeRqalphaRuntime(),
    )
    use_case = RunSingleBacktest(gateway)
    request = RunSingleBacktestRequest(
        run_id="phase1-demo-run-001",
        strategy_name="moving_average_strategy",
        symbol="000001.XSHE",
        benchmark="000300.XSHG",
        start_date="2020-01-01",
        end_date="2020-12-31",
    )
    result = use_case.execute(request)

    if result.run_id != request.run_id:
        raise SystemExit("formal fake runtime verification failed: run_id mismatch")
    if result.status != "completed":
        raise SystemExit("formal fake runtime verification failed: status mismatch")
    if "annualized_returns" not in result.metrics:
        raise SystemExit("formal fake runtime verification failed: metrics missing")

    print("formal fake runtime verification passed")


if __name__ == "__main__":
    main()
