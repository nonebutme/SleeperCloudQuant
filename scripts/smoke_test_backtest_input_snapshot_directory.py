"""Smoke test for stage 47 persisted backtest input snapshots and data asset directory."""

from __future__ import annotations

import json

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None, query_string: str = ""):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    return dispatch_request(app, method=method, path=path, query_string=query_string, body=body)


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app

    app = build_demo_app()
    run_id = "stage47-input-snapshot-directory-smoke"
    symbol = "000001.XSHE"

    status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"})
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage47 smoke failed: market sync did not complete")

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
        raise SystemExit("stage47 smoke failed: backtest did not complete")

    status, payload = _dispatch(app, "GET", f"/api/backtest/results/{run_id}/input-snapshot")
    snapshot = payload.get("snapshot", {})
    if status != 200 or snapshot.get("status") != "found" or not snapshot.get("data_version"):
        raise SystemExit("stage47 smoke failed: input snapshot not persisted")
    if snapshot.get("symbol") != symbol or snapshot.get("run_id") != run_id:
        raise SystemExit("stage47 smoke failed: input snapshot identity mismatch")

    status, payload = _dispatch(app, "GET", "/api/backtest/data-assets", query_string=f"symbol={symbol}&limit=10")
    assets = payload.get("assets", [])
    summary = payload.get("summary", {})
    versions = {item.get("data_version") for item in assets}
    if status != 200 or summary.get("asset_count", 0) < 1 or snapshot.get("data_version") not in versions:
        raise SystemExit("stage47 smoke failed: data asset directory missing snapshot version")

    status, payload = _dispatch(app, "GET", f"/api/backtest/results/{run_id}/panel")
    panel = payload.get("result", {})
    if status != 200 or panel.get("summary", {}).get("input_snapshot_id") != snapshot.get("snapshot_id"):
        raise SystemExit("stage47 smoke failed: result panel input snapshot id mismatch")
    if panel.get("input_snapshot", {}).get("data_version") != snapshot.get("data_version"):
        raise SystemExit("stage47 smoke failed: result panel input snapshot version mismatch")

    print("stage47 input snapshot directory smoke test passed")


if __name__ == "__main__":
    main()
