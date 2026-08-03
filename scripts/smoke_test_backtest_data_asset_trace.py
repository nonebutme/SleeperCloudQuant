"""Smoke test for stage 46 backtest data asset trace binding."""

from __future__ import annotations

import json
from urllib.parse import quote

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None, query_string: str = ""):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    return dispatch_request(app, method=method, path=path, query_string=query_string, body=body)


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app

    app = build_demo_app()
    run_id = "stage46-data-asset-trace-smoke"
    symbol = "000001.XSHE"

    status, payload = _dispatch(
        app,
        "POST",
        "/api/market/sync-price-history",
        {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"},
    )
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage46 smoke failed: local market asset sync did not complete")

    status, payload = _dispatch(app, "GET", "/api/market/local-price-bars/assets", query_string=f"symbol={symbol}&limit=5")
    asset_payload = payload.get("assets", {})
    asset = (asset_payload.get("assets") or [{}])[0]
    local_asset_version = asset.get("data_version")
    if status != 200 or not local_asset_version:
        raise SystemExit("stage46 smoke failed: data asset version missing before backtest")

    backtest_request = {
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
    status, payload = _dispatch(app, "POST", "/api/backtest/run-once", backtest_request)
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit("stage46 smoke failed: backtest did not complete")

    status, payload = _dispatch(app, "GET", f"/api/backtest/results/{quote(run_id)}/panel")
    panel = payload.get("result", {})
    trace = panel.get("data_asset_trace", {})
    if status != 200 or trace.get("status") != "bound":
        raise SystemExit("stage46 smoke failed: result panel data asset trace not bound")
    data_version = trace.get("asset", {}).get("data_version")
    if not data_version or panel.get("summary", {}).get("data_version") != data_version:
        raise SystemExit("stage46 smoke failed: result panel data version mismatch")
    if trace.get("manifest", {}).get("scope") != "published_canonical_a_share_release":
        raise SystemExit("stage46 smoke failed: backtest did not freeze a published canonical release")

    workflow_request = {
        "symbol": symbol,
        "analysis_date": "2020-01-02",
        "report_id": run_id,
        "max_debate_rounds": 1,
        "enabled_analysts": ["market"],
        "enabled_researchers": ["bull", "bear"],
        "risk_team": ["neutral"],
        "provider_profile": "openai-compatible",
    }
    status, payload = _dispatch(app, "POST", "/api/ai/workflow/run", workflow_request)
    workflow = payload.get("workflow", {})
    if status != 200 or workflow.get("report_id") != run_id:
        raise SystemExit("stage46 smoke failed: workflow not bound to run")

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/run-detail/{quote(run_id)}/report-package",
        {"symbol": symbol, "workflow_id": workflow.get("workflow_id"), "title": "Stage 46 data asset trace package"},
    )
    package = payload.get("package", {})
    manifest_assets = package.get("manifest", {}).get("data_assets", {})
    if status != 200 or manifest_assets.get("data_version") != data_version:
        raise SystemExit("stage46 smoke failed: report package manifest data version mismatch")
    if manifest_assets.get("status") != "bound" or manifest_assets.get("symbol") != symbol:
        raise SystemExit("stage46 smoke failed: report package manifest asset binding invalid")
    package_text = json.dumps(package, ensure_ascii=False).lower()
    if '"api_key"' in package_text or "sk-" in package_text or "must-not-be-persisted" in package_text:
        raise SystemExit("stage46 smoke failed: sensitive field leaked")
    print("stage46 backtest data asset trace smoke test passed")


if __name__ == "__main__":
    main()
