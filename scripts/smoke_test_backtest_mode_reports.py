"""Smoke test Stage 63 statistical and shared-template reports."""

from __future__ import annotations

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.backtest_mode_report_service import BacktestModeReportService
    from data_platform import ClassificationHistoryStore

    store = ClassificationHistoryStore("tmp/stage63_classification_smoke.sqlite3")
    store.upsert_intervals([
        {"symbol": f"0000{i:02d}", "dimension": "industry", "category": "金融" if i < 5 else "科技", "valid_from": "2019-01-01", "valid_to": None, "source": "smoke", "observed_at": "2020-01-01"}
        for i in range(10)
    ])
    service = BacktestModeReportService(FakeReporting(), FakeIndependent(), FakeShared(), FakeRuntimeStore(), store)
    independent = service.get_independent_screening_report("screening-smoke")
    distribution = independent["distribution"]
    if distribution["sample_size"] != 10 or distribution["normality"]["status"] != "tested":
        raise SystemExit("stage63 smoke failed: distribution/normality mismatch")
    if len(independent["group_comparisons"]["industry"]) != 2:
        raise SystemExit("stage63 smoke failed: historical industry comparison mismatch")
    if independent["classification_coverage"]["concept"]["coverage_ratio"] != 0.0:
        raise SystemExit("stage63 smoke failed: missing concepts must not use current snapshot")
    shared = service.get_shared_portfolio_report("portfolio-smoke")
    if shared["template"] != "current_strategy_evaluation_7_dimensions" or shared["professional_report"]["average_score"] != 77:
        raise SystemExit("stage63 smoke failed: shared template reuse mismatch")
    print("stage63 backtest mode reports smoke test passed")


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
        return {"average_score": 77, "run_id": run_id}

    def get_run_detail(self, run_id):
        return {"run_id": run_id, "status": "completed"}


if __name__ == "__main__":
    main()
