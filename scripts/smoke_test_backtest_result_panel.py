"""Smoke test for stage 36 backtest result panel API."""

from __future__ import annotations

import json

from _project_bootstrap import ensure_project_root_on_sys_path


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    return dispatch_request(app, method=method, path=path, body=body)


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.runtime import build_demo_app

    app = build_demo_app()
    run_id = "stage36-result-panel-smoke"
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
            "end_date": "2020-01-10",
            "initial_cash": 1000000,
            "frequency": "1d",
            "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
            "extra_config": {"stage": "36", "smoke": True},
        },
    )
    result = payload.get("result", {})
    if status != 200 or result.get("run_id") != run_id or result.get("status") != "completed":
        raise SystemExit("stage36 smoke failed: backtest run did not complete")

    status, payload = _dispatch(app, "GET", f"/api/backtest/results/{run_id}/panel")
    panel = payload.get("result", {})
    summary = panel.get("summary", {})
    metrics = panel.get("metrics", {})
    if status != 200 or panel.get("run_id") != run_id or summary.get("run_id") != run_id:
        raise SystemExit("stage36 smoke failed: result panel summary invalid")
    if "total_returns" not in metrics or "max_drawdown" not in metrics:
        raise SystemExit("stage36 smoke failed: result panel metrics missing")
    for key in ("trades", "positions", "accounts", "yearly_returns", "logs"):
        if key not in panel or not isinstance(panel[key], list):
            raise SystemExit(f"stage36 smoke failed: result panel {key} missing")
    snapshot = panel.get("parameter_snapshot", {})
    if snapshot.get("parameters", {}).get("short_window") != 2 or snapshot.get("extra_config", {}).get("stage") != "36":
        raise SystemExit("stage36 smoke failed: parameter snapshot missing")
    if summary.get("trade_fill_count") != len(panel.get("trades", [])):
        raise SystemExit("stage36 smoke failed: trade fill count mismatch")
    realized_count = panel.get("trade_attribution", {}).get("roundtrip_count") or 0
    if summary.get("trade_count") != realized_count or metrics.get("trade_count") != realized_count:
        raise SystemExit("stage36 smoke failed: realized trade count mismatch")
    print("stage36 backtest result panel smoke test passed")


if __name__ == "__main__":
    main()
