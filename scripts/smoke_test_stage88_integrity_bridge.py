"""Stage-88 governance, factor-artifact and credibility smoke tests."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest_advanced_analysis import build_advanced_analysis
from app.services.data_center_service import DataCenterService
from app.services.strategy_dataset_resolver import StrategyDatasetResolver
from data_platform.research_data_version import ResearchDataVersionResolver
from data_platform.storage.data_center_store import DataCenterStore
from factor_lab.research_core import canonical_hash
from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore


class _IndexReader:
    pass


def _seed_version(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE data_versions (
                data_version_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                as_of_trade_date TEXT NOT NULL, quality_report_id TEXT NOT NULL,
                manifest_hash TEXT NOT NULL, published_at TEXT
            );
            CREATE TABLE data_version_members (
                data_version_id TEXT NOT NULL, dataset TEXT NOT NULL,
                adjustment TEXT, symbol_scope TEXT, row_count INTEGER,
                symbol_count INTEGER, min_date TEXT, max_date TEXT,
                source TEXT, sync_run_ref TEXT, content_hash TEXT,
                quality_status TEXT, details_json TEXT
            );
            CREATE TABLE data_quality_reports (
                quality_report_id TEXT PRIMARY KEY, status TEXT NOT NULL
            );
            CREATE TABLE data_center_settings (
                setting_key TEXT PRIMARY KEY, setting_value TEXT, updated_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO data_versions VALUES (?,?,?,?,?,?)",
            ("dv-stage88", "published", "2026-08-10", "qr-stage88", "manifest", "2026-08-11"),
        )
        connection.execute(
            "INSERT INTO data_version_members VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "dv-stage88", "market_daily_prices", "hfq", "all", 3, 1,
                "2026-08-06", "2026-08-10", "test", "sync", "prices", "passed", "{}",
            ),
        )
        connection.execute("INSERT INTO data_quality_reports VALUES (?,?)", ("qr-stage88", "passed"))
        connection.execute(
            "INSERT INTO data_center_settings VALUES (?,?,?)",
            ("default_data_version_id", "dv-stage88", "2026-08-11"),
        )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-stage88-", ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        market_database = root / "market.sqlite3"

        guarded_service = DataCenterService.__new__(DataCenterService)
        try:
            guarded_service.sync_index_component_snapshots(["000300.XSHG"])
        except ValueError as exc:
            assert "explicit data-use authorization" in str(exc)
        else:
            raise AssertionError("index snapshot sync must require explicit authorization")
        _seed_version(market_database)

        version = ResearchDataVersionResolver(market_database).resolve(
            required_members=(("market_daily_prices", "hfq"),)
        )
        assert version["status"] == "ready"
        assert version["data_version_id"] == "dv-stage88"
        assert version["selection_policy"] == "global_default_version"

        index_store = DataCenterStore(market_database)
        index_store.ensure_schema()
        first = index_store.replace_index_component_snapshot(
            index_code="000300.XSHG", as_of_date="2026-08-01",
            rows=[{"symbol": "000001"}, {"symbol": "600000"}],
            source="controlled-test", source_version="snapshot-1",
            observed_at="2026-08-01T08:00:00+00:00",
        )
        assert first["symbols"] == ["000001", "600000"]
        second = index_store.replace_index_component_snapshot(
            index_code="000300.XSHG", as_of_date="2026-08-10",
            rows=[{"symbol": "000001"}, {"symbol": "300333"}],
            source="controlled-test", source_version="snapshot-2",
            observed_at="2026-08-10T08:00:00+00:00",
        )
        assert second["symbols"] == ["000001", "300333"]
        assert index_store.resolve_index_components("000300.XSHG", "2026-08-09")["symbols"] == [
            "000001", "600000"
        ]

        factor_store = SqliteFactorResearchStore(root / "factor.sqlite3", index_store=index_store)
        config = {
            "factor_id": "stage88_factor", "factor_version": "v1",
            "factor_adjustment": "hfq",
        }
        context = {"effective_range": {"start_date": "2026-08-06", "end_date": "2026-08-10"}}
        pool = {"symbols": ["300333"], "source": "test"}
        task = factor_store.create_task(
            task_id="stage88-task", config=config, context=context,
            context_hash=canonical_hash(context), preflight={"status": "ready"},
            data_version_id="dv-stage88", quality_report_id="qr-stage88",
            pool_snapshot=pool,
        )
        assert task["status"] == "ready"
        factor_store.replace_observations(
            "stage88-task",
            [
                {"trade_date": "2026-08-06", "symbol": "300333", "raw_value": 1.0,
                 "processed_value": 1.0, "aligned_value": 1.0},
                {"trade_date": "2026-08-07", "symbol": "300333", "raw_value": 2.0,
                 "processed_value": 2.0, "aligned_value": 2.0},
                {"trade_date": "2026-08-10", "symbol": "300333", "raw_value": 3.0,
                 "processed_value": 3.0, "aligned_value": 3.0},
            ],
        )
        artifact = factor_store.publish_artifact("stage88-task")
        assert artifact["artifact_id"].startswith("factor-artifact-")
        assert factor_store.publish_artifact("stage88-task")["artifact_id"] == artifact["artifact_id"]

        resolver = StrategyDatasetResolver(_IndexReader(), factor_store=factor_store)
        source = (
            'DATASET_REQUIREMENTS=["factor_values"]\n'
            'FACTOR_REQUIREMENTS=["stage88_factor"]\n'
            'def generate_target_weights(bars, parameters):\n    return []\n'
        )
        frozen = resolver.freeze_parameters(
            source,
            {"factor_artifacts": {"stage88_factor": artifact["artifact_id"]}},
        )
        assert frozen["factor_artifacts"]["stage88_factor"] == artifact["artifact_id"]
        result = resolver.resolve(
            source,
            [
                {"symbol": "300333", "trade_date": "2026-08-06", "close": 1.0},
                {"symbol": "300333", "trade_date": "2026-08-07", "close": 1.0},
                {"symbol": "300333", "trade_date": "2026-08-10", "close": 1.0},
            ],
            frozen,
        )
        assert result["evidence"][-1]["artifact_id"] == artifact["artifact_id"]
        assert result["bars"][-1]["datasets"]["factor_values"]["stage88_factor"]["value"] == 3.0

        analysis = build_advanced_analysis(
            account_rows=[], benchmark_curve=[], excess_curve=[], trades=[], metrics={},
            raw_result={}, extra_config={"data_version_binding": version},
        )
        governance = analysis["report_governance"]
        assert governance["credibility_label"] == "historical_simulation_only"
        assert governance["paper_or_live_validation"] == "not performed"

    index_html = Path("web/index.html").read_text(encoding="utf-8")
    factor_js = Path("web/factor_research.js").read_text(encoding="utf-8")
    app_js = Path("web/app.js").read_text(encoding="utf-8")
    assert 'id="factor-report-credibility"' in index_html
    assert 'id="mode-report-credibility"' in index_html
    assert "factor_artifact_id" in factor_js or "artifact.artifact_id" in factor_js
    assert "paper_or_live_validation" in app_js
    print("stage88 integrity bridge smoke test passed")


if __name__ == "__main__":
    main()
