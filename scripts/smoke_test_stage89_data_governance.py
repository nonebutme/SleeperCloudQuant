"""Focused verification for stage-89 data governance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sqlite3
import tempfile
from pathlib import Path

from app.runtime.database_paths import backtest_runtime_database_path
from data_platform.asset_governance import ASSETS, DATABASES, catalog_payload
from data_platform.storage.asset_governance_store import AssetGovernanceStore


def main() -> None:
    payload = catalog_payload()
    assert payload["model"] == "business_topic_plus_lifecycle"
    assert len(ASSETS) == 79
    assert backtest_runtime_database_path() == Path("var/runtime/backtest_results.sqlite3")
    assert any(item.asset_id == "factor.factor_index_component_intervals" and item.authority == "deprecated_non_authoritative" for item in ASSETS)
    assert DATABASES["backtest"] == Path("var/runtime/backtest_results.sqlite3")
    by_id = {item.asset_id: item for item in ASSETS}
    assert by_id["market.market_daily_prices"].lifecycle_layer == "F2"
    assert by_id["market.data_versions"].lifecycle_layer == "F3"
    assert by_id["backtest.backtest_input_snapshots"].lifecycle_layer == "F3"
    assert by_id["factor.factor_research_tasks"].lifecycle_layer == "C1"
    assert by_id["factor.factor_optimization_tasks"].lifecycle_layer == "C1"
    assert by_id["factor.factor_optimization_reports"].lifecycle_layer == "F4"
    assert by_id["backtest.market_sync_runs"].lifecycle_layer == "C1"
    assert by_id["backtest.backtest_runs"].secondary_layers == ("C1",)

    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "governance.sqlite3"
        sqlite3.connect(database).close()
        store = AssetGovernanceStore(database)
        store.ensure_schema()
        assets = store.list_assets()
        assert len(assets) == 79
        assert len(store.list_lineage()) == 24
        run_asset = next(item for item in assets if item["asset_id"] == "backtest.backtest_runs")
        assert run_asset["secondary_layers"] == ["C1"]

    print("[stage89] data governance smoke passed")


if __name__ == "__main__":
    main()
