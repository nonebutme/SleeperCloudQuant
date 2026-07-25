"""Smoke test Stage 74 independent dual-layer and shared-portfolio reports."""

from __future__ import annotations

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.backtest_mode_report_service import BacktestModeReportService
    from data_platform import ClassificationHistoryStore

    store = ClassificationHistoryStore("tmp/stage74_classification_smoke.sqlite3")
    store.upsert_intervals([
        {"symbol": f"0000{i:02d}", "dimension": "industry", "category": "金融" if i < 5 else "科技", "valid_from": "2019-01-01", "valid_to": None, "source": "smoke", "observed_at": "2020-01-01"}
        for i in range(10)
    ])
    service = BacktestModeReportService(FakeReporting(), FakeIndependent(), FakeShared(), FakeRuntimeStore(), store)

    independent = service.get_independent_screening_report("screening-smoke")
    distribution = independent["distribution"]
    if independent.get("report_version") != "stage74-independent-dual-layer-report-v2":
        raise SystemExit("stage74 smoke failed: independent report version mismatch")
    expected_buckets = ["跌停", "-8%-", "-8~-6%", "-6~-4%", "-4~-2%", "-2~0%", "0~2%", "2~4%", "4~6%", "6~8%", "8%+", "涨停"]
    if [item.get("bucket") for item in distribution.get("histogram", [])] != expected_buckets:
        raise SystemExit("stage74 smoke failed: fixed A-share return buckets mismatch")
    if distribution["sample_size"] != 10 or distribution["normality"]["status"] != "tested":
        raise SystemExit("stage74 smoke failed: distribution/normality mismatch")
    if len(independent["group_comparisons"]["industry"]) != 2:
        raise SystemExit("stage74 smoke failed: historical industry comparison mismatch")
    if independent["classification_coverage"]["concept"]["coverage_ratio"] != 0.0:
        raise SystemExit("stage74 smoke failed: missing concepts must not use current snapshot")
    if len(independent.get("run_index") or []) != 10:
        raise SystemExit("stage74 smoke failed: selectable run index missing")
    if independent.get("factor_analysis", {}).get("version") != "stage74-factor-registry-v1":
        raise SystemExit("stage74 smoke failed: factor registry missing")
    if not any(item.get("factor") == "board" and item.get("status") == "available" for item in independent.get("factor_analysis", {}).get("factor_registry", [])):
        raise SystemExit("stage74 smoke failed: listed-board factor missing")
    tab_keys = set(independent.get("report_contract", {}).get("tabs", []))
    if tab_keys != {"task_statistics", "single_run_evaluation"}:
        raise SystemExit("stage74 smoke failed: independent dual-layer tabs mismatch")

    single = service.get_independent_run_report("screening-smoke", "run-0")
    dimensions = single.get("professional_report", {}).get("dimensions") or []
    if single.get("status") != "ready" or single.get("symbol") != "000000":
        raise SystemExit("stage74 smoke failed: independent run report unavailable")
    if len(dimensions) != 7 or dimensions[-1].get("key") != "execution_data":
        raise SystemExit("stage74 smoke failed: single-run dimension 7 semantic mismatch")
    if single.get("professional_report", {}).get("evaluation_scope") != "independent_single_symbol_virtual_account":
        raise SystemExit("stage74 smoke failed: single-run evaluation scope mismatch")
    if service.get_independent_run_report("screening-smoke", "shared-run").get("status") != "run_not_in_task":
        raise SystemExit("stage74 smoke failed: cross-task run access was not rejected")

    shared = service.get_shared_portfolio_report("portfolio-smoke")
    if shared["template"] != "shared_portfolio_strategy_evaluation_7_dimensions_v2":
        raise SystemExit("stage74 smoke failed: shared template mismatch")
    if shared["professional_report"]["average_score"] != 77 or not shared["data_quality_gate"]["score_allowed"]:
        raise SystemExit("stage74 smoke failed: shared evidence gate mismatch")
    if shared.get("semantic_boundary", {}).get("account_scope") != "single_shared_account":
        raise SystemExit("stage74 smoke failed: shared account semantic boundary mismatch")
    print("stage74 backtest mode reports smoke test passed")


class FakeIndependent:
    def get_task(self, task_id):
        return {"task_id": task_id, "status": "completed", "config": {"date_window": {"start_date": "2020-01-01"}}, "progress": {"total": 12, "processed": 12, "entered": 10, "no_entry": 2, "failed": 0}}

    def list_items(self, task_id, *, limit, offset, **kwargs):
        items = [{"symbol": f"0000{i:02d}", "name": f"Stock {i}", "market": "SZSE" if i < 5 else "SSE", "status": "completed", "entered": True, "run_id": f"run-{i}", "metrics": {"total_returns": (i - 4) / 20, "annualized_returns": (i - 4) / 10, "max_drawdown": -0.1, "sharpe": 1.0}} for i in range(10)]
        return {"total": len(items), "items": items[offset : offset + limit]}


class FakeShared:
    def get_task(self, task_id):
        return {"task_id": task_id, "status": "completed", "run_id": "shared-run"}


class FakeRuntimeStore:
    def fetch_backtest_trades(self, run_id):
        index = int(run_id.split("-")[-1])
        return [{"side": "BUY", "quantity": 100, "trade_time": f"2020-{index % 3 + 1:02d}-02T15:00:00+08:00"}]


class FakeReporting:
    def get_strategy_evaluation(self, run_id):
        dimensions = [
            {"key": key, "short_label": key, "title": f"dimension-{index}", "score": 77, "level": "good", "metrics": [], "chart": {"kind": "bar", "rows": []}}
            for index, key in enumerate(("return", "risk", "riskReturn", "stable", "attr", "cost", "diverse"), start=1)
        ]
        return {"average_score": 77, "run_id": run_id, "dimensions": dimensions, "evidence_quality": {"grade": "medium", "coverage_score": 0.75, "points": {"account_points": 2, "trade_points": 2}}}

    def get_run_detail(self, run_id):
        return {"run_id": run_id, "status": "completed", "accounts": [{"total_value": 100000}], "trades": [{"side": "BUY"}], "positions": [{"quantity": 100}], "yearly_returns": [{"year": 2020, "portfolio_return": 0.1}]}


if __name__ == "__main__":
    main()