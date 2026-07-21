"""Smoke test for stage 53 experiment comparison charts."""

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
        raise SystemExit(f"stage53 smoke failed: backtest did not complete for {run_id}")


def main() -> None:
    ensure_project_root_on_sys_path()
    root = Path.cwd()
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    css = (root / "web" / "styles.css").read_text(encoding="utf-8")
    for needle, text, context in (
        ("report-experiment-comparison-charts", html, "web/index.html"),
        ("renderExperimentComparisonCharts", js, "web/app.js"),
        ("renderComparisonBarSvg", js, "web/app.js"),
        ("comparison-chart", css, "web/styles.css"),
        ("version-strip", css, "web/styles.css"),
    ):
        if needle not in text:
            raise SystemExit(f"stage53 smoke failed: missing {needle} in {context}")

    from app.runtime import build_demo_app

    app = build_demo_app()
    prefix = "stage53-report-comparison-charts"
    symbol = "000001.XSHE"
    status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-01-02", "end_date": "2020-01-10"})
    if status != 200 or payload.get("summary", {}).get("row_count", 0) <= 0:
        raise SystemExit("stage53 smoke failed: market sync did not complete")

    _run(app, f"{prefix}-001", symbol, 2, 3)
    _run(app, f"{prefix}-002", symbol, 3, 5)
    _run(app, f"{prefix}-003", symbol, 4, 6)

    status, payload = _dispatch(app, "GET", f"/api/reporting/experiments/{quote(prefix)}/comparison")
    comparison = payload.get("comparison", {})
    rows = comparison.get("rows", [])
    summary = comparison.get("summary", {})
    if status != 200 or comparison.get("status") != "ready" or len(rows) < 3:
        raise SystemExit("stage53 smoke failed: comparison did not return enough rows")
    if not all(row.get("score") is not None for row in rows):
        raise SystemExit("stage53 smoke failed: score chart source missing")
    if not all(row.get("annualized_return") is not None for row in rows):
        raise SystemExit("stage53 smoke failed: annualized chart source missing")
    if not all(row.get("max_drawdown") is not None for row in rows):
        raise SystemExit("stage53 smoke failed: drawdown chart source missing")
    if summary.get("asset_consistency_status") != "consistent" or summary.get("data_version_count") != 1:
        raise SystemExit("stage53 smoke failed: version strip source inconsistent")

    print("stage53 experiment report comparison charts smoke test passed")


if __name__ == "__main__":
    main()
