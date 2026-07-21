"""Smoke test for stage 20 report package manifest exports."""

from __future__ import annotations

import json
from urllib.parse import quote

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request

    app = build_demo_app()
    run_id = "stage20-report-package-manifest-smoke"
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
    status, payload = dispatch_request(
        app,
        method="POST",
        path="/api/backtest/run-once",
        body=json.dumps(backtest_request).encode("utf-8"),
    )
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit("report package manifest smoke test failed: backtest did not complete")

    workflow_request = {
        "symbol": symbol,
        "analysis_date": "2020-01-02",
        "report_id": run_id,
        "max_debate_rounds": 1,
        "enabled_analysts": ["market", "news"],
        "enabled_researchers": ["bull", "bear"],
        "risk_team": ["neutral"],
        "provider_profile": "openai-compatible",
    }
    status, payload = dispatch_request(
        app,
        method="POST",
        path="/api/ai/workflow/run",
        body=json.dumps(workflow_request).encode("utf-8"),
    )
    workflow = payload.get("workflow", {})
    if status != 200 or workflow.get("report_id") != run_id:
        raise SystemExit("report package manifest smoke test failed: workflow not bound to run")
    if workflow.get("llm_provider_trace", {}).get("status") != "fallback_to_local_demo":
        raise SystemExit("report package manifest smoke test failed: LLM fallback trace missing")

    status, payload = dispatch_request(
        app,
        method="POST",
        path=f"/api/reporting/run-detail/{quote(run_id)}/report-package",
        body=json.dumps({"symbol": symbol, "workflow_id": workflow.get("workflow_id"), "title": "Stage 20 manifest package"}).encode("utf-8"),
    )
    package = payload.get("package", {})
    manifest = package.get("manifest", {})
    if status != 200 or manifest.get("manifest_version") != "stage20-report-package-manifest-v1":
        raise SystemExit("report package manifest smoke test failed: manifest missing")
    if manifest.get("runtime", {}).get("engine") != "local_sqlite_backtest_runtime":
        raise SystemExit("report package manifest smoke test failed: runtime manifest mismatch")
    if manifest.get("llm_provider", {}).get("status") != "fallback_to_local_demo":
        raise SystemExit("report package manifest smoke test failed: LLM provider manifest mismatch")
    if not any(item.get("source_id") == "legacy_sqlite_market_data" for item in manifest.get("data_sources", [])):
        raise SystemExit("report package manifest smoke test failed: data-source manifest mismatch")
    if not any("smoke_test_report_package_manifest.py" in item for item in manifest.get("verification", {}).get("commands", [])):
        raise SystemExit("report package manifest smoke test failed: verification command missing")
    package_text = json.dumps(package, ensure_ascii=False).lower()
    if "must-not-be-persisted" in package_text or "\"api_key\"" in package_text or "sk-" in package_text:
        raise SystemExit("report package manifest smoke test failed: sensitive field leaked")

    package_id = package.get("package_id")
    status, payload = dispatch_request(app, method="GET", path=f"/api/reporting/report-packages/{quote(package_id)}")
    detail = payload.get("package", {})
    if status != 200 or detail.get("manifest", {}).get("bindings", {}).get("run_id") != run_id:
        raise SystemExit("report package manifest smoke test failed: package detail manifest mismatch")

    status, payload = dispatch_request(app, method="GET", path=f"/api/reporting/report-packages/{quote(package_id)}/export", query_string="format=json")
    json_export = payload.get("export", {})
    if status != 200 or "stage20-report-package-manifest-v1" not in json_export.get("content", ""):
        raise SystemExit("report package manifest smoke test failed: JSON export manifest missing")

    status, payload = dispatch_request(app, method="GET", path=f"/api/reporting/report-packages/{quote(package_id)}/export", query_string="format=html")
    html_export = payload.get("export", {})
    if status != 200 or "报告包 Manifest" not in html_export.get("content", "") or "stage20-report-package-manifest-v1" not in html_export.get("content", ""):
        raise SystemExit("report package manifest smoke test failed: HTML export manifest missing")

    print("report package manifest smoke test passed")


if __name__ == "__main__":
    main()

