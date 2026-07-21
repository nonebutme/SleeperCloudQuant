"""Smoke test for the local SQLite market-data driven backtest runtime."""

from __future__ import annotations

import json

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request

    app = build_demo_app()
    run_id = "stage18-local-sqlite-runtime-smoke"
    request = {
        "run_id": run_id,
        "strategy_name": "moving_average_strategy",
        "strategy_id": "moving_average_strategy",
        "strategy_version": "v1",
        "symbol": "000001.XSHE",
        "benchmark": "000300.XSHG",
        "start_date": "2020-01-02",
        "end_date": "2020-06-30",
        "parameters": {"short_window": 3, "long_window": 5, "position_size": 1.0},
        "extra_config": {"runtime_mode": "local_sqlite_backtest"},
    }
    status, payload = dispatch_request(
        app,
        method="POST",
        path="/api/backtest/run-once",
        body=json.dumps(request).encode("utf-8"),
    )
    result = payload.get("result", {})
    if status != 200 or result.get("status") != "completed":
        raise SystemExit("local SQLite runtime smoke test failed: run-once did not complete")
    metrics = result.get("metrics", {})
    if "total_returns" not in metrics or "max_drawdown" not in metrics or "sharpe" not in metrics:
        raise SystemExit("local SQLite runtime smoke test failed: metrics missing")

    detail_status, detail_payload = dispatch_request(app, method="GET", path=f"/api/reporting/run-detail/{run_id}")
    detail = detail_payload.get("detail", {})
    if detail_status != 200 or not detail.get("account_value_chart"):
        raise SystemExit("local SQLite runtime smoke test failed: account chart missing")
    if not detail.get("trade_activity_chart"):
        raise SystemExit("local SQLite runtime smoke test failed: trade chart missing")
    if not detail.get("position_exposure_chart"):
        raise SystemExit("local SQLite runtime smoke test failed: position chart missing")
    if not detail.get("yearly_return_chart"):
        raise SystemExit("local SQLite runtime smoke test failed: yearly return chart missing")

    report_status, report_payload = dispatch_request(app, method="GET", path=f"/api/reporting/strategy-evaluation/{run_id}")
    report = report_payload.get("report", {})
    if report_status != 200 or len(report.get("dimensions", [])) != 7:
        raise SystemExit("local SQLite runtime smoke test failed: seven-dimension report missing")

    print("local SQLite backtest runtime smoke test passed")


if __name__ == "__main__":
    main()
