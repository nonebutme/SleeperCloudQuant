"""针对回测审计缺陷的数值回归；仅使用合成行情及内存 SQLite。"""
from __future__ import annotations

import json
import sqlite3
import unittest
from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()
from app.api.backtest import list_backtest_mode_tasks
from app.schemas.backtest import BacktestModeTaskDirectoryQueryPayload
from app.services.backtest_service import BacktestService
from app.services.persistent_backtest_service import PersistentBacktestService, _build_trade_attribution
from app.services.shared_portfolio_service import _run_shared_account
from app.services.single_backtest_task_service import SingleBacktestTaskService
from backtest_kernel import RunSingleBacktest
from backtest_kernel.adapters.local_sqlite_runtime import LocalSQLiteBacktestRuntime, _build_metrics, _build_yearly_returns
from backtest_kernel.adapters.rqalpha_ricequant_gateway import RqalphaRicequantGateway
from config_center.providers.ricequant_config import RicequantConfig
from domain.backtest.models import BacktestRunRequest

HOLD = 'def generate_target_weights(bars, parameters):\n    return [1.0 for bar in bars]\n'
CURRENT_CLOSE = 'def generate_target_weights(bars, parameters):\n    return [1.0 if bar["close"] > bar["open"] else 0.0 for bar in bars]\n'


def bars(prices=(10, 11), volume=100000):
    return [dict(date=f"2020-01-{2+i:02d}", open=10, high=p, low=10, close=p, volume=volume)
            for i, p in enumerate(prices)]


class Repository:
    def __init__(self, rows):
        self.rows = rows
        self.adjustment = None

    def fetch_price_history(self, *args, **kwargs):
        self.adjustment = kwargs.get("adjustment")
        return self.rows


def single(rows, source=HOLD, parameters=None):
    return LocalSQLiteBacktestRuntime(Repository(rows), strategy_resolver=lambda *args: {
        "source_code": source, "latest_version": "v1"
    }).run(dict(run_id="audit", strategy_name="audit", start_date="2020-01-02", end_date="2020-01-05",
               initial_cash=10000, benchmark="000300.XSHG", parameters=parameters or {}, extra_config={"strategy_id": "audit"}))


def portfolio(prepared, **overrides):
    config = dict(initial_cash=10000, parameters={}, max_positions=1, portfolio_exposure=.5,
                  commission_rate=0, min_commission=0, tax_rate=0, slippage_rate=0,
                  date_window={"start_date": "2020-01-02", "end_date": "2020-01-05"})
    config.update(overrides)
    return _run_shared_account(prepared, config, {}, [])


def payload(prices, weights, volume=100000):
    return dict(meta={"name": "sample"}, rows=bars(prices, volume), weights=weights)


