"""Smoke test for stage 21 PDF and Word-compatible report package exports."""

from __future__ import annotations

import json
from urllib.parse import quote

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request

    app = build_demo_app()
    run_id = "stage21-report-package-export-smoke"
    symbol = "000001.XSHE"

    backtest_request = {
        "run_id": run_id,
        "strategy_name": "moving_average_strategy",
        "strategy_id": "moving_average_strategy",
        "strategy_version": "v1",
        "symbol": symbol,
        "benchmark": "000300.XSHG",
        "start_date": "2020-01-02",
        "end_date": "2020-06-30",
        "parameters": {"short_window": 3, "long_window": 5, "position_size": 1.0},
        "extra_config": {"runtime_mode": "local_sqlite_backtest"},
    }
    status, payload = dispatch_request(app, method="POST", path="/api/backtest/run-once", body=json.dumps(backtest_request).encode("utf-8"))
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit("report package export smoke test failed: backtest did not complete")

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
    status, payload = dispatch_request(app, method="POST", path="/api/ai/workflow/run", body=json.dumps(workflow_request).encode("utf-8"))
    workflow = payload.get("workflow", {})
    if status != 200 or workflow.get("report_id") != run_id:
        raise SystemExit("report package export smoke test failed: workflow not bound")

    status, payload = dispatch_request(
        app,
        method="POST",
        path=f"/api/reporting/run-detail/{quote(run_id)}/report-package",
        body=json.dumps({"symbol": symbol, "workflow_id": workflow.get("workflow_id"), "title": "Stage 21 export package"}).encode("utf-8"),
    )
    package = payload.get("package", {})
    package_id = package.get("package_id")
    manifest = package.get("manifest", {})
    if status != 200 or manifest.get("artifacts", {}).get("export_formats") != ["html", "json", "pdf", "word"]:
        raise SystemExit("report package export smoke test failed: export formats missing")

    for fmt, expected_filename, expected_type in (
        ("html", ".html", "text/html"),
        ("json", ".json", "application/json"),
        ("pdf", ".pdf", "application/pdf"),
        ("word", ".doc", "application/msword"),
    ):
        status, payload = dispatch_request(app, method="GET", path=f"/api/reporting/report-packages/{quote(package_id)}/export", query_string=f"format={fmt}")
        exported = payload.get("export", {})
        content = exported.get("content", "")
        if status != 200 or not exported.get("filename", "").endswith(expected_filename) or expected_type not in exported.get("content_type", ""):
            raise SystemExit(f"report package export smoke test failed: {fmt} metadata mismatch")
        if fmt == "pdf" and not content.startswith("%PDF-1.4"):
            raise SystemExit("report package export smoke test failed: PDF header missing")
        if fmt == "pdf" and "stage20-report-package-manifest-v1" not in content:
            raise SystemExit("report package export smoke test failed: PDF manifest missing")
        if fmt == "word" and ("schemas-microsoft-com:office:word" not in content or "报告包 Manifest" not in content):
            raise SystemExit("report package export smoke test failed: Word-compatible HTML missing")
        if fmt in {"html", "json"} and "stage20-report-package-manifest-v1" not in content:
            raise SystemExit(f"report package export smoke test failed: {fmt} manifest missing")

    print("report package export smoke test passed")


if __name__ == "__main__":
    main()
