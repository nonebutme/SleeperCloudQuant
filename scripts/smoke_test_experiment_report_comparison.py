"""Smoke test for stage 52 experiment-level report comparison."""

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
        raise SystemExit(f"stage52 smoke failed: backtest did not complete for {run_id}")


def main() -> None:
    ensure_project_root_on_sys_path()
    root = Path.cwd()
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    css = (root / "web" / "styles.css").read_text(encoding="utf-8")
    for needle, text, context in (
        ("report-experiment-comparison-summary", html, "web/index.html"),
        ("report-experiment-comparison-table", html, "web/index.html"),
        ("renderExperimentReportComparison", js, "web/app.js"),
        ("loadExperimentReportComparison", js, "web/app.js"),
        ("report-comparison-panel", css, "web/styles.css"),
    ):
        if needle not in text:
            raise SystemExit(f"stage52 smoke failed: missing {needle} in {context}")

    from app.runtime import build_demo_app

    app = build_demo_app()
    prefix = "stage52-report-comparison-smoke"
    symbol = "000001.XSHE"
    status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"})
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage52 smoke failed: market sync did not complete")

    _run(app, f"{prefix}-001", symbol, 2, 3)
    _run(app, f"{prefix}-002", symbol, 3, 4)

    status, payload = _dispatch(app, "GET", f"/api/reporting/experiments/{quote(prefix)}/comparison")
    comparison = payload.get("comparison", {})
    summary = comparison.get("summary", {})
    rows = comparison.get("rows", [])
    if status != 200 or comparison.get("status") != "ready" or len(rows) < 2:
        raise SystemExit("stage52 smoke failed: comparison did not return rows")
    if summary.get("run_count") < 2 or not summary.get("best_run_id"):
        raise SystemExit("stage52 smoke failed: comparison summary missing best run")
    if summary.get("asset_consistency_status") != "consistent":
        raise SystemExit("stage52 smoke failed: asset consistency should be consistent")
    if not all(row.get("score") is not None and row.get("data_version") for row in rows):
        raise SystemExit("stage52 smoke failed: comparison rows missing score/data_version")

    print("stage52 experiment report comparison smoke test passed")


if __name__ == "__main__":
    main()
