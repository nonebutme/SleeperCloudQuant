"""Smoke test for stage 56 report package lifecycle governance."""

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
        raise SystemExit(f"stage56 smoke failed: backtest did not complete for {run_id}")


def main() -> None:
    ensure_project_root_on_sys_path()
    root = Path.cwd()
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    for needle, text, context in (
        ("report-package-directory-lifecycle", html, "web/index.html"),
        ("report-package-lifecycle-archive", html, "web/index.html"),
        ("updateSelectedReportPackageLifecycle", js, "web/app.js"),
        ("/lifecycle", js, "web/app.js"),
    ):
        if needle not in text:
            raise SystemExit(f"stage56 smoke failed: missing {needle} in {context}")

    from app.runtime import build_demo_app

    app = build_demo_app()
    prefix = "stage56-report-package-lifecycle"
    symbol = "000001.XSHE"
    status, payload = _dispatch(
        app,
        "POST",
        "/api/market/sync-price-history",
        {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"},
    )
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage56 smoke failed: market sync did not complete")

    _run(app, f"{prefix}-001", symbol, 2, 3)
    _run(app, f"{prefix}-002", symbol, 3, 5)

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/experiments/{quote(prefix)}/comparison-package",
        {"title": "阶段56 生命周期实验对比报告包"},
    )
    package = payload.get("package", {})
    package_id = package.get("package_id")
    if status != 200 or not package_id:
        raise SystemExit("stage56 smoke failed: comparison package was not created")

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/report-packages/{quote(package_id)}/lifecycle",
        {"status": "archived", "retention_policy": "retain-local-audit", "protected": False, "reason": "阶段56 smoke 归档", "updated_by": "smoke"},
    )
    archived = payload.get("package", {}).get("lifecycle", {})
    if status != 200 or archived.get("status") != "archived" or not archived.get("audit_log"):
        raise SystemExit("stage56 smoke failed: archive lifecycle update missing audit log")

    status, payload = _dispatch(
        app,
        "GET",
        f"/api/reporting/report-packages?run_id={quote(prefix)}&lifecycle_status=archived&limit=20",
    )
    archived_directory = payload.get("directory", {})
    archived_packages = archived_directory.get("packages", [])
    if status != 200 or not any(item.get("package_id") == package_id and item.get("lifecycle_status") == "archived" for item in archived_packages):
        raise SystemExit("stage56 smoke failed: archived directory filter missed package")

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/report-packages/{quote(package_id)}/lifecycle",
        {"status": "protected", "retention_policy": "retain-protected", "protected": True, "reason": "阶段56 smoke 保护", "updated_by": "smoke"},
    )
    protected_lifecycle = payload.get("package", {}).get("lifecycle", {})
    if status != 200 or protected_lifecycle.get("status") != "protected" or protected_lifecycle.get("protected") is not True:
        raise SystemExit("stage56 smoke failed: protected lifecycle update missing flag")
    if len(protected_lifecycle.get("audit_log") or []) < 2:
        raise SystemExit("stage56 smoke failed: lifecycle audit log did not append")

    status, payload = _dispatch(
        app,
        "GET",
        f"/api/reporting/report-packages?run_id={quote(prefix)}&lifecycle_status=protected&limit=20",
    )
    protected_packages = payload.get("directory", {}).get("packages", [])
    if status != 200 or not any(item.get("package_id") == package_id and item.get("protected") is True for item in protected_packages):
        raise SystemExit("stage56 smoke failed: protected directory filter missed package")

    status, payload = _dispatch(app, "GET", f"/api/reporting/report-packages/{quote(package_id)}")
    detail = payload.get("package", {})
    if status != 200 or detail.get("lifecycle", {}).get("retention_policy") != "retain-protected":
        raise SystemExit("stage56 smoke failed: package detail did not persist lifecycle")

    print("stage56 report package lifecycle smoke test passed")


if __name__ == "__main__":
    main()
