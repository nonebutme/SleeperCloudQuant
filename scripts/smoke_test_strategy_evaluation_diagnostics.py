"""Smoke test for stage 43 strategy evaluation diagnostics."""

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
    run_id = "stage43-strategy-diagnostics"
    status, payload = _dispatch(
        app,
        "POST",
        "/api/backtest/run-once",
        {
            "run_id": run_id,
            "strategy_name": "moving_average_strategy",
            "strategy_id": "moving_average_strategy",
            "strategy_version": "v1",
            "symbol": "000001.XSHE",
            "benchmark": "000300.XSHG",
            "start_date": "2020-01-01",
            "end_date": "2020-02-15",
            "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
            "extra_config": {"rqalpha_local": {"commission_rate": 0.0003, "tax_rate": 0.001, "slippage_rate": 0.0005}},
        },
    )
    if status != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit("stage43 smoke failed: backtest did not complete")

    status, payload = _dispatch(app, "GET", f"/api/reporting/strategy-evaluation/{quote(run_id)}")
    report = payload.get("report", {})
    diagnostics = report.get("diagnostics", {})
    if status != 200 or report.get("average_score") is None:
        raise SystemExit("stage43 smoke failed: evaluation missing")
    required_sections = {"return", "risk", "stability", "trade_quality", "capacity_cost", "exposure", "data_quality"}
    if not required_sections.issubset(set(diagnostics.keys())):
        raise SystemExit("stage43 smoke failed: diagnostics sections missing")
    if report.get("score_breakdown", {}).get("formula_version") != "stage43-diagnostic-score-v1":
        raise SystemExit("stage43 smoke failed: score formula missing")
    if not report.get("decision_flags") or not any(flag.get("key") == "data_coverage" for flag in report.get("decision_flags", [])):
        raise SystemExit("stage43 smoke failed: decision flags missing")
    if diagnostics.get("capacity_cost", {}).get("estimated_cost_rate") is None:
        raise SystemExit("stage43 smoke failed: cost diagnostics missing")

    status, payload = _dispatch(app, "POST", f"/api/reporting/run-detail/{quote(run_id)}/report-package", {"title": "Stage 43 diagnostics package"})
    package = payload.get("package", {})
    if status != 200 or package.get("strategy_evaluation", {}).get("diagnostics", {}).get("risk") is None:
        raise SystemExit("stage43 smoke failed: package diagnostics missing")
    package_id = package.get("package_id")
    status, payload = _dispatch(app, "GET", f"/api/reporting/report-packages/{quote(package_id)}/export?format=json")
    exported = payload.get("export", {})
    if status != 200 or "stage43-diagnostic-score-v1" not in exported.get("content", ""):
        raise SystemExit("stage43 smoke failed: exported package diagnostics missing")

    print("stage43 strategy evaluation diagnostics smoke test passed")


if __name__ == "__main__":
    main()
