"""Smoke test for the stdlib HTTP adapter."""

from __future__ import annotations

import json

from _project_bootstrap import ensure_project_root_on_sys_path



def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request

    app = build_demo_app()

    status_code, payload = dispatch_request(
        app,
        method="GET",
        path="/api/market/price-history",
        query_string="symbol=000001.XSHE&start_date=2020-01-01&end_date=2020-01-02",
    )
    if status_code != 200 or len(payload.get("rows", [])) != 2:
        raise SystemExit("formal HTTP adapter smoke test failed: price-history dispatch")

    status_code, payload = dispatch_request(
        app,
        method="GET",
        path="/api/market/trading-calendar",
        query_string="start_date=2020-01-01&end_date=2020-01-02",
    )
    if status_code != 200 or len(payload.get("days", [])) != 2:
        raise SystemExit("formal HTTP adapter smoke test failed: trading-calendar dispatch")

    status_code, payload = dispatch_request(
        app,
        method="POST",
        path="/api/backtest/run-once",
        body=json.dumps(
            {
                "run_id": "http-adapter-run-001",
                "strategy_name": "moving_average_strategy",
                "symbol": "000001.XSHE",
                "benchmark": "000300.XSHG",
                "start_date": "2020-01-01",
                "end_date": "2020-12-31",
            }
        ).encode("utf-8"),
    )
    if status_code != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit("formal HTTP adapter smoke test failed: backtest dispatch")

    status_code, payload = dispatch_request(
        app,
        method="GET",
        path="/api/reporting/run-detail/phase1-demo-run-001",
    )
    if status_code != 200 or not payload.get("detail", {}).get("account_value_chart"):
        raise SystemExit("formal HTTP adapter smoke test failed: run-detail dispatch")

    status_code, payload = dispatch_request(
        app,
        method="GET",
        path="/api/reporting/batch-summary/phase1-batch-001",
    )
    if status_code != 200 or not payload.get("summary", {}).get("rows"):
        raise SystemExit("formal HTTP adapter smoke test failed: batch-summary dispatch")

    print("formal HTTP adapter smoke test passed")


if __name__ == "__main__":
    main()
