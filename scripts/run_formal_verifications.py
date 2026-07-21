"""Unified direct-execution entry for local formal verification scripts."""

from __future__ import annotations

import runpy
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def _run_script(script_name: str) -> None:
    script_path = Path(__file__).resolve().parent / script_name
    runpy.run_path(str(script_path), run_name="__main__")


def main() -> None:
    ensure_project_root_on_sys_path()
    scripts = [
        "verify_formal_fake_runtime.py",
        "verify_formal_reporting.py",
        "verify_formal_sqlite_cache.py",
        "smoke_test_legacy_sqlite_market_data.py",
        "smoke_test_a_share_source_database.py",
        "smoke_test_a_share_canonical_store.py",
        "smoke_test_a_share_full_market_quality.py",
        "smoke_test_local_sqlite_backtest_runtime.py",
        "smoke_test_versioned_custom_strategies.py",
        "smoke_test_strategy_library_crud.py",
        "smoke_test_independent_screening_backtest.py",
        "smoke_test_shared_portfolio_backtest.py",
        "smoke_test_backtest_mode_reports.py",
        "smoke_test_backtest_mode_task_directory.py",
        "smoke_test_full_market_backtest_scheduler.py",
        "smoke_test_classification_batch_sync.py",
        "smoke_test_factor_lab.py",
        "smoke_test_formal_services.py",
        "smoke_test_formal_api.py",
        "smoke_test_formal_http_adapter.py",
        "smoke_test_ai_config_api.py",
        "smoke_test_report_package_manifest.py",
        "smoke_test_report_package_exports.py",
        "smoke_test_report_package_layout.py",
        "smoke_test_real_provider_entry.py",
        "smoke_test_rqalpha_local_settings.py",
        "smoke_test_external_market_provider_e2e.py",
        "smoke_test_external_market_observability.py",
        "smoke_test_market_endpoint_mapping.py",
        "smoke_test_market_provider_preflight.py",
        "smoke_test_market_provider_sync_tasks.py",
        "smoke_test_local_market_bar_storage.py",
        "smoke_test_market_data_quality.py",
        "smoke_test_market_data_browser.py",
        "smoke_test_strategy_research_tasks.py",
        "smoke_test_research_task_backtest_run.py",
        "smoke_test_backtest_result_panel.py",
        "smoke_test_backtest_portfolio_panel.py",
        "smoke_test_backtest_trade_risk_attribution.py",
        "smoke_test_backtest_result_pagination_exports.py",
        "smoke_test_backtest_experiment_index.py",
        "smoke_test_experiment_review_package.py",
        "smoke_test_experiment_filter_compare.py",
        "smoke_test_strategy_evaluation_diagnostics.py",
        "smoke_test_parameter_matrix_tasks.py",
        "smoke_test_market_data_assets.py",
        "smoke_test_backtest_data_asset_trace.py",
        "smoke_test_backtest_input_snapshot_directory.py",
        "smoke_test_asset_consistency_panels.py",
        "smoke_test_data_asset_directory_filters_migration.py",
        "smoke_test_report_analysis_summary.py",
        "smoke_test_report_visual_contract.py",
        "smoke_test_experiment_report_comparison.py",
        "smoke_test_experiment_report_comparison_charts.py",
        "smoke_test_experiment_report_comparison_package.py",
        "smoke_test_report_package_directory.py",
        "smoke_test_report_package_lifecycle.py",
        "smoke_test_report_package_export_manifest.py",
        "smoke_test_backtest_workspace_ui.py",
        "smoke_test_backtest_task_workflow_ui.py",
    "smoke_test_backtest_task_usability.py",
    ]
    for script_name in scripts:
        print(f"[formal] running {script_name}")
        _run_script(script_name)
    print("[formal] all verifications passed")


if __name__ == "__main__":
    main()





























