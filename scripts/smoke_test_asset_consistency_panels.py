"""Smoke test for stage 48 data-version panels and asset consistency."""

from __future__ import annotations

import json

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None, query_string: str = ""):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    return dispatch_request(app, method=method, path=path, query_string=query_string, body=body)


def _run_backtest(app, run_id: str, symbol: str) -> None:
    request = {
        "run_id": run_id,
        "strategy_name": "moving_average_strategy",
        "strategy_id": "moving_average_strategy",
        "strategy_version": "v1",
        "symbol": symbol,
        "benchmark": "000300.XSHG",
        "start_date": "2020-01-02",
        "end_date": "2020-01-10",
        "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
        "extra_config": {"runtime_mode": "local_sqlite_backtest"},
    }
    status, payload = _dispatch(app, "POST", "/api/backtest/run-once", request)
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit(f"stage48 smoke failed: backtest did not complete for {run_id}")


def _assert_consistency(panel: dict[str, object], context: str) -> None:
    consistency = panel.get("asset_consistency") or {}
    if consistency.get("status") != "consistent":
        raise SystemExit(f"stage48 smoke failed: {context} asset consistency is not consistent")
    if consistency.get("data_version_count") != 1:
        raise SystemExit(f"stage48 smoke failed: {context} data_version_count mismatch")
    if int(consistency.get("missing_count") or 0) != 0:
        raise SystemExit(f"stage48 smoke failed: {context} has missing data versions")
    if int(consistency.get("snapshot_count") or 0) < 2:
        raise SystemExit(f"stage48 smoke failed: {context} snapshot_count mismatch")


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app

    app = build_demo_app()
    prefix = "stage48-asset-consistency-smoke"
    symbol = "000001.XSHE"

    status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"})
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage48 smoke failed: market sync did not complete")

    _run_backtest(app, f"{prefix}-001", symbol)
    _run_backtest(app, f"{prefix}-002", symbol)

    status, payload = _dispatch(app, "GET", f"/api/backtest/results/{prefix}-001/panel")
    result_panel = payload.get("result", {})
    if status != 200 or not result_panel.get("summary", {}).get("data_version"):
        raise SystemExit("stage48 smoke failed: result panel missing data_version")
    if not result_panel.get("summary", {}).get("input_snapshot_id"):
        raise SystemExit("stage48 smoke failed: result panel missing input_snapshot_id")
    if not result_panel.get("input_snapshot", {}).get("snapshot_id"):
        raise SystemExit("stage48 smoke failed: result panel missing input_snapshot payload")

    status, payload = _dispatch(app, "GET", f"/api/backtest/results/{prefix}/portfolio-panel")
    portfolio_panel = payload.get("result", {})
    if status != 200:
        raise SystemExit("stage48 smoke failed: portfolio panel request failed")
    _assert_consistency(portfolio_panel, "portfolio")
    if not all(row.get("data_version") and row.get("input_snapshot_id") for row in portfolio_panel.get("rows", [])):
        raise SystemExit("stage48 smoke failed: portfolio rows missing asset fields")

    status, payload = _dispatch(app, "GET", f"/api/backtest/experiments/{prefix}/panel")
    experiment_panel = payload.get("result", {})
    if status != 200:
        raise SystemExit("stage48 smoke failed: experiment panel request failed")
    _assert_consistency(experiment_panel, "experiment")
    if experiment_panel.get("summary", {}).get("asset_consistency_status") != "consistent":
        raise SystemExit("stage48 smoke failed: experiment summary missing consistency status")

    print("stage48 asset consistency panels smoke test passed")


if __name__ == "__main__":
    main()
