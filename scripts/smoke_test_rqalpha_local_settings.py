"""Smoke test for stage 25 rqalpha-style local runtime settings."""

from __future__ import annotations

import json

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request
    from app.runtime.demo_registry import _build_market_repository
    from backtest_kernel import LocalSQLiteBacktestRuntime

    direct_runtime = LocalSQLiteBacktestRuntime(_build_market_repository())
    direct_result = direct_runtime.run(
        {
            "run_id": "stage25-direct-runtime-cost-probe",
            "strategy_name": "moving_average_strategy",
            "symbol": "000001.XSHE",
            "benchmark": "000300.XSHG",
            "start_date": "2020-01-02",
            "end_date": "2020-06-30",
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
    direct_raw = direct_result.get("raw_result", {})
    direct_trades = direct_raw.get("trades", [])
    if not direct_trades or not any(float(row.get("commission") or 0) >= 7 for row in direct_trades):
        raise SystemExit("stage25 smoke failed: direct runtime cost model not applied")
    if direct_raw.get("strategy_template", {}).get("template_id") != "handle_bar_ma_cross":
        raise SystemExit("stage25 smoke failed: direct runtime strategy template trace missing")
    if "benchmark_return" not in direct_result.get("metrics", {}) or "excess_return" not in direct_result.get("metrics", {}):
        raise SystemExit("stage25 smoke failed: direct runtime benchmark metrics missing")

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


