"""Smoke test for stage 22 formal report package PDF layout."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request

    app = build_demo_app()
    run_id = "stage22-report-layout-smoke"
    symbol = "000001.XSHE"

    status, payload = dispatch_request(
        app,
        method="POST",
        path="/api/backtest/run-once",
        body=json.dumps(
            {
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
        ).encode("utf-8"),
    )
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit("report package layout smoke test failed: backtest did not complete")

    status, payload = dispatch_request(
        app,
        method="POST",
        path="/api/ai/workflow/run",
        body=json.dumps(
            {
                "symbol": symbol,
                "analysis_date": "2020-01-02",
                "report_id": run_id,
                "max_debate_rounds": 1,
                "enabled_analysts": ["market"],
                "enabled_researchers": ["bull", "bear"],
                "risk_team": ["neutral"],
                "provider_profile": "openai-compatible",
            }
        ).encode("utf-8"),
    )
    workflow = payload.get("workflow", {})
    if status != 200 or workflow.get("report_id") != run_id:
        raise SystemExit("report package layout smoke test failed: workflow not bound")

    status, payload = dispatch_request(
        app,
        method="POST",
        path=f"/api/reporting/run-detail/{quote(run_id)}/report-package",
        body=json.dumps({"symbol": symbol, "workflow_id": workflow.get("workflow_id"), "title": "Stage 22 layout package"}).encode("utf-8"),
    )
    package_id = payload.get("package", {}).get("package_id")
    if status != 200 or not package_id:
        raise SystemExit("report package layout smoke test failed: package missing")

    status, payload = dispatch_request(app, method="GET", path=f"/api/reporting/report-packages/{quote(package_id)}/export", query_string="format=pdf")
    exported = payload.get("export", {})
    content = exported.get("content", "")
    if status != 200 or not content.startswith("%PDF-1.4"):
        raise SystemExit("report package layout smoke test failed: PDF header missing")
    required_tokens = [
        "/Count 4",
        "Executive Overview",
        "Backtest And Strategy Review",
        "AI Workflow And Risk Committee",
        "Manifest, Sources, And Boundaries",
        "Page 1/4",
        "Page 4/4",
        "stage20-report-package-manifest-v1",
        "not investment advice",
    ]
    missing = [token for token in required_tokens if token not in content]
    if missing:
        raise SystemExit(f"report package layout smoke test failed: missing {missing}")
    if content.count("/Type /Page") < 4:
        raise SystemExit("report package layout smoke test failed: expected at least four page objects")

    output_dir = Path("output/pdf")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "stage22-report-package-layout-smoke.pdf"
    output_path.write_bytes(content.encode("latin-1"))
    if output_path.stat().st_size < 3000:
        raise SystemExit("report package layout smoke test failed: PDF artifact too small")

    print("report package layout smoke test passed")


if __name__ == "__main__":
    main()
