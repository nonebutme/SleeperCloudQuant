"""Smoke test for the new formal API shell."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


def _bootstrap() -> None:
    ensure_project_root_on_sys_path()


def main() -> None:
    _bootstrap()

    from app.main import AppServiceRegistry, SimpleApiApp, create_app
    from app.runtime.http_adapter import DispatchError
    from app.schemas.backtest import BatchBacktestRunItemPayload, BatchBacktestRunRequestPayload, BacktestRunRequestPayload, ParameterScanRequestPayload, StrategySaveRequestPayload
    from app.schemas.reporting import ReportPackageCreateRequestPayload, ReportPackageExportQueryPayload, ReportSnapshotSaveRequestPayload, ReportingAIWorkflowReplayQuery
    from app.schemas.factor import FactorCrossSectionSummaryQuery, FactorPoolMembersQuery, FactorSummaryQuery, FactorTopNQuery, FactorValuesQuery
    from app.schemas.market import MarketPriceHistoryQuery, MarketSyncPriceHistoryRequest, MarketSyncTradingCalendarRequest, MarketTradingCalendarQuery
    from app.services import BacktestService, BatchResearchService, FactorResearchService, IndependentScreeningService, MarketDataService, PersistentBacktestService, ReportingService, SharedPortfolioService, StrategyService
    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from backtest_kernel import RqalphaRicequantGateway, RunSingleBacktest
    from config_center.providers.ricequant_config import RicequantConfig
    from data_platform import CachedMarketDataRepository, SqliteMetadataStore
    from factor_lab import FactorDefinition, FactorValue, SqliteFactorStore
    from reporting import BatchComparisonService, RunResultsReader

    db = Path("tmp") / "formal_api_smoke.sqlite3"
    market = MarketDataService(CachedMarketDataRepository(FakeMarketDataRepository(), SqliteMetadataStore(db)))
    factor_store = SqliteFactorStore(db)
    factor = FactorResearchService(market, factor_store)
    factor.run_factor_for_symbols(factor_id="close_to_close_return_1d", symbols=["000001.XSHE", "600000.XSHG"], start_date="2020-01-01", end_date="2020-01-02")
    factor.run_factor_for_symbols(factor_id="close_to_ma2_bias", symbols=["000001.XSHE", "600000.XSHG"], start_date="2020-01-01", end_date="2020-01-02")
    _seed_tie_rank_factor(factor_store)
    runtime_store = SqliteRuntimeStore(db)
    backtest = PersistentBacktestService(BacktestService(RunSingleBacktest(RqalphaRicequantGateway(RicequantConfig(username="demo", password="demo"), runtime=FakeRqalphaRuntime()))), runtime_store)
    strategy_service = StrategyService(Path("tmp") / "formal_api_strategy_smoke.sqlite3")
    independent_screening_service = IndependentScreeningService(backtest, market, strategy_service, runtime_store, Path("tmp") / "formal_api_screening_smoke.sqlite3")
    shared_portfolio_service = SharedPortfolioService(market, strategy_service, runtime_store, Path("tmp") / "formal_api_portfolio_smoke.sqlite3")
    app = create_app(AppServiceRegistry(market_data_service=market, factor_research_service=factor, backtest_service=backtest, batch_research_service=BatchResearchService(backtest, runtime_store), reporting_service=ReportingService(RunResultsReader(runtime_store), BatchComparisonService(runtime_store), snapshot_store=runtime_store), strategy_service=strategy_service, independent_screening_service=independent_screening_service, shared_portfolio_service=shared_portfolio_service))
    if not isinstance(app, SimpleApiApp) or len(app.routes) < 15:
        raise SystemExit("formal API smoke test failed: app shell mismatch")

    routes = {route.name: route for route in app.routes}
    if "backtest_strategy_library" not in routes or len(routes["backtest_strategy_library"].handler().strategies) < 3:
        raise SystemExit("formal API smoke test failed: strategy library route mismatch")
    if "backtest_independent_screening_task_create" not in routes or "backtest_independent_screening_task_items" not in routes:
        raise SystemExit("formal API smoke test failed: independent screening routes missing")
    if "backtest_shared_portfolio_task_create" not in routes or "backtest_shared_portfolio_task_run" not in routes:
        raise SystemExit("formal API smoke test failed: shared portfolio routes missing")
    if len(routes["factor_definitions"].handler().definitions) != 2:
        raise SystemExit("formal API smoke test failed: factor definitions route mismatch")
    default_pool_members = routes["factor_pool_members"].handler(FactorPoolMembersQuery(index_code="000300.XSHG")).symbols
    if default_pool_members != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: default factor pool members route mismatch")
    pool_members = routes["factor_pool_members"].handler(FactorPoolMembersQuery(index_code="000300.XSHG", date="2020-01-02")).symbols
    if pool_members != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: factor pool members route mismatch")
    dated_pool_members = routes["factor_pool_members"].handler(FactorPoolMembersQuery(index_code="000300.XSHG", date="2020-01-01")).symbols
    if dated_pool_members != ["000001.XSHE"]:
        raise SystemExit("formal API smoke test failed: dated factor pool members route mismatch")
    later_pool_members = routes["factor_pool_members"].handler(FactorPoolMembersQuery(index_code="000300.XSHG", date="2020-01-03")).symbols
    if later_pool_members != ["600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: later factor pool members route mismatch")
    if routes["factor_pool_members"].handler(FactorPoolMembersQuery(index_code="UNKNOWN.XSHG")).symbols:
        raise SystemExit("formal API smoke test failed: unknown default factor pool members route should be empty")
    if routes["factor_pool_members"].handler(FactorPoolMembersQuery(index_code="UNKNOWN.XSHG", date="2020-01-02")).symbols:
        raise SystemExit("formal API smoke test failed: unknown factor pool members route should be empty")
    if len(routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02")).rows) != 2:
        raise SystemExit("formal API smoke test failed: factor summary route mismatch")
    filtered_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids="close_to_ma2_bias"))
    if len(filtered_summary.rows) != 1 or filtered_summary.rows[0].factor_id != "close_to_ma2_bias":
        raise SystemExit("formal API smoke test failed: filtered factor summary route mismatch")
    default_scope_missing_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-02", factor_ids="unknown_factor"))
    if default_scope_missing_summary.rows:
        raise SystemExit("formal API smoke test failed: default-scope unknown factor summary route should be empty")
    missing_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids="unknown_factor"))
    if missing_summary.rows:
        raise SystemExit("formal API smoke test failed: unknown factor summary route should be empty")
    unknown_symbol_unknown_factor_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="UNKNOWN.XSHG", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids="unknown_factor"))
    if unknown_symbol_unknown_factor_summary.rows:
        raise SystemExit("formal API smoke test failed: unknown symbol and unknown factor summary route should be empty")
    unknown_symbol_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="UNKNOWN.XSHG", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02"))
    if unknown_symbol_summary.rows:
        raise SystemExit("formal API smoke test failed: unknown symbol summary route should be empty")
    empty_trade_date_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-01", start_date="2020-01-01", end_date="2020-01-02"))
    if empty_trade_date_summary.rows:
        raise SystemExit("formal API smoke test failed: empty trade-date summary route should be empty")
    filtered_empty_trade_date_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-01", start_date="2020-01-01", end_date="2020-01-02", factor_ids="close_to_ma2_bias"))
    if filtered_empty_trade_date_summary.rows:
        raise SystemExit("formal API smoke test failed: filtered empty trade-date summary route should be empty")
    blank_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=""))
    if len(blank_summary.rows) != 2:
        raise SystemExit("formal API smoke test failed: blank factor_ids summary should fall back to all factors")
    comma_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=",,close_to_ma2_bias,,"))
    if len(comma_summary.rows) != 1 or comma_summary.rows[0].factor_id != "close_to_ma2_bias":
        raise SystemExit("formal API smoke test failed: comma factor_ids summary parse mismatch")
    default_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02"))
    if [item.symbol for item in default_cross_section.summaries] != ["000001.XSHE", "600000.XSHG"] or any(len(item.rows) != 2 for item in default_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: default factor cross-section summary route mismatch")
    base_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02"))
    if [item.symbol for item in base_cross_section.summaries] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: factor cross-section summary route mismatch")
    dated_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-01", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02"))
    if [item.symbol for item in dated_cross_section.summaries] != ["000001.XSHE"] or any(len(item.rows) != 2 for item in dated_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: dated factor cross-section summary route mismatch")
    later_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-03", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02"))
    if [item.symbol for item in later_cross_section.summaries] != ["600000.XSHG"] or any(len(item.rows) != 2 for item in later_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: later factor cross-section summary route mismatch")
    filtered_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids="close_to_close_return_1d"))
    if [item.symbol for item in filtered_cross_section.summaries] != ["000001.XSHE", "600000.XSHG"] or any(len(item.rows) != 1 or item.rows[0].factor_id != "close_to_close_return_1d" for item in filtered_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: filtered factor cross-section summary route mismatch")
    missing_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids="unknown_factor"))
    if [item.symbol for item in missing_cross_section.summaries] != ["000001.XSHE", "600000.XSHG"] or any(item.rows for item in missing_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: unknown factor cross-section summary route should be empty")
    later_unknown_factor_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-03", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids="unknown_factor"))
    if [item.symbol for item in later_unknown_factor_cross_section.summaries] != ["600000.XSHG"] or any(item.rows for item in later_unknown_factor_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: later unknown factor cross-section summary route should preserve symbols and return empty rows")
    blank_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=""))
    if [item.symbol for item in blank_cross_section.summaries] != ["000001.XSHE", "600000.XSHG"] or any(len(item.rows) != 2 for item in blank_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: blank factor_ids cross-section should fall back to all factors")
    comma_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", factor_ids=",,close_to_close_return_1d,,"))
    if [item.symbol for item in comma_cross_section.summaries] != ["000001.XSHE", "600000.XSHG"] or any(len(item.rows) != 1 or item.rows[0].factor_id != "close_to_close_return_1d" for item in comma_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: comma factor_ids cross-section parse mismatch")
    empty_trade_date_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-01", start_date="2020-01-01", end_date="2020-01-02"))
    if [item.symbol for item in empty_trade_date_cross_section.summaries] != ["000001.XSHE", "600000.XSHG"] or any(item.rows for item in empty_trade_date_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: empty trade-date cross-section summary route should preserve symbols and return empty rows")
    filtered_empty_trade_date_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", date="2020-01-02", trade_date="2020-01-01", start_date="2020-01-01", end_date="2020-01-02", factor_ids="close_to_close_return_1d"))
    if [item.symbol for item in filtered_empty_trade_date_cross_section.summaries] != ["000001.XSHE", "600000.XSHG"] or any(item.rows for item in filtered_empty_trade_date_cross_section.summaries):
        raise SystemExit("formal API smoke test failed: filtered empty trade-date cross-section summary route should preserve symbols and return empty rows")
    default_unknown_pool_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="UNKNOWN.XSHG", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02"))
    if default_unknown_pool_cross_section.summaries:
        raise SystemExit("formal API smoke test failed: unknown default pool cross-section summary route should be empty")
    unknown_pool_cross_section = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="UNKNOWN.XSHG", date="2020-01-02", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02"))
    if unknown_pool_cross_section.summaries:
        raise SystemExit("formal API smoke test failed: unknown pool cross-section summary route should be empty")
    default_scope_values = routes["factor_values"].handler(FactorValuesQuery(factor_id="close_to_close_return_1d", symbol="000001.XSHE"))
    if default_scope_values.rows:
        raise SystemExit("formal API smoke test failed: default-scope factor values route should be empty")
    default_scope_unknown_factor_values = routes["factor_values"].handler(FactorValuesQuery(factor_id="unknown_factor", symbol="000001.XSHE"))
    if default_scope_unknown_factor_values.rows:
        raise SystemExit("formal API smoke test failed: default-scope unknown factor values route should be empty")
    exact_scope_values = routes["factor_values"].handler(FactorValuesQuery(factor_id="close_to_close_return_1d", symbol="000001.XSHE", start_date="2020-01-01", end_date="2020-01-02"))
    if len(exact_scope_values.rows) != 1 or exact_scope_values.rows[0].trade_date != "2020-01-02":
        raise SystemExit("formal API smoke test failed: factor values route mismatch")
    unmatched_scope_values = routes["factor_values"].handler(FactorValuesQuery(factor_id="close_to_close_return_1d", symbol="000001.XSHE", start_date="2020-01-02", end_date="2020-01-02"))
    if unmatched_scope_values.rows:
        raise SystemExit("formal API smoke test failed: unmatched scope factor values route should be empty")
    if routes["factor_values"].handler(FactorValuesQuery(factor_id="unknown_factor", symbol="000001.XSHE", start_date="2020-01-01", end_date="2020-01-02")).rows:
        raise SystemExit("formal API smoke test failed: unknown factor values route should be empty")
    if routes["factor_values"].handler(FactorValuesQuery(factor_id="unknown_factor", symbol="UNKNOWN.XSHG", start_date="2020-01-01", end_date="2020-01-02")).rows:
        raise SystemExit("formal API smoke test failed: unknown symbol and unknown factor values route should be empty")
    if routes["factor_values"].handler(FactorValuesQuery(factor_id="close_to_close_return_1d", symbol="UNKNOWN.XSHG", start_date="2020-01-01", end_date="2020-01-02")).rows:
        raise SystemExit("formal API smoke test failed: unknown symbol factor values route should be empty")
    if routes["factor_values"].handler(FactorValuesQuery(factor_id="close_to_close_return_1d", symbol="UNKNOWN.XSHG")).rows:
        raise SystemExit("formal API smoke test failed: unknown symbol default-scope factor values route should be empty")
    default_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02"))
    if [row.symbol for row in default_top_n.ranking.rows] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal API smoke test failed: default top-n route mismatch")
    empty_parse_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="", descending=""))
    if [row.symbol for row in empty_parse_top_n.ranking.rows] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal API smoke test failed: empty-parse top-n route mismatch")
    try:
        routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="abc", descending="true"))
    except DispatchError as exc:
        if exc.status_code != 400 or exc.message != "limit must be an integer":
            raise SystemExit("formal API smoke test failed: non-numeric limit DispatchError mismatch") from exc
    else:
        raise SystemExit("formal API smoke test failed: non-numeric limit should raise DispatchError")
    false_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="2", descending="false"))
    if [row.symbol for row in false_top_n.ranking.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: false descending parse mismatch")
    zero_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="2", descending="0"))
    if [row.symbol for row in zero_top_n.ranking.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: zero descending parse mismatch")
    no_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="2", descending="no"))
    if [row.symbol for row in no_top_n.ranking.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: no descending parse mismatch")
    default_scope_summary = routes["factor_summary"].handler(FactorSummaryQuery(symbol="000001.XSHE", trade_date="2020-01-02"))
    if default_scope_summary.rows:
        raise SystemExit("formal API smoke test failed: default-scope summary route should be empty")
    default_scope_cross_section_summary = routes["factor_cross_section_summary"].handler(FactorCrossSectionSummaryQuery(index_code="000300.XSHG", trade_date="2020-01-02"))
    if [item.symbol for item in default_scope_cross_section_summary.summaries] != ["000001.XSHE", "600000.XSHG"] or any(item.rows for item in default_scope_cross_section_summary.summaries):
        raise SystemExit("formal API smoke test failed: default-scope cross-section summary route should preserve symbols and return empty rows")
    top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="1", descending="true"))
    if top_n.ranking.rows[0].symbol != "600000.XSHG":
        raise SystemExit("formal API smoke test failed: factor top-n route mismatch")
    descending_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="2", descending="true"))
    if [row.symbol for row in descending_top_n.ranking.rows] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal API smoke test failed: descending top-n route order mismatch")
    ascending_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="2", descending="false"))
    if [row.symbol for row in ascending_top_n.ranking.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: ascending top-n route order mismatch")
    zero_limit_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="0", descending="true"))
    if zero_limit_top_n.ranking.row_count != 1 or [row.symbol for row in zero_limit_top_n.ranking.rows] != ["600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: zero-limit top-n route clamp mismatch")
    tie_desc_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="tie_rank_factor", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="2", descending="true"))
    if [row.symbol for row in tie_desc_top_n.ranking.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: tie descending top-n route symbol order mismatch")
    tie_asc_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="tie_rank_factor", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="2", descending="false"))
    if [row.symbol for row in tie_asc_top_n.ranking.rows] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: tie ascending top-n route symbol order mismatch")
    unmatched_scope_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-02", end_date="2020-01-02", limit="5", descending="true"))
    if unmatched_scope_top_n.ranking.row_count != 0 or unmatched_scope_top_n.ranking.rows:
        raise SystemExit("formal API smoke test failed: unmatched scope top-n route should be empty")
    large_limit_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="99", descending="true"))
    if [row.symbol for row in large_limit_top_n.ranking.rows] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal API smoke test failed: large-limit top-n route mismatch")
    negative_limit_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="-3", descending="true"))
    if negative_limit_top_n.ranking.row_count != 1 or [row.symbol for row in negative_limit_top_n.ranking.rows] != ["600000.XSHG"]:
        raise SystemExit("formal API smoke test failed: negative-limit top-n route clamp mismatch")
    missing_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="unknown_factor", trade_date="2020-01-02", start_date="2020-01-01", end_date="2020-01-02", limit="5", descending="true"))
    if missing_top_n.ranking.row_count != 0 or missing_top_n.ranking.rows:
        raise SystemExit("formal API smoke test failed: unknown factor top-n route should be empty")
    unknown_trade_date_top_n = routes["factor_top_n"].handler(FactorTopNQuery(factor_id="close_to_ma2_bias", trade_date="2020-01-03", start_date="2020-01-01", end_date="2020-01-02", limit="5", descending="true"))
    if unknown_trade_date_top_n.ranking.row_count != 0 or unknown_trade_date_top_n.ranking.rows:
        raise SystemExit("formal API smoke test failed: unknown trade-date top-n route should be empty")
    if len(routes["market_price_history"].handler(MarketPriceHistoryQuery(symbol="000001.XSHE", start_date="2020-01-01", end_date="2020-01-02")).rows) != 2:
        raise SystemExit("formal API smoke test failed: market route mismatch")
    if len(routes["market_trading_calendar"].handler(MarketTradingCalendarQuery(start_date="2020-01-01", end_date="2020-01-03")).days) != 3:
        raise SystemExit("formal API smoke test failed: calendar route mismatch")
    if routes["market_sync_price_history"].handler(MarketSyncPriceHistoryRequest(symbol="000001.XSHE", start_date="2020-01-01", end_date="2020-01-02")).summary.row_count != 2:
        raise SystemExit("formal API smoke test failed: sync price route mismatch")
    if routes["market_sync_trading_calendar"].handler(MarketSyncTradingCalendarRequest(start_date="2020-01-01", end_date="2020-01-03")).summary.row_count != 3:
        raise SystemExit("formal API smoke test failed: sync calendar route mismatch")
    if routes["market_sync_status"].handler("price_history").status.cache_status is None:
        raise SystemExit("formal API smoke test failed: sync status route mismatch")
    if routes["backtest_run_once"].handler(BacktestRunRequestPayload(run_id="api-smoke-run-001", strategy_name="moving_average_strategy", symbol="000001.XSHE", benchmark="000300.XSHG", start_date="2020-01-01", end_date="2020-12-31", strategy_id="moving_average_strategy", strategy_version="v1")).result.status.value != "completed":
        raise SystemExit("formal API smoke test failed: backtest route mismatch")
    normalized_batch_payload = BatchBacktestRunRequestPayload(experiment_id="api-batch-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-002", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}])
    if not isinstance(normalized_batch_payload.runs[0], BatchBacktestRunItemPayload):
        raise SystemExit("formal API smoke test failed: batch payload should normalize nested run items")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-empty-001", profile="default_a_share", runs=[])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: empty batch payload should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-duplicate-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-duplicate", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}, {"run_id": "api-smoke-run-duplicate", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: duplicate batch run_id should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-benchmark-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-benchmark-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}, {"run_id": "api-smoke-run-benchmark-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000905.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: inconsistent batch benchmark should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-strategy-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-strategy-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}, {"run_id": "api-smoke-run-strategy-002", "strategy_name": "mean_reversion_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: inconsistent batch strategy_name should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-frequency-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-frequency-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "frequency": "1d"}, {"run_id": "api-smoke-run-frequency-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "frequency": "1m"}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: inconsistent batch frequency should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-initial-cash-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-initial-cash-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000}, {"run_id": "api-smoke-run-initial-cash-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 2000000}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: inconsistent batch initial_cash should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-start-date-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-start-date-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000}, {"run_id": "api-smoke-run-start-date-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-02-01", "end_date": "2020-12-31", "initial_cash": 1000000}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: inconsistent batch start_date should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-end-date-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-end-date-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000}, {"run_id": "api-smoke-run-end-date-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2021-12-31", "initial_cash": 1000000}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: inconsistent batch end_date should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-parameters-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-parameters-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000, "parameters": {"window": 5}}, {"run_id": "api-smoke-run-parameters-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000, "parameters": {"window": 10}}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: inconsistent batch parameters should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-extra-config-001", profile="default_a_share", runs=[{"run_id": "api-smoke-run-extra-config-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000, "parameters": {"window": 5}, "extra_config": {"slippage": 0.001}}, {"run_id": "api-smoke-run-extra-config-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000, "parameters": {"window": 5}, "extra_config": {"slippage": 0.002}}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: inconsistent batch extra_config should raise ValueError")
    try:
        BatchBacktestRunRequestPayload(experiment_id="api-batch-invalid-001", profile="default_a_share", runs=[{}])
    except ValueError:
        pass
    else:
        raise SystemExit("formal API smoke test failed: invalid batch payload item should raise ValueError")
    batch_summary = routes["backtest_run_batch"].handler(normalized_batch_payload).summary
    if batch_summary.status != "completed":
        raise SystemExit("formal API smoke test failed: batch route mismatch")
    if batch_summary.successful_run_ids != ["api-smoke-run-002"]:
        raise SystemExit("formal API smoke test failed: batch summary successful_run_ids mismatch")
    reporting_detail = routes["reporting_run_detail"].handler("api-smoke-run-001").detail
    if not reporting_detail.metrics:
        raise SystemExit("formal API smoke test failed: reporting detail route mismatch")
    if reporting_detail.strategy_id != "moving_average_strategy" or reporting_detail.extra_config.get("strategy_version") != "v1":
        raise SystemExit("formal API smoke test failed: reporting strategy binding mismatch")
    runtime_store.save_ai_workflow_run(
        workflow_id="api-ai-workflow-report-link-001",
        symbol="000001.XSHE",
        analysis_date="2020-01-02",
        report_id="api-smoke-run-001",
        status="completed",
        generated_at="2020-01-02T15:10:00+08:00",
        provider_mode="local-demo-tradingagents-style",
        payload={
            "workflow_id": "api-ai-workflow-report-link-001",
            "symbol": "000001.XSHE",
            "analysis_date": "2020-01-02",
            "status": "completed",
            "generated_at": "2020-01-02T15:10:00+08:00",
            "provider_mode": "local-demo-tradingagents-style",
            "enabled_analysts": ["market", "news"],
            "enabled_researchers": ["bear"],
            "risk_team": ["neutral"],
            "max_debate_rounds": 2,
            "decision_policy": "watchlist_only_until_real_data",
            "timeline": [{"stage": "portfolio_manager", "status": "completed", "artifact": "portfolio_decision", "summary": "demo"}],
            "agent_messages": [{"agent": "Market Analyst", "content": "demo", "status": "completed"}],
            "debate_rounds": [],
            "risk_votes": [{"agent": "Neutral Risk Analyst", "vote": "watchlist_only", "content": "demo risk"}],
            "portfolio_decision": {"action": "watchlist_only", "rationale": "demo rationale"},
        },
    )
    replay = routes["reporting_ai_workflow_replay"].handler(ReportingAIWorkflowReplayQuery(symbol="000001.XSHE"), "api-smoke-run-001").replay
    if not replay.get("linked") or replay.get("workflow_id") != "api-ai-workflow-report-link-001" or replay.get("portfolio_decision", {}).get("action") != "watchlist_only":
        raise SystemExit("formal API smoke test failed: reporting AI workflow replay mismatch")
    package_response = routes["reporting_report_package_create"].handler(ReportPackageCreateRequestPayload(symbol="000001.XSHE", title="API smoke research package"), "api-smoke-run-001")
    package = package_response.package
    if package.get("run_id") != "api-smoke-run-001" or package.get("workflow_id") != "api-ai-workflow-report-link-001" or not package.get("snapshot_id"):
        raise SystemExit("formal API smoke test failed: report package create mismatch")
    if package.get("binding_mode") != "report_id_exact":
        raise SystemExit("formal API smoke test failed: report package should prefer exact report_id binding")
    packages = routes["reporting_report_package_list"].handler("api-smoke-run-001").packages
    if not packages or packages[0].get("package_id") != package.get("package_id"):
        raise SystemExit("formal API smoke test failed: report package list mismatch")
    package_detail = routes["reporting_report_package_detail"].handler(package.get("package_id")).package
    if package_detail.get("ai_workflow_replay", {}).get("workflow_id") != "api-ai-workflow-report-link-001":
        raise SystemExit("formal API smoke test failed: report package detail mismatch")
    html_export = routes["reporting_report_package_export"].handler(ReportPackageExportQueryPayload(format="html"), package.get("package_id")).export
    if html_export.get("format") != "html" or "<!doctype html>" not in html_export.get("content", "") or "API smoke research package" not in html_export.get("content", ""):
        raise SystemExit("formal API smoke test failed: report package HTML export mismatch")
    json_export = routes["reporting_report_package_export"].handler(ReportPackageExportQueryPayload(format="json"), package.get("package_id")).export
    if json_export.get("format") != "json" or "api-ai-workflow-report-link-001" not in json_export.get("content", ""):
        raise SystemExit("formal API smoke test failed: report package JSON export mismatch")
    scan = routes["backtest_parameter_scan"].handler(ParameterScanRequestPayload(run_id_prefix="api-scan", strategy_name="moving_average_strategy", strategy_id="moving_average_strategy", strategy_version="v1", symbol="000001.XSHE", benchmark="000300.XSHG", start_date="2020-01-01", end_date="2020-12-31", base_parameters={"short_window": 5}, parameter_grid={"long_window": [20, 30]}, max_runs=2))
    if len(scan.results) != 2 or scan.combinations[1].get("long_window") != 30:
        raise SystemExit("formal API smoke test failed: parameter scan route mismatch")
    comparison = routes["reporting_parameter_scan_comparison"].handler("api-scan").report
    if comparison.best_run_id is None or len(comparison.rows) != 2 or comparison.rows[0].rank != 1:
        raise SystemExit("formal API smoke test failed: parameter scan comparison route mismatch")
    comparison_snapshot = routes["reporting_parameter_scan_comparison_snapshot_save"].handler(ReportSnapshotSaveRequestPayload(report_type="parameter_scan_comparison", report_version="parameter-scan-v1"), "api-scan")
    if comparison_snapshot is None or comparison_snapshot.snapshot.payload.get("best_run_id") != comparison.best_run_id:
        raise SystemExit("formal API smoke test failed: parameter scan comparison snapshot save mismatch")
    comparison_snapshot_rows = routes["reporting_snapshot_list"].handler("api-scan").snapshots
    if not any(row.report_type == "parameter_scan_comparison" for row in comparison_snapshot_rows):
        raise SystemExit("formal API smoke test failed: parameter scan comparison snapshot list mismatch")
    comparison_snapshot_detail = routes["reporting_snapshot_detail"].handler(comparison_snapshot.snapshot.snapshot_id).snapshot
    if len(comparison_snapshot_detail.payload.get("rows", [])) != 2:
        raise SystemExit("formal API smoke test failed: parameter scan comparison snapshot detail mismatch")
    evaluation = routes["reporting_strategy_evaluation"].handler("api-smoke-run-001").report
    if evaluation.average_score <= 0 or len(evaluation.dimensions) != 7:
        raise SystemExit("formal API smoke test failed: strategy evaluation route mismatch")
    if evaluation.dimensions[0].chart.kind != "bar" or not evaluation.conclusions:
        raise SystemExit("formal API smoke test failed: strategy evaluation payload mismatch")
    snapshot_response = routes["reporting_strategy_evaluation_snapshot_save"].handler(ReportSnapshotSaveRequestPayload(), "api-smoke-run-001")
    if snapshot_response is None or snapshot_response.snapshot.payload.get("average_score") != evaluation.average_score:
        raise SystemExit("formal API smoke test failed: strategy evaluation snapshot save mismatch")
    snapshot_rows = routes["reporting_snapshot_list"].handler("api-smoke-run-001").snapshots
    if not snapshot_rows or snapshot_rows[0].snapshot_id != snapshot_response.snapshot.snapshot_id:
        raise SystemExit("formal API smoke test failed: strategy evaluation snapshot list mismatch")
    snapshot_detail = routes["reporting_snapshot_detail"].handler(snapshot_response.snapshot.snapshot_id).snapshot
    if snapshot_detail.payload.get("run_id") != "api-smoke-run-001" or len(snapshot_detail.payload.get("dimensions", [])) != 7:
        raise SystemExit("formal API smoke test failed: strategy evaluation snapshot detail mismatch")
    if routes["reporting_run_detail"].handler("api-missing-run-001") is not None:
        raise SystemExit("formal API smoke test failed: missing reporting detail should return None")
    if routes["reporting_strategy_evaluation"].handler("api-missing-run-001") is not None:
        raise SystemExit("formal API smoke test failed: missing strategy evaluation should return None")
    if not routes["reporting_batch_summary"].handler("api-batch-001").summary.rows:
        raise SystemExit("formal API smoke test failed: reporting summary route mismatch")
    if routes["reporting_batch_summary"].handler("api-missing-batch-001") is not None:
        raise SystemExit("formal API smoke test failed: missing reporting batch summary should return None")
    runtime_store.upsert_research_run(
        run_id="api-batch-failure-001",
        strategy_name="default_a_share",
        status="partial_failed",
        started_at="2020-01-01T09:30:00+08:00",
        finished_at="2020-01-01T09:35:00+08:00",
        parameters={
            "profile": "default_a_share",
            "request_count": 2,
            "success_count": 0,
            "failure_count": 2,
            "run_ids": [],
            "failures": [
                {"run_id": "api-failed-run-001", "failure_type": "runtime_error", "failure_stage": "run_once", "failure_code": "BACKTEST_RUN_ONCE_RUNTIME_ERROR"},
                {"run_id": "api-failed-run-002", "failure_type": "unexpected_status", "failure_stage": "result_status_check", "failure_code": "BACKTEST_UNEXPECTED_RESULT_STATUS"},
            ],
        },
    )
    failure_summary = routes["reporting_batch_summary"].handler("api-batch-failure-001").summary
    if failure_summary.failure_type_counts != {"runtime_error": 1, "unexpected_status": 1}:
        raise SystemExit("formal API smoke test failed: reporting batch summary should expose failure_type_counts")
    if failure_summary.failure_stage_counts != {"result_status_check": 1, "run_once": 1}:
        raise SystemExit("formal API smoke test failed: reporting batch summary should expose failure_stage_counts")
    if failure_summary.failure_code_counts != {"BACKTEST_RUN_ONCE_RUNTIME_ERROR": 1, "BACKTEST_UNEXPECTED_RESULT_STATUS": 1}:
        raise SystemExit("formal API smoke test failed: reporting batch summary should expose failure_code_counts")
    print("formal API smoke test passed")



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
        return {"run_id": str(payload.get("run_id") or "api-smoke-run"), "strategy_name": str(payload.get("strategy_name") or "unknown_strategy"), "status": "completed", "start_date": str(payload.get("start_date") or "2020-01-01"), "end_date": str(payload.get("end_date") or "2020-12-31"), "benchmark": str(payload.get("benchmark") or "000300.XSHG"), "metrics": {"annualized_returns": 0.1234, "total_returns": 0.2345, "max_drawdown": -0.0567, "sharpe": 1.89}, "raw_result": {"engine": "formal-api-smoke", "logs": [{"recorded_at": "2020-01-03T09:35:00+08:00", "level": "INFO", "stage": "runtime", "message": "formal API smoke completed"}], "trades": [{"trade_time": "2020-02-03T10:00:00+08:00", "order_book_id": "000001.XSHE", "side": "BUY", "price": 10.2, "quantity": 100.0, "amount": 1020.0}], "positions": [{"snapshot_time": "2020-02-03T15:00:00+08:00", "order_book_id": "000001.XSHE", "quantity": 100.0, "market_value": 1020.0, "notes": {"source": "runtime"}}], "accounts": [{"snapshot_time": "2020-02-03T15:00:00+08:00", "total_value": 1001020.0, "market_value": 1020.0, "cash": 1000000.0, "unit_net_value": 1.00102, "notes": {"account_type": "portfolio"}}], "yearly_returns": [{"year": "2020", "portfolio_return": 0.2345, "benchmark_return": 0.1567, "excess_return": 0.0778}]}}


if __name__ == "__main__":
    main()













