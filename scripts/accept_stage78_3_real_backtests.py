"""Run three real backtest modes against the published stage-78.3 release."""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import quote

from _project_bootstrap import ensure_project_root_on_sys_path


EXPECTED_VERSION = "scq-20260724-06a16f4a9fb078d9"
SYMBOLS = ["000001", "600000", "300750"]
START_DATE = "2026-05-01"
END_DATE = "2026-07-24"


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.runtime import build_demo_app, dispatch_request

    app = build_demo_app()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")

    def dispatch(
        method: str,
        path: str,
        payload: dict | None = None,
        query_string: str = "",
    ) -> dict:
        body = (
            json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
            if method == "POST"
            else None
        )
        status, response = dispatch_request(
            app,
            method=method,
            path=path,
            query_string=query_string,
            body=body,
        )
        if status != 200:
            raise RuntimeError(f"{method} {path} failed: {status} {response}")
        return response

    single_task_id = f"stage783-single-{stamp}"
    single_run_id = f"{single_task_id}-run"
    single = dispatch(
        "POST",
        "/api/backtest/single-backtest-tasks",
        {
            "task_id": single_task_id,
            "run_id": single_run_id,
            "name": "阶段78.3单品种真实验收",
            "strategy_name": "moving_average_strategy",
            "strategy_id": "moving_average_strategy",
            "strategy_version": "v1",
            "symbol": "000001.XSHE",
            "benchmark": "000300.XSHG",
            "start_date": START_DATE,
            "end_date": END_DATE,
            "initial_cash": 1_000_000,
            "frequency": "1d",
            "adjustment": "qfq",
            "parameters": {
                "short_window": 5,
                "long_window": 20,
                "position_size": 0.9,
            },
            "extra_config": {"runtime_mode": "local_sqlite_backtest"},
        },
    )["task"]
    single = dispatch(
        "POST",
        f"/api/backtest/single-backtest-tasks/{quote(single_task_id)}/run",
        {"wait": True},
    )["task"]
    if single.get("status") != "completed":
        raise RuntimeError(f"single backtest failed: {single}")
    panel = dispatch(
        "GET",
        f"/api/backtest/results/{quote(single_run_id)}/panel",
    )["result"]
    _assert_panel(panel, single_run_id)
    single_report = dispatch(
        "GET",
        f"/api/reporting/run-detail/{quote(single_run_id)}",
    )["detail"]
    _assert_run_detail(single_report, "single report")

    independent_task_id = f"stage783-independent-{stamp}"
    independent = dispatch(
        "POST",
        "/api/backtest/independent-screening-tasks",
        {
            "task_id": independent_task_id,
            "name": "阶段78.3独立账户批量真实验收",
            "strategy_id": "moving_average_strategy",
            "strategy_version": "v1",
            "symbols": SYMBOLS,
            "market": "",
            "start_date": START_DATE,
            "end_date": END_DATE,
            "adjustment": "qfq",
            "benchmark": "000300.XSHG",
            "initial_cash": 1_000_000,
            "parameters": {
                "short_window": 5,
                "long_window": 20,
                "position_size": 0.9,
            },
            "max_workers": 3,
            "retry_count": 1,
            "symbol_limit": 3,
        },
    )["task"]
    independent = dispatch(
        "POST",
        f"/api/backtest/independent-screening-tasks/{quote(independent_task_id)}/run",
        {"wait": True},
    )["task"]
    if independent.get("status") not in {"completed", "partial_completed"}:
        raise RuntimeError(f"independent backtest failed: {independent}")
    independent_items = dispatch(
        "GET",
        f"/api/backtest/independent-screening-tasks/{quote(independent_task_id)}/items",
        query_string="limit=10",
    )["result"]
    items = list(independent_items.get("items") or [])
    if len(items) != 3 or any(item.get("status") == "failed" for item in items):
        raise RuntimeError(f"independent items invalid: {independent_items}")
    for item in items:
        run_id = str(item.get("run_id") or "")
        run_panel = dispatch(
            "GET",
            f"/api/backtest/results/{quote(run_id)}/panel",
        )["result"]
        _assert_panel(run_panel, run_id)

    independent_report = dispatch(
        "GET",
        f"/api/reporting/backtest-modes/independent-screening/{quote(independent_task_id)}",
    )["report"]
    _assert_report(independent_report, "independent report")

    portfolio_task_id = f"stage783-portfolio-{stamp}"
    portfolio = dispatch(
        "POST",
        "/api/backtest/shared-portfolio-tasks",
        {
            "task_id": portfolio_task_id,
            "name": "阶段78.3投资组合真实验收",
            "strategy_id": "moving_average_strategy",
            "strategy_version": "v1",
            "symbols": SYMBOLS,
            "market": "",
            "start_date": START_DATE,
            "end_date": END_DATE,
            "adjustment": "qfq",
            "benchmark": "000300.XSHG",
            "initial_cash": 1_000_000,
            "parameters": {
                "short_window": 5,
                "long_window": 20,
                "position_size": 0.9,
            },
            "max_workers": 3,
            "symbol_limit": 3,
            "max_positions": 3,
            "portfolio_exposure": 0.9,
            "commission_rate": 0.0003,
            "min_commission": 5,
            "tax_rate": 0.001,
            "slippage_rate": 0.0005,
        },
    )["task"]
    _assert_version(portfolio, "portfolio task")
    portfolio = dispatch(
        "POST",
        f"/api/backtest/shared-portfolio-tasks/{quote(portfolio_task_id)}/run",
        {"wait": True},
    )["task"]
    if portfolio.get("status") != "completed":
        raise RuntimeError(f"portfolio backtest failed: {portfolio}")
    portfolio_run_id = str(portfolio.get("run_id") or "")
    portfolio_panel = dispatch(
        "GET",
        f"/api/backtest/results/{quote(portfolio_run_id)}/panel",
    )["result"]
    _assert_panel(portfolio_panel, portfolio_run_id)
    portfolio_report = dispatch(
        "GET",
        f"/api/reporting/backtest-modes/shared-portfolio/{quote(portfolio_task_id)}",
    )["report"]
    _assert_report(portfolio_report, "portfolio report")

    result = {
        "status": "passed",
        "data_version": EXPECTED_VERSION,
        "single": {
            "task_id": single_task_id,
            "run_id": single_run_id,
            "status": single["status"],
            "metrics": panel.get("summary", {}).get("metrics", {}),
        },
        "independent": {
            "task_id": independent_task_id,
            "status": independent["status"],
            "progress": independent.get("progress"),
            "run_ids": [item.get("run_id") for item in items],
        },
        "portfolio": {
            "task_id": portfolio_task_id,
            "run_id": portfolio_run_id,
            "status": portfolio["status"],
            "metrics": portfolio_panel.get("summary", {}).get("metrics", {}),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _assert_version(payload: dict, label: str) -> None:
    config = dict(payload.get("config") or {})
    binding = dict(config.get("data_version_binding") or {})
    version = (
        binding.get("data_version")
        or payload.get("data_version")
        or dict(payload.get("input_snapshot") or {}).get("data_version")
    )
    if version != EXPECTED_VERSION:
        raise RuntimeError(f"{label} data version mismatch: {version}")


def _assert_panel(panel: dict, run_id: str) -> None:
    if panel.get("status") != "completed":
        raise RuntimeError(f"result panel unavailable for {run_id}: {panel}")
    trace = dict(panel.get("data_asset_trace") or {})
    asset = dict(trace.get("asset") or {})
    version = (
        asset.get("data_version")
        or dict(panel.get("summary") or {}).get("data_version")
    )
    if trace.get("status") != "bound" or version != EXPECTED_VERSION:
        raise RuntimeError(f"result panel version mismatch for {run_id}: {trace}")


def _assert_report(report: dict, label: str) -> None:
    if report.get("status") not in {"completed", "ready"}:
        raise RuntimeError(f"{label} unavailable: {report}")



def _assert_run_detail(detail: dict, label: str) -> None:
    if not detail.get("metrics") or not detail.get("account_value_chart"):
        raise RuntimeError(f"{label} unavailable: {detail}")

if __name__ == "__main__":
    main()
