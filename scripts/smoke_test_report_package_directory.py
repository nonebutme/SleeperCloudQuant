"""Smoke test for stage 55 report package archive directory."""

from __future__ import annotations

import json
from pathlib import Path
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
        raise SystemExit(f"stage55 smoke failed: backtest did not complete for {run_id}")


def main() -> None:
    ensure_project_root_on_sys_path()
    root = Path.cwd()
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    for needle, text, context in (
        ("report-package-directory-panel", html, "web/index.html"),
        ("report-package-directory-refresh", html, "web/index.html"),
        ("loadReportPackageDirectory", js, "web/app.js"),
        ("/api/reporting/report-packages", js, "web/app.js"),
    ):
        if needle not in text:
            raise SystemExit(f"stage55 smoke failed: missing {needle} in {context}")

    from app.runtime import build_demo_app

    app = build_demo_app()
    prefix = "stage55-report-package-directory"
    symbol = "000001.XSHE"
    status, payload = _dispatch(
        app,
        "POST",
        "/api/market/sync-price-history",
        {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"},
    )
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage55 smoke failed: market sync did not complete")

    _run(app, f"{prefix}-001", symbol, 2, 3)
    _run(app, f"{prefix}-002", symbol, 3, 5)

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/run-detail/{quote(prefix + '-001')}/report-package",
        {"symbol": symbol, "title": "阶段55 普通研究报告包"},
    )
    regular_package = payload.get("package", {})
    if status != 200 or not regular_package.get("package_id"):
        raise SystemExit("stage55 smoke failed: regular report package was not created")

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/experiments/{quote(prefix)}/comparison-package",
        {"title": "阶段55 实验对比报告包"},
    )
    comparison_package = payload.get("package", {})
    if status != 200 or comparison_package.get("binding_mode") != "run_id_prefix_comparison":
        raise SystemExit("stage55 smoke failed: comparison package was not created")

    status, payload = _dispatch(app, "GET", f"/api/reporting/report-packages?run_id={quote(prefix)}&limit=20")
    directory = payload.get("directory", {})
    packages = directory.get("packages", [])
    if status != 200 or directory.get("status") != "ready":
        raise SystemExit("stage55 smoke failed: directory endpoint was not ready")
    if not any(item.get("package_id") == comparison_package.get("package_id") for item in packages):
        raise SystemExit("stage55 smoke failed: directory missing comparison package")
    if directory.get("summary", {}).get("type_counts", {}).get("experiment_report_comparison", 0) < 1:
        raise SystemExit("stage55 smoke failed: directory type_counts missing comparison package")
    if not all(item.get("export_links", {}).get("html") for item in packages):
        raise SystemExit("stage55 smoke failed: directory export links missing")

    status, payload = _dispatch(
        app,
        "GET",
        f"/api/reporting/report-packages?run_id={quote(prefix)}&package_type=experiment_report_comparison&limit=20",
    )
    filtered = payload.get("directory", {}).get("packages", [])
    if status != 200 or not filtered or any(item.get("package_type") != "experiment_report_comparison" for item in filtered):
        raise SystemExit("stage55 smoke failed: package_type filter did not isolate comparison packages")

    status, payload = _dispatch(app, "GET", f"/api/reporting/report-packages?run_id={quote(prefix + '-001')}&limit=20")
    run_directory = payload.get("directory", {})
    regular_items = [item for item in run_directory.get("packages", []) if item.get("package_id") == regular_package.get("package_id")]
    if status != 200 or not regular_items or regular_items[0].get("package_type") != "research_report_package":
        raise SystemExit("stage55 smoke failed: run-level directory missing regular package")

    print("stage55 report package directory smoke test passed")


if __name__ == "__main__":
    main()



