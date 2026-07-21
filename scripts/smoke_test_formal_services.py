"""Smoke test for the new formal domain and service-layer skeleton."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


def _bootstrap() -> None:
    ensure_project_root_on_sys_path()


def main() -> None:
    _bootstrap()

    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from app.services import BacktestService, BatchResearchService, FactorResearchService, MarketDataService, PersistentBacktestService, ReportingService
    from backtest_kernel import RqalphaRicequantGateway, RunSingleBacktest
    from config_center.providers.ricequant_config import RicequantConfig
    from data_platform import CachedMarketDataRepository, SqliteMetadataStore
    from domain.backtest import BacktestResultSummary, BacktestRunRequest, BatchBacktestRunRequest
    from factor_lab import FactorDefinition, FactorValue, SqliteFactorStore
    from reporting import BatchComparisonService, RunResultsReader

    database_path = Path("tmp") / "formal_services_smoke.sqlite3"
    store = SqliteMetadataStore(database_path)
    runtime_store = SqliteRuntimeStore(database_path)
    market_service = MarketDataService(CachedMarketDataRepository(FakeMarketDataRepository(), store))
    factor_store = SqliteFactorStore(database_path)
    factor_service = FactorResearchService(market_service, factor_store)
    factor_service.run_factor_for_symbols(factor_id="close_to_close_return_1d", symbols=["000001.XSHE", "600000.XSHG"], start_date="2020-01-01", end_date="2020-01-02")
    factor_service.run_factor_for_symbols(factor_id="close_to_ma2_bias", symbols=["000001.XSHE", "600000.XSHG"], start_date="2020-01-01", end_date="2020-01-02")
    _seed_tie_rank_factor(factor_store)
    if len(market_service.get_price_history(symbol="000001.XSHE", start_date="2020-01-01", end_date="2020-01-02")) != 2:
        raise SystemExit("formal services smoke test failed: market service returned no bars")
    default_pool_members = factor_service.get_pool_members(index_code="000300.XSHG")
    if default_pool_members != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal services smoke test failed: default pool members mismatch")
    pool_members = factor_service.get_pool_members(index_code="000300.XSHG", date="2020-01-02")
    if pool_members != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal services smoke test failed: pool members mismatch")
    dated_pool_members = factor_service.get_pool_members(index_code="000300.XSHG", date="2020-01-01")
    if dated_pool_members != ["000001.XSHE"]:
        raise SystemExit("formal services smoke test failed: dated pool members mismatch")
    later_pool_members = factor_service.get_pool_members(index_code="000300.XSHG", date="2020-01-03")
    if later_pool_members != ["600000.XSHG"]:
        raise SystemExit("formal services smoke test failed: later pool members mismatch")
    if factor_service.get_pool_members(index_code="UNKNOWN.XSHG"):
        raise SystemExit("formal services smoke test failed: unknown default pool members should be empty")
    if factor_service.get_pool_members(index_code="UNKNOWN.XSHG", date="2020-01-02"):
        raise SystemExit("formal services smoke test failed: unknown pool members should be empty")
    summary_rows = factor_service.get_factor_summary(symbol="000001.XSHE", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if len(summary_rows) != 2:
        raise SystemExit("formal services smoke test failed: factor summary mismatch")
    filtered_summary_rows = factor_service.get_factor_summary(symbol="000001.XSHE", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=["close_to_ma2_bias"])
    if len(filtered_summary_rows) != 1 or filtered_summary_rows[0].factor_id != "close_to_ma2_bias":
        raise SystemExit("formal services smoke test failed: filtered factor summary mismatch")
    default_scope_missing_summary_rows = factor_service.get_factor_summary(symbol="000001.XSHE", trade_date="2020-01-02", factor_ids=["unknown_factor"])
    if default_scope_missing_summary_rows:
        raise SystemExit("formal services smoke test failed: default-scope unknown factor summary should be empty")
    missing_summary_rows = factor_service.get_factor_summary(symbol="000001.XSHE", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=["unknown_factor"])
    if missing_summary_rows:
        raise SystemExit("formal services smoke test failed: unknown factor summary should be empty")
    unknown_symbol_unknown_factor_summary_rows = factor_service.get_factor_summary(symbol="UNKNOWN.XSHG", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=["unknown_factor"])
    if unknown_symbol_unknown_factor_summary_rows:
        raise SystemExit("formal services smoke test failed: unknown symbol and unknown factor summary should be empty")
    unknown_symbol_summary_rows = factor_service.get_factor_summary(symbol="UNKNOWN.XSHG", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if unknown_symbol_summary_rows:
        raise SystemExit("formal services smoke test failed: unknown symbol summary should be empty")
    empty_trade_date_summary_rows = factor_service.get_factor_summary(symbol="000001.XSHE", trade_date="2020-01-01", start_date="2020-01-01", end_date="2020-01-02")
    if empty_trade_date_summary_rows:
        raise SystemExit("formal services smoke test failed: empty trade-date summary should be empty")
    filtered_empty_trade_date_summary_rows = factor_service.get_factor_summary(symbol="000001.XSHE", trade_date="2020-01-01", start_date="2020-01-01", end_date="2020-01-02", factor_ids=["close_to_ma2_bias"])
    if filtered_empty_trade_date_summary_rows:
        raise SystemExit("formal services smoke test failed: filtered empty trade-date summary should be empty")
    default_cross_section_summary = factor_service.get_pool_factor_summary(index_code="000300.XSHG", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if list(default_cross_section_summary.keys()) != ["000001.XSHE", "600000.XSHG"] or any(len(rows) != 2 for rows in default_cross_section_summary.values()):
        raise SystemExit("formal services smoke test failed: default factor cross-section summary mismatch")
    cross_section_summary = factor_service.get_pool_factor_summary(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if list(cross_section_summary.keys()) != ["000001.XSHE", "600000.XSHG"] or any(len(rows) != 2 for rows in cross_section_summary.values()):
        raise SystemExit("formal services smoke test failed: factor cross-section summary mismatch")
    dated_cross_section_summary = factor_service.get_pool_factor_summary(index_code="000300.XSHG", date="2020-01-01", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if list(dated_cross_section_summary.keys()) != ["000001.XSHE"] or any(len(rows) != 2 for rows in dated_cross_section_summary.values()):
        raise SystemExit("formal services smoke test failed: dated factor cross-section summary mismatch")
    later_cross_section_summary = factor_service.get_pool_factor_summary(index_code="000300.XSHG", date="2020-01-03", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if list(later_cross_section_summary.keys()) != ["600000.XSHG"] or any(len(rows) != 2 for rows in later_cross_section_summary.values()):
        raise SystemExit("formal services smoke test failed: later factor cross-section summary mismatch")
    filtered_cross_section_summary = factor_service.get_pool_factor_summary(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=["close_to_close_return_1d"])
    if list(filtered_cross_section_summary.keys()) != ["000001.XSHE", "600000.XSHG"] or any(len(rows) != 1 or rows[0].factor_id != "close_to_close_return_1d" for rows in filtered_cross_section_summary.values()):
        raise SystemExit("formal services smoke test failed: filtered factor cross-section summary mismatch")
    missing_cross_section_summary = factor_service.get_pool_factor_summary(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=["unknown_factor"])
    if list(missing_cross_section_summary.keys()) != ["000001.XSHE", "600000.XSHG"] or any(rows for rows in missing_cross_section_summary.values()):
        raise SystemExit("formal services smoke test failed: unknown factor cross-section summary should be empty")
    later_unknown_factor_cross_section_summary = factor_service.get_pool_factor_summary(index_code="000300.XSHG", date="2020-01-03", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=["unknown_factor"])
    if list(later_unknown_factor_cross_section_summary.keys()) != ["600000.XSHG"] or any(rows for rows in later_unknown_factor_cross_section_summary.values()):
        raise SystemExit("formal services smoke test failed: later unknown factor cross-section summary should preserve symbols and return empty rows")
    empty_trade_date_cross_section = factor_service.get_pool_factor_summary(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-01", start_date="2020-01-01", end_date="2020-01-02")
    if list(empty_trade_date_cross_section.keys()) != ["000001.XSHE", "600000.XSHG"] or any(rows for rows in empty_trade_date_cross_section.values()):
        raise SystemExit("formal services smoke test failed: empty trade-date cross-section summary should preserve symbols and return empty rows")
    filtered_empty_trade_date_cross_section = factor_service.get_pool_factor_summary(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-01", start_date="2020-01-01", end_date="2020-01-02", factor_ids=["close_to_close_return_1d"])
    if list(filtered_empty_trade_date_cross_section.keys()) != ["000001.XSHE", "600000.XSHG"] or any(rows for rows in filtered_empty_trade_date_cross_section.values()):
        raise SystemExit("formal services smoke test failed: filtered empty trade-date cross-section summary should preserve symbols and return empty rows")
    default_unknown_pool_cross_section = factor_service.get_pool_factor_summary(index_code="UNKNOWN.XSHG", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if default_unknown_pool_cross_section:
        raise SystemExit("formal services smoke test failed: unknown default pool cross-section summary should be empty")
    unknown_pool_cross_section = factor_service.get_pool_factor_summary(index_code="UNKNOWN.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if unknown_pool_cross_section:
        raise SystemExit("formal services smoke test failed: unknown pool cross-section summary should be empty")
    default_scope_values = factor_service.get_factor_values(factor_id="close_to_close_return_1d", symbol="000001.XSHE")
    if default_scope_values:
        raise SystemExit("formal services smoke test failed: default scope factor values should be empty")
    default_scope_unknown_factor_values = factor_service.get_factor_values(factor_id="unknown_factor", symbol="000001.XSHE")
    if default_scope_unknown_factor_values:
        raise SystemExit("formal services smoke test failed: default-scope unknown factor values should be empty")
    exact_scope_values = factor_service.get_factor_values(factor_id="close_to_close_return_1d", symbol="000001.XSHE", start_date="2020-01-01", end_date="2020-01-02")
    if len(exact_scope_values) != 1 or exact_scope_values[0].trade_date != "2020-01-02":
        raise SystemExit("formal services smoke test failed: exact scope factor values mismatch")
    unmatched_scope_values = factor_service.get_factor_values(factor_id="close_to_close_return_1d", symbol="000001.XSHE", start_date="2020-01-02", end_date="2020-01-02")
    if unmatched_scope_values:
        raise SystemExit("formal services smoke test failed: unmatched scope factor values should be empty")
    if factor_service.get_factor_values(factor_id="unknown_factor", symbol="000001.XSHE", start_date="2020-01-01", end_date="2020-01-02"):
        raise SystemExit("formal services smoke test failed: unknown factor values should be empty")
    if factor_service.get_factor_values(factor_id="unknown_factor", symbol="UNKNOWN.XSHG", start_date="2020-01-01", end_date="2020-01-02"):
        raise SystemExit("formal services smoke test failed: unknown symbol and unknown factor values should be empty")
    if factor_service.get_factor_values(factor_id="close_to_close_return_1d", symbol="UNKNOWN.XSHG", start_date="2020-01-01", end_date="2020-01-02"):
        raise SystemExit("formal services smoke test failed: unknown symbol factor values should be empty")
    if factor_service.get_factor_values(factor_id="close_to_close_return_1d", symbol="UNKNOWN.XSHG"):
        raise SystemExit("formal services smoke test failed: unknown symbol default-scope factor values should be empty")
    default_scope_missing_top_n = factor_service.get_factor_top_n(factor_id="unknown_factor", trade_date="2020-01-02", start_date=None, end_date=None)
    if default_scope_missing_top_n.row_count != 0 or default_scope_missing_top_n.rows:
        raise SystemExit("formal services smoke test failed: default-scope unknown factor top-n should be empty")
    default_top_n = factor_service.get_factor_top_n(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")
    if [row.symbol for row in default_top_n.rows] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal services smoke test failed: default top-n order mismatch")
    default_scope_summary_rows = factor_service.get_factor_summary(symbol="000001.XSHE", trade_date="2020-01-02")
    if default_scope_summary_rows:
        raise SystemExit("formal services smoke test failed: default-scope summary should be empty")
    default_scope_cross_section_summary = factor_service.get_pool_factor_summary(index_code="000300.XSHG", trade_date="2020-01-02")
    if list(default_scope_cross_section_summary.keys()) != ["000001.XSHE", "600000.XSHG"] or any(rows for rows in default_scope_cross_section_summary.values()):
        raise SystemExit("formal services smoke test failed: default-scope cross-section summary should preserve symbols and return empty rows")
    descending_top_n = factor_service.get_factor_top_n(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit=2, descending=True)
    if [row.symbol for row in descending_top_n.rows] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal services smoke test failed: descending top-n order mismatch")
    ascending_top_n = factor_service.get_factor_top_n(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit=2, descending=False)
    if [row.symbol for row in ascending_top_n.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal services smoke test failed: ascending top-n order mismatch")
    zero_limit_top_n = factor_service.get_factor_top_n(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit=0, descending=True)
    if zero_limit_top_n.row_count != 1 or [row.symbol for row in zero_limit_top_n.rows] != ["600000.XSHG"]:
        raise SystemExit("formal services smoke test failed: zero-limit top-n clamp mismatch")
    tie_desc_top_n = factor_service.get_factor_top_n(factor_id="tie_rank_factor", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit=2, descending=True)
    if [row.symbol for row in tie_desc_top_n.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal services smoke test failed: tie descending top-n symbol order mismatch")
    tie_asc_top_n = factor_service.get_factor_top_n(factor_id="tie_rank_factor", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit=2, descending=False)
    if [row.symbol for row in tie_asc_top_n.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal services smoke test failed: tie ascending top-n symbol order mismatch")
    unmatched_scope_top_n = factor_service.get_factor_top_n(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-02", end_date="2020-01-02", limit=5, descending=True)
    if unmatched_scope_top_n.row_count != 0 or unmatched_scope_top_n.rows:
        raise SystemExit("formal services smoke test failed: unmatched scope top-n should be empty")
    large_limit_top_n = factor_service.get_factor_top_n(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit=99, descending=True)
    if [row.symbol for row in large_limit_top_n.rows] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal services smoke test failed: large-limit top-n mismatch")
    negative_limit_top_n = factor_service.get_factor_top_n(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit=-3, descending=True)
    if negative_limit_top_n.row_count != 1 or [row.symbol for row in negative_limit_top_n.rows] != ["600000.XSHG"]:
        raise SystemExit("formal services smoke test failed: negative-limit top-n clamp mismatch")
    missing_top_n = factor_service.get_factor_top_n(factor_id="unknown_factor", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit=5, descending=True)
    if missing_top_n.row_count != 0 or missing_top_n.rows:
        raise SystemExit("formal services smoke test failed: unknown factor top-n should be empty")
    unknown_trade_date_top_n = factor_service.get_factor_top_n(factor_id="close_to_ma2_bias", trade_date="2020-01-03", start_date="2020-01-01", end_date="2020-01-02", limit=5, descending=True)
    if unknown_trade_date_top_n.row_count != 0 or unknown_trade_date_top_n.rows:
        raise SystemExit("formal services smoke test failed: unknown trade-date top-n should be empty")
    sync_price = market_service.sync_price_history(symbol="000001.XSHE", start_date="2020-01-01", end_date="2020-01-02")
    if sync_price.dataset != "price_history" or sync_price.row_count != 2:
        raise SystemExit("formal services smoke test failed: price sync summary mismatch")
    sync_calendar = market_service.sync_trading_calendar(start_date="2020-01-01", end_date="2020-01-03")
    if sync_calendar.dataset != "trading_calendar" or sync_calendar.row_count != 3:
        raise SystemExit("formal services smoke test failed: calendar sync summary mismatch")
    if market_service.get_sync_status(dataset="price_history").cache_status is None:
        raise SystemExit("formal services smoke test failed: sync status missing latest state")

    gateway = RqalphaRicequantGateway(RicequantConfig(username="demo", password="demo"), runtime=FakeRqalphaRuntime())
    backtest_service = PersistentBacktestService(BacktestService(RunSingleBacktest(gateway)), runtime_store)
    backtest_result = backtest_service.run_once(BacktestRunRequest(run_id="services-smoke-run-001", strategy_name="moving_average_strategy", symbol="000001.XSHE", benchmark="000300.XSHG", start_date="2020-01-01", end_date="2020-12-31"))
    if backtest_result.status.value != "completed":
        raise SystemExit("formal services smoke test failed: backtest service did not complete")
    batch_service = BatchResearchService(backtest_service, runtime_store)
    batch_result = batch_service.run_batch(BatchBacktestRunRequest(experiment_id="services-batch-001", profile="default_a_share", runs=[BacktestRunRequest(run_id="services-smoke-run-002", strategy_name="moving_average_strategy", symbol="000001.XSHE", benchmark="000300.XSHG", start_date="2020-01-01", end_date="2020-12-31")]))
    if batch_result.status != "completed":
        raise SystemExit("formal services smoke test failed: batch service did not complete")

    class _FailureBatchRunService:
        def run_once(self, request: BacktestRunRequest) -> BacktestResultSummary:
            if request.run_id == "services-smoke-run-fail-001":
                raise RuntimeError("simulated runtime failure")
            return BacktestResultSummary(
                run_id=request.run_id,
                strategy_name=request.strategy_name,
                status=backtest_result.status,
                start_date=request.start_date,
                end_date=request.end_date,
                benchmark=request.benchmark,
                metrics={},
            )

    failure_batch_service = BatchResearchService(_FailureBatchRunService(), runtime_store)
    failure_batch_result = failure_batch_service.run_batch(
        BatchBacktestRunRequest(
            experiment_id="services-batch-failure-001",
            profile="default_a_share",
            runs=[
                BacktestRunRequest(run_id="services-smoke-run-fail-001", strategy_name="moving_average_strategy", symbol="000001.XSHE", benchmark="000300.XSHG", start_date="2020-01-01", end_date="2020-12-31"),
                BacktestRunRequest(run_id="services-smoke-run-ok-001", strategy_name="moving_average_strategy", symbol="600000.XSHG", benchmark="000300.XSHG", start_date="2020-01-01", end_date="2020-12-31"),
            ],
        )
    )
    if failure_batch_result.status != "partial_failed":
        raise SystemExit("formal services smoke test failed: failure batch service status mismatch")
    if failure_batch_result.failures[0].get("failure_type") != "runtime_error":
        raise SystemExit("formal services smoke test failed: failure batch summary should classify runtime failures")
    if failure_batch_result.failures[0].get("failure_stage") != "run_once":
        raise SystemExit("formal services smoke test failed: failure batch summary should preserve failure_stage")
    if failure_batch_result.failures[0].get("failure_code") != "BACKTEST_RUN_ONCE_RUNTIME_ERROR":
        raise SystemExit("formal services smoke test failed: failure batch summary should preserve failure_code")
    if failure_batch_result.failures[0].get("failure_source") != "single_run_service":
        raise SystemExit("formal services smoke test failed: failure batch summary should preserve failure_source")
    reader = RunResultsReader(runtime_store)
    raw_detail = reader.get_run_detail("services-smoke-run-001")
    if raw_detail is None or not raw_detail.trades or not raw_detail.accounts or not raw_detail.yearly_returns:
        raise SystemExit("formal services smoke test failed: persisted runtime rows missing")
    reporting_service = ReportingService(reader, BatchComparisonService(runtime_store))
    if not reporting_service.get_run_detail("services-smoke-run-001").metrics:
        raise SystemExit("formal services smoke test failed: reporting detail missing")
    if not reporting_service.get_batch_summary("services-batch-001").rows:
        raise SystemExit("formal services smoke test failed: reporting summary missing")
    failure_summary = reporting_service.get_batch_summary("services-batch-failure-001")
    if not failure_summary.failures or failure_summary.failures[0].get("failure_type") != "runtime_error":
        raise SystemExit("formal services smoke test failed: reporting summary should preserve failure_type")
    if failure_summary.failures[0].get("failure_stage") != "run_once":
        raise SystemExit("formal services smoke test failed: reporting summary should preserve failure_stage")
    if failure_summary.failures[0].get("failure_code") != "BACKTEST_RUN_ONCE_RUNTIME_ERROR":
        raise SystemExit("formal services smoke test failed: reporting summary should preserve failure_code")
    if failure_summary.failures[0].get("failure_source") != "single_run_service":
        raise SystemExit("formal services smoke test failed: reporting summary should preserve failure_source")
    if failure_summary.failure_type_counts != {"runtime_error": 1}:
        raise SystemExit("formal services smoke test failed: reporting summary should count runtime failure types")
    if failure_summary.failure_stage_counts != {"run_once": 1}:
        raise SystemExit("formal services smoke test failed: reporting summary should count runtime failure stages")
    if failure_summary.failure_code_counts != {"BACKTEST_RUN_ONCE_RUNTIME_ERROR": 1}:
        raise SystemExit("formal services smoke test failed: reporting summary should count runtime failure codes")

    from domain.common.enums import BacktestRunStatus

    class _UnexpectedStatusBatchRunService:
        def run_once(self, request: BacktestRunRequest) -> BacktestResultSummary:
            return BacktestResultSummary(
                run_id=request.run_id,
                strategy_name=request.strategy_name,
                status=BacktestRunStatus.FAILED,
                start_date=request.start_date,
                end_date=request.end_date,
                benchmark=request.benchmark,
                metrics={},
            )

    unexpected_status_batch_service = BatchResearchService(_UnexpectedStatusBatchRunService(), runtime_store)
    unexpected_status_batch_result = unexpected_status_batch_service.run_batch(
        BatchBacktestRunRequest(
            experiment_id="services-batch-unexpected-status-001",
            profile="default_a_share",
            runs=[
                BacktestRunRequest(run_id="services-smoke-run-unexpected-001", strategy_name="moving_average_strategy", symbol="000001.XSHE", benchmark="000300.XSHG", start_date="2020-01-01", end_date="2020-12-31"),
            ],
        )
    )
    if unexpected_status_batch_result.status != "failed":
        raise SystemExit("formal services smoke test failed: unexpected-status batch service status mismatch")
    if unexpected_status_batch_result.failures[0].get("result_status") != "failed":
        raise SystemExit("formal services smoke test failed: unexpected-status batch summary should preserve result_status")
    unexpected_status_summary = reporting_service.get_batch_summary("services-batch-unexpected-status-001")
    if not unexpected_status_summary.failures or unexpected_status_summary.failures[0].get("result_status") != "failed":
        raise SystemExit("formal services smoke test failed: reporting summary should preserve unexpected result_status")
    if unexpected_status_batch_result.failures[0].get("expected_status") != "completed":
        raise SystemExit("formal services smoke test failed: unexpected-status batch summary should preserve expected_status")
    if unexpected_status_summary.failures[0].get("expected_status") != "completed":
        raise SystemExit("formal services smoke test failed: reporting summary should preserve unexpected expected_status")
    if unexpected_status_batch_result.failures[0].get("status_transition") != "completed->failed":
        raise SystemExit("formal services smoke test failed: unexpected-status batch summary should preserve status_transition")
    if unexpected_status_summary.failures[0].get("status_transition") != "completed->failed":
        raise SystemExit("formal services smoke test failed: reporting summary should preserve unexpected status_transition")
    if unexpected_status_summary.failure_type_counts != {"unexpected_status": 1}:
        raise SystemExit("formal services smoke test failed: reporting summary should count unexpected status failure types")
    if unexpected_status_summary.failure_stage_counts != {"result_status_check": 1}:
        raise SystemExit("formal services smoke test failed: reporting summary should count unexpected status failure stages")
    if unexpected_status_summary.failure_code_counts != {"BACKTEST_UNEXPECTED_RESULT_STATUS": 1}:
        raise SystemExit("formal services smoke test failed: reporting summary should count unexpected status failure codes")
    print("formal services smoke test passed")



def _seed_tie_rank_factor(factor_store: SqliteFactorStore) -> None:
    from factor_lab import FactorDefinition, FactorValue

    factor_store.save_factor_values(
        definition=FactorDefinition(factor_id="tie_rank_factor", name="Tie Rank Factor"),
        symbol="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-01-02",
        rows=[FactorValue(factor_id="tie_rank_factor", symbol="000001.XSHE", trade_date="2020-01-02", value=1.0)],
    )
    factor_store.save_factor_values(
        definition=FactorDefinition(factor_id="tie_rank_factor", name="Tie Rank Factor"),
        symbol="600000.XSHG",
        start_date="2020-01-01",
        end_date="2020-01-02",
        rows=[FactorValue(factor_id="tie_rank_factor", symbol="600000.XSHG", trade_date="2020-01-02", value=1.0)],
    )
class FakeMarketDataRepository:
    def fetch_price_history(self, symbol: str, start_date: str | None = None, end_date: str | None = None) -> Sequence[Mapping[str, Any]]:
        if symbol == "600000.XSHG":
            return [{"date": "2020-01-01", "open": 8.0, "high": 8.4, "low": 7.9, "close": 8.0, "volume": 2000.0}, {"date": "2020-01-02", "open": 8.0, "high": 8.8, "low": 8.0, "close": 8.8, "volume": 2500.0}]
        return [{"date": "2020-01-01", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1000.0}, {"date": "2020-01-02", "open": 10.2, "high": 10.8, "low": 10.1, "close": 10.7, "volume": 1200.0}]
    def fetch_index_components(self, index_code: str, date: str | None = None) -> Sequence[str]:
        if index_code != "000300.XSHG":
            return []
        if date == "2020-01-01":
            return ["000001.XSHE"]
        if date == "2020-01-03":
            return ["600000.XSHG"]
        return ["000001.XSHE", "600000.XSHG"]
    def fetch_financial_indicators(self, symbol: str, report_date: str | None = None) -> Sequence[Mapping[str, Any]]:
        return []
    def fetch_trading_calendar(self, start_date: str, end_date: str) -> Sequence[str]:
        return ["2020-01-01", "2020-01-02", "2020-01-03"]


class FakeRqalphaRuntime:
    def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"run_id": str(payload.get("run_id") or "smoke-run"), "strategy_name": str(payload.get("strategy_name") or "unknown_strategy"), "status": "completed", "start_date": str(payload.get("start_date") or "2020-01-01"), "end_date": str(payload.get("end_date") or "2020-12-31"), "benchmark": str(payload.get("benchmark") or "000300.XSHG"), "metrics": {"annualized_returns": 0.1234, "total_returns": 0.2345, "max_drawdown": -0.0567, "sharpe": 1.89}, "raw_result": {"engine": "formal-services-smoke", "logs": [{"recorded_at": "2020-01-03T09:35:00+08:00", "level": "INFO", "stage": "runtime", "message": "formal services smoke completed"}], "trades": [{"trade_time": "2020-02-03T10:00:00+08:00", "order_book_id": "000001.XSHE", "side": "BUY", "price": 10.2, "quantity": 100.0, "amount": 1020.0}], "positions": [{"snapshot_time": "2020-02-03T15:00:00+08:00", "order_book_id": "000001.XSHE", "quantity": 100.0, "market_value": 1020.0, "notes": {"source": "runtime"}}], "accounts": [{"snapshot_time": "2020-02-03T15:00:00+08:00", "total_value": 1001020.0, "market_value": 1020.0, "cash": 1000000.0, "unit_net_value": 1.00102, "notes": {"account_type": "portfolio"}}], "yearly_returns": [{"year": "2020", "portfolio_return": 0.2345, "benchmark_return": 0.1567, "excess_return": 0.0778}]}}


if __name__ == "__main__":
    main()
