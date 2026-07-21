"""Smoke test for stage 50 report analysis summary."""

from __future__ import annotations

import json
from urllib.parse import quote

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    path_only, _, query = path.partition("?")
    return dispatch_request(app, method=method, path=path_only, query_string=query, body=body)


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.runtime import build_demo_app

    app = build_demo_app()
    run_id = "stage50-report-analysis-summary"
    symbol = "000001.XSHE"

    status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"})
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage50 smoke failed: market sync did not complete")

    status, payload = _dispatch(
        app,
        "POST",
        "/api/backtest/run-once",
        {
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
        },
    )
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit("stage50 smoke failed: backtest did not complete")

    status, payload = _dispatch(app, "GET", f"/api/reporting/strategy-evaluation/{quote(run_id)}")
    report = payload.get("report", {})
    summary = report.get("analysis_summary", {})
    if status != 200 or summary.get("version") != "stage50-report-analysis-v1":
        raise SystemExit("stage50 smoke failed: analysis summary missing")
    if not summary.get("cards") or not summary.get("action_items"):
        raise SystemExit("stage50 smoke failed: analysis cards/action_items missing")
    if not summary.get("data_asset", {}).get("data_version"):
        raise SystemExit("stage50 smoke failed: data asset version missing from analysis summary")

    status, payload = _dispatch(app, "POST", f"/api/reporting/run-detail/{quote(run_id)}/report-package", {"title": "Stage 50 analysis package"})
    package = payload.get("package", {})
    package_summary = package.get("strategy_evaluation", {}).get("analysis_summary", {})
    if status != 200 or package_summary.get("version") != "stage50-report-analysis-v1":
        raise SystemExit("stage50 smoke failed: package did not persist analysis summary")
    package_id = package.get("package_id")

    status, payload = _dispatch(app, "GET", f"/api/reporting/report-packages/{quote(package_id)}/export?format=json")
    exported = payload.get("export", {})
    if status != 200 or "stage50-report-analysis-v1" not in exported.get("content", ""):
        raise SystemExit("stage50 smoke failed: exported package missing analysis summary")

    print("stage50 report analysis summary smoke test passed")


if __name__ == "__main__":
    main()