class AuditRegression(unittest.TestCase):
    def test_first_day_loss_is_visible_in_report_curves(self):
        from app.services.persistent_backtest_service import _build_drawdown_curve
        from app.services.reporting_service import _account_drawdown_curve
        points = _build_drawdown_curve([{"value": .9}, {"value": .95}])
        self.assertAlmostEqual(points[0]["value"], -.1)
        accounts = _account_drawdown_curve([{"total_value": 9000, "unit_net_value": .9}])
        self.assertAlmostEqual(accounts[0]["value"], -.1)

    def test_reporting_preserves_benchmark_evidence(self):
        from verify_formal_reporting import FakeReportingStore
        from reporting import RunResultsReader
        from app.services.reporting_service import ReportingService
        store = FakeReportingStore()
        store._run["raw_result"] = {
            "benchmark_alignment": {"mode": "same_symbol_buy_hold"},
            "benchmark_status": "ready",
            "benchmark_curve": [{"date": "2020-01-02", "value": 1}, {"date": "2020-01-03", "value": 1.1}],
        }
        detail = ReportingService(RunResultsReader(store), None).get_run_detail(store._run["run_id"])
        self.assertEqual(detail.benchmark_alignment["mode"], "same_symbol_buy_hold")
        self.assertEqual(detail.benchmark_status, "ready")
        self.assertEqual(len(detail.benchmark_curve), 2)

    def test_open_uses_prior_close(self):
        for close in (9, 11):
            result = single(bars((close, 10)), CURRENT_CLOSE, {"execution_price": "open"})
            trades = result["raw_result"]["trades"]
            self.assertFalse(any(t["trade_time"].startswith("2020-01-02") for t in trades))
            self.assertEqual(bool(trades), close == 11)

    def test_declared_prior_signal_is_not_shifted_twice(self):
        source = 'SIGNAL_TIMING = "before_open"\ndef generate_target_weights(bars, parameters):\n    return [0.0] + [1.0 for b in bars[1:]]\n'
        result = single(bars((10, 11, 12)), source, {"execution_price": "open"})
        self.assertTrue(result["raw_result"]["trades"][0]["trade_time"].startswith("2020-01-03"))

    def test_shared_open_uses_prior_signal(self):
        raw, _ = portfolio({"A": payload((11, 10), [1, 0])}, parameters={"execution_price": "open"})
        self.assertTrue(raw["trades"][0]["trade_time"].startswith("2020-01-03"))

    def test_zero_volume_has_valuation_but_no_fills(self):
        result = single(bars(volume=0))
        self.assertEqual(result["raw_result"]["trades"], [])
        self.assertEqual(len(result["raw_result"]["accounts"]), 2)
        raw, _ = portfolio({"A": payload((10, 11), [1, 1], 0)})
        self.assertEqual(raw["trades"], [])

    def test_explicit_suspension_blocks_fills(self):
        rows = bars()
        for row in rows:
            row["datasets"] = {"trading_status": {"is_tradable": False}}
        self.assertEqual(single(rows)["raw_result"]["trades"], [])
        raw, _ = portfolio({"A": dict(meta={}, rows=rows, weights=[1, 1])})
        self.assertEqual(raw["trades"], [])

    def test_cash_includes_fees(self):
        result = single(bars((10, 10)))
        accounts = result["raw_result"]["accounts"]
        self.assertTrue(all(a["cash"] >= 0 for a in accounts))
        self.assertEqual(result["raw_result"]["trades"][0]["quantity"], 900)

    def test_unsold_incumbent_occupies_slot(self):
        raw, _ = portfolio({"000001": payload((10, 9), [1, 0]), "000002": payload((10, 10), [0, 1])})
        self.assertEqual(len(raw["final_holdings"]), 1)
        self.assertEqual(raw["final_holdings"][0]["symbol"], "000001")

    def test_unsold_incumbent_consumes_exposure(self):
        raw, _ = portfolio({"000001": payload((10, 9), [1, 0]), "000002": payload((10, 10), [0, 1])}, max_positions=2)
        last = raw["accounts"][-1]
        self.assertLessEqual(last["market_value"] / last["total_value"], .5)

    def test_first_day_loss_counts_in_drawdown(self):
        self.assertAlmostEqual(_build_metrics([("2020-01-02", 90), ("2020-01-03", 90)], 100)["max_drawdown"], -.1)

    def test_years_compound_and_benchmark_not_zero(self):
        curve = [("2019-12-31", 100), ("2020-01-02", 110), ("2020-12-31", 121)]
        result = _build_yearly_returns(curve, initial_cash=100, benchmark_curve=curve)
        self.assertAlmostEqual(result[1]["portfolio_return"], .21)
        self.assertAlmostEqual(result[1]["benchmark_return"], .21)
        self.assertEqual(result[1]["excess_return"], 0)
        from app.services.shared_portfolio_service import _yearly_returns
        shared = _yearly_returns([("2019-12-31", 90), ("2020-12-31", 99)], 100,
                                [("2019-12-31", 1), ("2020-12-31", 1.1)])
        self.assertAlmostEqual(shared[0]["portfolio_return"], -.1)
        self.assertAlmostEqual((1 + shared[0]["portfolio_return"]) * (1 + shared[1]["portfolio_return"]), .99)

    def test_buy_commission_changes_win_to_loss(self):
        trades = [dict(side="BUY", order_book_id="A", amount=1000, quantity=100, commission=5),
                  dict(side="SELL", order_book_id="A", amount=1003, quantity=100, commission=1)]
        result = _build_trade_attribution(trades)
        self.assertEqual(result["estimated_win_count"], 0)
        self.assertEqual(result["estimated_loss_count"], 1)

    def test_task_freezes_version_and_passes_adjustment(self):
        repo = Repository(bars())
        base = BacktestService(RunSingleBacktest(RqalphaRicequantGateway(
            RicequantConfig(username="audit", password="audit"), runtime=LocalSQLiteBacktestRuntime(repo))))
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        service = SingleBacktestTaskService.__new__(SingleBacktestTaskService)
        class Strategy:
            def resolve_version(self, *args):
                return dict(latest_version="v7", source_code=HOLD, source_sha256="test-hash")
        service._strategy_service = Strategy()
        service._market_data_service = None
        service._dataset_resolver = None
        service._backtest_service = base
        service._connect = lambda: connection
        service._ensure_schema()
        try:
            task = service.create_task(task_id="audit", strategy_id="audit", symbol="000001.XSHE",
                                       adjustment="qfq", start_date="2020-01-02", end_date="2020-01-03")
            self.assertEqual(task["config"]["strategy_version"], "v7")
            self.assertEqual(task["config"]["source_sha256"], "test-hash")
            service._execute_task("audit")
            self.assertEqual(service.get_task("audit")["status"], "completed")
            self.assertEqual(repo.adjustment, "qfq")
        finally:
            connection.close()

    def test_independent_trace_matches_parameters(self):
        class Market:
            def get_published_data_version(self, **kwargs):
                return {"status": "bound", "adjustment": kwargs["adjustment"]}
        service = PersistentBacktestService(None, None, Market())
        request = BacktestRunRequest(run_id="audit", strategy_name="audit", symbol="A", benchmark="B",
                                     start_date="2020-01-02", end_date="2020-01-03", parameters={"adjustment": "qfq"})
        self.assertEqual(service._build_data_asset_trace(request=request, bound_at="audit")["asset"]["adjustment"], "qfq")

    def test_history_search_and_pagination(self):
        class Service:
            def __init__(self, rows): self.rows = rows
            def list_tasks(self, *, limit=30): return self.rows[:limit]
        rows = [dict(task_id=f"task-{i}", status="completed", config={"name": f"task-{i}"}, run_id=f"run-{i}") for i in range(201)]
        empty, service = Service([]), Service(rows)
        found = list_backtest_mode_tasks(empty, empty, BacktestModeTaskDirectoryQueryPayload(search="task-200"), service)
        self.assertEqual(found.tasks[0]["task_id"], "task-200")
        last = list_backtest_mode_tasks(empty, empty, BacktestModeTaskDirectoryQueryPayload(limit=20, offset=200), service)
        self.assertEqual(len(last.tasks), 1)
        self.assertEqual(last.summary["task_count"], 201)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AuditRegression)
    outcome = unittest.TextTestRunner().run(suite)
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
