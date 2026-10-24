"""Stage-89 machine-readable asset governance catalog."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class AssetDefinition:
    asset_id: str
    database_role: str
    lifecycle_layer: str
    owner: str
    authority: str = "authoritative"
    mutability: str = "append_or_upsert"
    retention_class: str = "business_record"
    secondary_layers: tuple[str, ...] = ()


SOURCE_FACT_TABLES = ("corporate_action_events",)
STANDARD_FACT_TABLES = (
    "index_component_intervals", "market_daily_prices",
    "market_index_daily_prices", "market_symbols", "market_trade_calendar",
    "price_adjustment_factors", "security_lifecycle_events",
    "security_trading_status_daily",
)
CONTROL_TABLES = (
    "data_asset_registry", "data_lineage_edges",
    "data_center_settings", "data_correction_overlays", "data_dataset_catalog",
    "data_quality_dispositions", "data_quality_issues", "data_quality_refetches",
    "data_quality_reports", "data_quality_scan_controls", "data_quality_scan_jobs",
    "data_route_snapshots", "data_source_capabilities", "data_source_definitions",
    "data_source_routes",
    "market_context_backfill_items", "market_context_backfill_jobs",
    "market_incremental_sync_items", "market_incremental_sync_jobs",
    "market_scheduler_settings", "market_schema_migrations", "market_sync_runs",
    "market_sync_state",
)


def _assets(database_id: str, role: str, layer: str, owner: str, tables: Iterable[str], **kwargs: str) -> list[AssetDefinition]:
    return [AssetDefinition(f"{database_id}.{table}", role, layer, owner, **kwargs) for table in tables]


ASSETS: tuple[AssetDefinition, ...] = tuple([
    *_assets("market", "source_event_fact", "F1", "data_platform", SOURCE_FACT_TABLES),
    *_assets("market", "standard_market_fact", "F2", "data_platform", STANDARD_FACT_TABLES),
    *_assets("market", "published_dataset", "F3", "data_platform", (
        "data_versions", "data_version_members",
    ), mutability="immutable_versioned", retention_class="published_dataset"),
    *_assets("market", "governance_control", "C1", "data_platform", CONTROL_TABLES),
    AssetDefinition("classification.classification_intervals", "standard_reference_fact", "F2", "data_platform"),
    AssetDefinition("classification.classification_sync_state", "sync_control", "C1", "data_platform"),
    *_assets("panorama", "standard_panorama_fact", "F2", "data_platform", (
        "panorama_board_catalog", "panorama_board_daily", "panorama_board_fund_flow",
    )),
    AssetDefinition("panorama.panorama_events", "source_event_fact", "F1", "data_platform"),
    *_assets("panorama", "sync_control", "C1", "data_platform", (
        "panorama_sync_items", "panorama_sync_job_ranges", "panorama_sync_jobs",
    )),
    *_assets("factor", "factor_research", "F4", "factor_lab", (
        "factor_definitions", "factor_research_observations", "factor_research_reports",
        "factor_research_snapshots", "factor_artifacts", "factor_artifact_values",
        "factor_optimization_reports",
    )),
    AssetDefinition("factor.factor_research_tasks", "research_task_control", "C1", "factor_lab"),
    AssetDefinition("factor.factor_optimization_tasks", "optimization_task_control", "C1", "factor_lab"),
    AssetDefinition("factor.factor_index_component_intervals", "compatibility", "X", "factor_lab", authority="deprecated_non_authoritative", retention_class="compatibility_until_migration"),
    *_assets("strategy", "strategy_asset", "F5", "strategy_library", (
        "strategy_definitions", "strategy_manifests", "strategy_versions",
    ), mutability="immutable_versioned"),
    AssetDefinition("strategy.strategy_migrations", "schema_control", "C1", "strategy_library"),
    AssetDefinition("single_task.single_backtest_tasks", "execution_task_control", "C1", "backtest", secondary_layers=("F6",)),
    AssetDefinition("screening.screening_items", "screening_result", "F6", "backtest", secondary_layers=("C1",)),
    AssetDefinition("screening.screening_tasks", "execution_task_control", "C1", "backtest"),
    AssetDefinition("portfolio.portfolio_tasks", "execution_task_control", "C1", "backtest", secondary_layers=("F6",)),
    AssetDefinition("backtest.backtest_input_snapshots", "frozen_execution_input", "F3", "backtest", mutability="immutable", retention_class="execution_evidence"),
    *_assets("backtest", "execution_result", "F6", "backtest", (
        "backtest_accounts", "backtest_metrics", "backtest_positions", "backtest_trades",
        "backtest_yearly_returns", "report_packages", "report_snapshots", "ai_workflow_runs",
    )),
    AssetDefinition("backtest.backtest_runs", "execution_result_root", "F6", "backtest", secondary_layers=("C1",)),
    AssetDefinition("backtest.backtest_logs", "execution_audit", "C1", "backtest"),
    AssetDefinition("backtest.research_runs", "research_run_control", "C1", "backtest"),
    AssetDefinition("backtest.market_sync_runs", "legacy_sync_audit", "C1", "data_platform", authority="legacy_control"),
    *_assets("backtest", "rebuildable_cache", "X", "data_platform", (
        "factor_result_cache", "local_data_assets", "market_data_cache",
        "market_price_bars", "trading_calendar_cache",
    ), authority="compatibility_cache", retention_class="rebuildable_cache"),
])


DATABASES: dict[str, Path] = {
    "market": Path("var/market/a_share_market.sqlite3"),
    "classification": Path("var/runtime/a_share_classification_history.sqlite3"),
    "factor": Path("var/runtime/factor_research.sqlite3"),
    "screening": Path("var/runtime/independent_screening.sqlite3"),
    "panorama": Path("var/runtime/market_panorama.sqlite3"),
    "portfolio": Path("var/runtime/shared_portfolio.sqlite3"),
    "single_task": Path("var/runtime/single_backtest_tasks.sqlite3"),
    "strategy": Path("var/runtime/strategy_library.sqlite3"),
    "backtest": Path("var/runtime/backtest_results.sqlite3"),
}


LINEAGE: tuple[dict[str, str], ...] = (
    {"upstream": "market.corporate_action_events", "downstream": "market.price_adjustment_factors", "relation": "derives_adjustment"},
    {"upstream": "market.price_adjustment_factors", "downstream": "market.market_daily_prices", "relation": "materializes_adjusted_prices"},
    {"upstream": "market.market_daily_prices", "downstream": "market.data_version_members", "relation": "published_member"},
    {"upstream": "market.data_quality_reports", "downstream": "market.data_versions", "relation": "quality_gate"},
    {"upstream": "market.data_versions", "downstream": "market.data_version_members", "relation": "contains"},
    {"upstream": "market.data_versions", "downstream": "factor.factor_research_tasks", "relation": "frozen_input"},
    {"upstream": "classification.classification_intervals", "downstream": "factor.factor_research_observations", "relation": "classification_context"},
    {"upstream": "factor.factor_research_tasks", "downstream": "factor.factor_research_observations", "relation": "produces"},
    {"upstream": "factor.factor_research_tasks", "downstream": "factor.factor_artifacts", "relation": "publishes"},
    {"upstream": "factor.factor_artifacts", "downstream": "factor.factor_artifact_values", "relation": "contains"},
    {"upstream": "factor.factor_artifacts", "downstream": "factor.factor_optimization_tasks", "relation": "frozen_optimization_input"},
    {"upstream": "factor.factor_optimization_tasks", "downstream": "factor.factor_optimization_reports", "relation": "produces"},
    {"upstream": "market.data_versions", "downstream": "backtest.backtest_input_snapshots", "relation": "frozen_input"},
    {"upstream": "factor.factor_artifacts", "downstream": "backtest.backtest_input_snapshots", "relation": "frozen_feature"},
    {"upstream": "backtest.backtest_input_snapshots", "downstream": "backtest.backtest_runs", "relation": "reproduces"},
    {"upstream": "backtest.backtest_runs", "downstream": "backtest.backtest_accounts", "relation": "produces"},
    {"upstream": "backtest.backtest_runs", "downstream": "backtest.backtest_positions", "relation": "produces"},
    {"upstream": "backtest.backtest_runs", "downstream": "backtest.backtest_trades", "relation": "produces"},
    {"upstream": "backtest.backtest_runs", "downstream": "backtest.backtest_metrics", "relation": "produces"},
    {"upstream": "backtest.backtest_runs", "downstream": "backtest.report_snapshots", "relation": "reported_by"},
    {"upstream": "backtest.report_snapshots", "downstream": "backtest.report_packages", "relation": "packages"},
    {"upstream": "market.market_daily_prices", "downstream": "backtest.market_price_bars", "relation": "legacy_cache_projection"},
    {"upstream": "market.market_trade_calendar", "downstream": "backtest.trading_calendar_cache", "relation": "legacy_cache_projection"},
    {"upstream": "market.index_component_intervals", "downstream": "factor.factor_research_tasks", "relation": "point_in_time_universe"},
)


def catalog_payload() -> dict[str, Any]:
    return {
        "model": "business_topic_plus_lifecycle",
        "lifecycle_layers": {
            "F1": "source_fact", "F2": "standard_fact", "F3": "published_or_frozen_dataset",
            "F4": "factor_asset", "F5": "strategy_asset", "F6": "execution_and_analysis_result",
            "C1": "control_and_governance", "X": "compatibility_or_cache",
        },
        "databases": {key: str(value) for key, value in DATABASES.items()},
        "assets": [asdict(item) for item in ASSETS],
        "lineage": [dict(item) for item in LINEAGE],
    }
