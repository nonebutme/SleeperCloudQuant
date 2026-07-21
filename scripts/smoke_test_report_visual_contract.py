"""Smoke test for stage 51 report visual layout contract."""

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


def _assert_contains(text: str, needle: str, context: str) -> None:
    if needle not in text:
        raise SystemExit(f"stage51 smoke failed: missing {needle} in {context}")


def main() -> None:
    ensure_project_root_on_sys_path()
    root = Path.cwd()
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    css = (root / "web" / "styles.css").read_text(encoding="utf-8")

    for needle in (
        "report-analysis-panel",
        "report-analysis-cards",
        "report-data-asset-summary",
        "report-action-items",
    ):
        _assert_contains(html, needle, "web/index.html")
    for needle in (
        "analysis-card",
        "asset-chip",
        "report-action-item",
        "@media (max-width: 1180px)",
        "@media (max-width: 560px)",
    ):
        _assert_contains(css, needle, "web/styles.css")
    for needle in (
        "renderReportAnalysisSummary",
        "analysis-card-${card.key",
        "asset-chip",
        "report-action-item",
    ):
        _assert_contains(js, needle, "web/app.js")

    from app.runtime import build_demo_app

    app = build_demo_app()

    run_id = "stage51-report-visual-contract"
    symbol = "000001.XSHE"
    status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"})
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage51 smoke failed: market sync did not complete")
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
        raise SystemExit("stage51 smoke failed: backtest did not complete")
    status, payload = _dispatch(app, "GET", f"/api/reporting/strategy-evaluation/{quote(run_id)}")
    summary = payload.get("report", {}).get("analysis_summary", {})
    if status != 200 or len(summary.get("cards") or []) < 6 or not summary.get("data_asset", {}).get("data_version"):
        raise SystemExit("stage51 smoke failed: report analysis payload is not renderable")

    print("stage51 report visual contract smoke test passed")


if __name__ == "__main__":
    main()

