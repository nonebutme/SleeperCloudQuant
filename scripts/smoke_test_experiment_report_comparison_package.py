"""Smoke test for stage 54 experiment comparison report packages."""

from __future__ import annotations

import json
from urllib.parse import quote

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    path_only, _, query = path.partition("?")
    return dispatch_request(app, method=method, path=path_only, query_string=query, body=body)


def _run(app, run_id: str, symbol: str, short_window: int, long_window: int) -> None:
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
            "parameters": {"short_window": short_window, "long_window": long_window, "position_size": 1.0},
            "extra_config": {"runtime_mode": "local_sqlite_backtest"},
        },
    )
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit(f"stage54 smoke failed: backtest did not complete for {run_id}")


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app

    app = build_demo_app()
    prefix = "stage54-report-comparison-package"
    symbol = "000001.XSHE"
    status, payload = _dispatch(
        app,
        "POST",
        "/api/market/sync-price-history",
        {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"},
    )
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage54 smoke failed: market sync did not complete")

    _run(app, f"{prefix}-001", symbol, 2, 3)
    _run(app, f"{prefix}-002", symbol, 3, 5)

    status, payload = _dispatch(app, "GET", f"/api/reporting/experiments/{quote(prefix)}/comparison")
    comparison = payload.get("comparison", {})
    if status != 200 or comparison.get("status") != "ready" or len(comparison.get("rows", [])) < 2:
        raise SystemExit("stage54 smoke failed: experiment comparison was not ready")

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/experiments/{quote(prefix)}/comparison-package",
        {"title": "阶段54 实验对比报告包"},
    )
    package = payload.get("package", {})
    package_id = package.get("package_id")
    manifest = package.get("manifest", {})
    if status != 200 or not package_id:
        raise SystemExit("stage54 smoke failed: comparison package was not created")
    if manifest.get("manifest_version") != "stage54-experiment-comparison-package-v1":
        raise SystemExit("stage54 smoke failed: manifest version mismatch")
    if package.get("binding_mode") != "run_id_prefix_comparison":
        raise SystemExit("stage54 smoke failed: binding mode mismatch")
    if package.get("experiment_report_comparison", {}).get("summary", {}).get("run_count", 0) < 2:
        raise SystemExit("stage54 smoke failed: package comparison summary missing")
    if not package.get("chart_source", {}).get("score"):
        raise SystemExit("stage54 smoke failed: score chart source missing")

    status, payload = _dispatch(app, "GET", f"/api/reporting/run-detail/{quote(prefix)}/report-packages")
    packages = payload.get("packages", [])
    if status != 200 or not any(item.get("package_id") == package_id for item in packages):
        raise SystemExit("stage54 smoke failed: package list did not include comparison package")

    status, payload = _dispatch(app, "GET", f"/api/reporting/report-packages/{quote(package_id)}/export?format=json")
    json_export = payload.get("export", {})
    json_content = json_export.get("content", "")
    if status != 200 or "stage54-experiment-comparison-package-v1" not in json_content or "experiment_report_comparison" not in json_content:
        raise SystemExit("stage54 smoke failed: json export missing comparison payload")

    status, payload = _dispatch(app, "GET", f"/api/reporting/report-packages/{quote(package_id)}/export?format=html")
    html_export = payload.get("export", {})
    html_content = html_export.get("content", "")
    for needle in ("实验报告对比排名", "图表源数据", "阶段54 实验对比报告包"):
        if status != 200 or needle not in html_content:
            raise SystemExit(f"stage54 smoke failed: html export missing {needle}")

    print("stage54 experiment report comparison package smoke test passed")


if __name__ == "__main__":
    main()
