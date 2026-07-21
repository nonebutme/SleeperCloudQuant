"""Smoke test for stage 57 report package export manifest."""

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
        raise SystemExit(f"stage57 smoke failed: backtest did not complete for {run_id}")


def main() -> None:
    ensure_project_root_on_sys_path()
    root = Path.cwd()
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    for needle, text, context in (
        ("report-package-export-manifest-create", html, "web/index.html"),
        ("report-package-export-manifest-output", html, "web/index.html"),
        ("createReportPackageExportManifest", js, "web/app.js"),
        ("/api/reporting/report-packages/export-manifest", js, "web/app.js"),
    ):
        if needle not in text:
            raise SystemExit(f"stage57 smoke failed: missing {needle} in {context}")

    from app.runtime import build_demo_app

    app = build_demo_app()
    prefix = "stage57-report-package-export-manifest"
    symbol = "000001.XSHE"
    status, payload = _dispatch(
        app,
        "POST",
        "/api/market/sync-price-history",
        {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"},
    )
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage57 smoke failed: market sync did not complete")

    _run(app, f"{prefix}-001", symbol, 2, 3)
    _run(app, f"{prefix}-002", symbol, 3, 5)

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/experiments/{quote(prefix)}/comparison-package",
        {"title": "阶段57 导出清单实验对比报告包"},
    )
    package = payload.get("package", {})
    package_id = package.get("package_id")
    if status != 200 or not package_id:
        raise SystemExit("stage57 smoke failed: comparison package was not created")

    status, payload = _dispatch(
        app,
        "POST",
        f"/api/reporting/report-packages/{quote(package_id)}/lifecycle",
        {"status": "archived", "retention_policy": "retain-local-audit", "protected": False, "reason": "stage57 manifest", "updated_by": "smoke"},
    )
    if status != 200 or payload.get("package", {}).get("lifecycle", {}).get("status") != "archived":
        raise SystemExit("stage57 smoke failed: lifecycle archive did not persist")

    status, payload = _dispatch(
        app,
        "GET",
        f"/api/reporting/report-packages/export-manifest?run_id={quote(prefix)}&lifecycle_status=archived&formats=html,json,pdf,invalid&limit=20",
    )
    manifest = payload.get("manifest", {})
    packages = manifest.get("packages", [])
    if status != 200 or manifest.get("manifest_version") != "stage57-report-package-export-manifest-v1":
        raise SystemExit("stage57 smoke failed: manifest version mismatch")
    if manifest.get("status") != "ready" or manifest.get("package_count", 0) < 1:
        raise SystemExit("stage57 smoke failed: manifest did not include packages")
    if "invalid" in manifest.get("formats", []) or set(manifest.get("formats", [])) != {"html", "json", "pdf"}:
        raise SystemExit("stage57 smoke failed: export formats were not normalized")
    if manifest.get("lifecycle_counts", {}).get("archived", 0) < 1:
        raise SystemExit("stage57 smoke failed: lifecycle counts missing archived package")
    if not any(item.get("package_id") == package_id for item in packages):
        raise SystemExit("stage57 smoke failed: manifest missing target package")
    first = packages[0]
    if not all(fmt in first.get("export_links", {}) for fmt in ("html", "json", "pdf")):
        raise SystemExit("stage57 smoke failed: manifest export links missing formats")
    boundary = manifest.get("offline_boundary", {})
    if boundary.get("mode") != "manifest_only" or boundary.get("no_files_written") is not True or boundary.get("no_package_deleted") is not True:
        raise SystemExit("stage57 smoke failed: offline boundary is not explicit")

    print("stage57 report package export manifest smoke test passed")


if __name__ == "__main__":
    main()
