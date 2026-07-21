"""Smoke test for stage 49 data asset directory filters and snapshot migration diagnostics."""

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
    run_id = "stage49-asset-directory-filter-smoke-001"
    prefix = "stage49-asset-directory-filter-smoke"
    symbol = "000001.XSHE"

    status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"})
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage49 smoke failed: market sync did not complete")

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
        raise SystemExit("stage49 smoke failed: backtest did not complete")

    status, payload = _dispatch(app, "GET", f"/api/backtest/results/{run_id}/input-snapshot")
    snapshot = payload.get("snapshot", {})
    data_version = snapshot.get("data_version")
    if status != 200 or snapshot.get("status") != "found" or not data_version:
        raise SystemExit("stage49 smoke failed: snapshot missing data_version")

    status, payload = _dispatch(app, "GET", "/api/backtest/data-assets", query_string=f"symbol={symbol}&dataset=price_history&quality_status=needs_attention&limit=20")
    assets = payload.get("assets", [])
    summary = payload.get("summary", {})
    if status != 200 or not assets or summary.get("filters", {}).get("dataset") != "price_history":
        raise SystemExit("stage49 smoke failed: filtered asset directory did not return expected assets")
    if data_version not in {item.get("data_version") for item in assets}:
        raise SystemExit("stage49 smoke failed: filtered asset directory missing run data_version")

    status, payload = _dispatch(app, "GET", "/api/backtest/data-assets", query_string=f"data_version={data_version}&limit=5")
    if status != 200 or payload.get("summary", {}).get("asset_count", 0) < 1:
        raise SystemExit("stage49 smoke failed: data_version filter returned no assets")

    status, payload = _dispatch(app, "POST", "/api/backtest/data-assets/migrate-input-snapshots", {"run_id_prefix": prefix, "dry_run": True, "limit": 10})
    migration = payload.get("result", {})
    if status != 200 or migration.get("status") != "dry_run":
        raise SystemExit("stage49 smoke failed: migration dry-run did not complete")
    if migration.get("summary", {}).get("already_snapshotted", 0) < 1:
        raise SystemExit("stage49 smoke failed: migration dry-run did not detect existing snapshot")

    status, payload = _dispatch(app, "POST", "/api/backtest/data-assets/migrate-input-snapshots", {"run_id_prefix": prefix, "dry_run": False, "limit": 10})
    migration = payload.get("result", {})
    if status != 200 or migration.get("status") != "completed":
        raise SystemExit("stage49 smoke failed: migration execution did not complete")
    if migration.get("summary", {}).get("already_snapshotted", 0) < 1:
        raise SystemExit("stage49 smoke failed: migration execution lost existing snapshot diagnostics")

    print("stage49 data asset directory filters and migration smoke test passed")


if __name__ == "__main__":
    main()

