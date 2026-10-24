"""Smoke test for stage 25 rqalpha-style local runtime settings."""

from __future__ import annotations

import json
import math

from _project_bootstrap import ensure_project_root_on_sys_path


class _DeterministicCostProbeRepository:
    """Small self-contained bar fixture that opens and then closes a position."""

    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        adjustment: str = "raw",
    ) -> list[dict[str, object]]:
        del symbol, start_date, end_date, adjustment
        return [
            {"date": "2020-01-02", "open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0, "volume": 1_000.0},
            {"date": "2020-01-03", "open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0, "volume": 1_000.0},
            {"date": "2020-01-06", "open": 11.0, "high": 11.2, "low": 10.8, "close": 11.0, "volume": 1_000.0},
            {"date": "2020-01-07", "open": 8.0, "high": 8.2, "low": 7.8, "close": 8.0, "volume": 1_000.0},
        ]


def _verify_direct_runtime_cost_model(runtime_type) -> dict[str, object]:
    direct_runtime = runtime_type(_DeterministicCostProbeRepository())
    direct_result = direct_runtime.run(
        {
            "run_id": "stage25-direct-runtime-cost-probe",
            "strategy_name": "moving_average_strategy",
            "symbol": "000001.XSHE",
            "benchmark": "000300.XSHG",
            "start_date": "2020-01-02",
            "end_date": "2020-01-07",
            "initial_cash": 8_000,
            "parameters": {"symbol": "000001.XSHE", "short_window": 2, "long_window": 3, "position_size": 1.0},
            "extra_config": {
                "rqalpha_local": {
                    "strategy_template": "handle_bar_ma_cross",
                    "commission_rate": 0.001,
                    "tax_rate": 0.002,
                    "min_commission": 7,
                    "slippage_rate": 0.001,
                    "benchmark_alignment": "same_symbol_buy_hold",
                }
            },
        }
    )
    direct_raw = dict(direct_result.get("raw_result") or {})
    direct_trades = [dict(row) for row in direct_raw.get("trades") or []]
    if [row.get("side") for row in direct_trades] != ["BUY", "SELL"]:
        raise SystemExit("stage25 smoke failed: deterministic cost probe did not open and close")

    buy_trade, sell_trade = direct_trades
    if not math.isclose(float(buy_trade.get("price") or 0), 11.0 * 1.001, abs_tol=1e-6):
        raise SystemExit("stage25 smoke failed: buy-side slippage not applied")
    if not math.isclose(float(sell_trade.get("price") or 0), 8.0 * (1.0 - 0.001), abs_tol=1e-6):
        raise SystemExit("stage25 smoke failed: sell-side slippage not applied")
    expected_buy_commission = max(float(buy_trade.get("amount") or 0) * 0.001, 7.0)
    expected_sell_commission = max(float(sell_trade.get("amount") or 0) * 0.001, 7.0)
    if not math.isclose(float(buy_trade.get("commission") or 0), expected_buy_commission, abs_tol=1e-6):
        raise SystemExit("stage25 smoke failed: proportional commission not applied")
    if not math.isclose(float(sell_trade.get("commission") or 0), expected_sell_commission, abs_tol=1e-6):
        raise SystemExit("stage25 smoke failed: minimum commission not applied")
    if expected_buy_commission <= 7.0 or not math.isclose(expected_sell_commission, 7.0, abs_tol=1e-6):
        raise SystemExit("stage25 smoke failed: commission probe does not exercise both cost branches")
    if not math.isclose(float(buy_trade.get("tax") or 0), 0.0, abs_tol=1e-6):
        raise SystemExit("stage25 smoke failed: buy-side tax should be zero")
    expected_sell_tax = float(sell_trade.get("amount") or 0) * 0.002
    if not math.isclose(float(sell_trade.get("tax") or 0), expected_sell_tax, abs_tol=1e-6):
        raise SystemExit("stage25 smoke failed: sell-side tax not applied")
    if direct_raw.get("strategy_template", {}).get("template_id") != "handle_bar_ma_cross":
        raise SystemExit("stage25 smoke failed: direct runtime strategy template trace missing")
    if "benchmark_return" not in direct_result.get("metrics", {}) or "excess_return" not in direct_result.get("metrics", {}):
        raise SystemExit("stage25 smoke failed: direct runtime benchmark metrics missing")
    return dict(direct_result)


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request
    from backtest_kernel import LocalSQLiteBacktestRuntime

    _verify_direct_runtime_cost_model(LocalSQLiteBacktestRuntime)

    app = build_demo_app()
    run_id = "stage25-rqalpha-local-settings-smoke"
    request = {
        "run_id": run_id,
        "strategy_name": "moving_average_strategy",
        "strategy_id": "moving_average_strategy",
        "strategy_version": "v1",
        "symbol": "000001.XSHE",
        "benchmark": "000300.XSHG",
        "start_date": "2020-01-02",
        "end_date": "2020-06-30",
        "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
        "extra_config": {
            "runtime_mode": "rqalpha_local_enhanced",
            "rqalpha_local": {
                "strategy_template": "handle_bar_ma_cross",
                "commission_rate": 0.001,
                "tax_rate": 0.002,
                "min_commission": 7,
                "slippage_rate": 0.001,
                "benchmark_alignment": "same_symbol_buy_hold",
            },
        },
    }
    status, payload = dispatch_request(app, method="POST", path="/api/backtest/run-once", body=json.dumps(request).encode("utf-8"))
    result = payload.get("result", {})
    if status != 200 or result.get("status") != "completed":
        raise SystemExit("stage25 smoke failed: backtest did not complete")
    metrics = result.get("metrics", {})
    if "benchmark_return" not in metrics or "excess_return" not in metrics:
        raise SystemExit("stage25 smoke failed: benchmark/excess metrics missing")

    detail_status, detail_payload = dispatch_request(app, method="GET", path=f"/api/reporting/run-detail/{run_id}")
    detail = detail_payload.get("detail", {})
    if detail_status != 200 or not detail.get("trade_activity_chart"):
        raise SystemExit("stage25 smoke failed: reporting detail missing")
    if not detail.get("trade_activity_chart"):
        raise SystemExit("stage25 smoke failed: reporting trade chart missing")
    if not detail.get("yearly_return_chart") or "benchmark_return" not in detail.get("yearly_return_chart", [{}])[0]:
        raise SystemExit("stage25 smoke failed: yearly benchmark return missing")

    print("stage25 rqalpha local settings smoke test passed")


if __name__ == "__main__":
    main()


