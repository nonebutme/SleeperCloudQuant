"""FA-OPT 0-3 immutable-artifact optimization smoke test."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.factor_research import build_factor_research_routes
from app.services.factor_analysis_service import FactorAnalysisService
from factor_lab.research_core import canonical_hash
from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-fa-opt-", ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        factor_store = SqliteFactorResearchStore(root / "factor.sqlite3")
        source_config = {
            "factor_id": "fa_opt_smoke_factor",
            "factor_version": "v1",
            "factor_adjustment": "raw",
            "forward_horizons": [5],
        }
        source_context = {
            "effective_range": {
                "start_date": "2026-08-03",
                "end_date": "2026-08-07",
            }
        }
        factor_store.create_task(
            task_id="fa-opt-source",
            config=source_config,
            context=source_context,
            context_hash=canonical_hash(source_context),
            preflight={"status": "ready"},
            data_version_id="dv-fa-opt",
            quality_report_id="qr-fa-opt",
            pool_snapshot={"symbols": [f"00000{item}" for item in range(1, 7)]},
        )
        observations = []
        for day_index, trade_date in enumerate(
            ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
        ):
            for symbol_index in range(1, 7):
                aligned = float(symbol_index + day_index / 10)
                observations.append(
                    {
                        "trade_date": trade_date,
                        "symbol": f"00000{symbol_index}",
                        "raw_value": aligned,
                        "processed_value": aligned,
                        "aligned_value": aligned,
                        "forward_returns": {"5": (symbol_index - 3.5) / 100},
                    }
                )
        factor_store.replace_observations("fa-opt-source", observations)
        artifact = factor_store.publish_artifact("fa-opt-source")
        factor_store.review_artifact(
            artifact["artifact_id"],
            decision="approved",
            policy_id="fa-opt-smoke-fixture",
            reviewer="fa-opt-smoke",
            note="fixture-only registration for optimization plumbing",
        )
        factor_store.register_artifact(artifact["artifact_id"])
        artifact = factor_store.get_artifact(artifact["artifact_id"])

        service = FactorAnalysisService(
            market_database_path=root / "unused-market.sqlite3",
            research_store=factor_store,
        )
        route_contracts = {
            (route.method, route.path)
            for route in build_factor_research_routes(service)
        }
        assert (
            "POST",
            "/api/factor-research/optimization/tasks/{task_id}/start",
        ) in route_contracts
        assert (
            "GET",
            "/api/factor-research/optimization/reports/{report_id}",
        ) in route_contracts
        preflight = service.preflight_optimization(
            {
                "artifact_id": artifact["artifact_id"],
                "group_counts": [3],
                "one_side_rates": [0.0, 0.001],
            }
        )
        assert preflight["status"] == "ready"
        assert preflight["config"]["value_field"] == "aligned_value"
        assert preflight["context"]["artifact_id"] == artifact["artifact_id"]
        assert preflight["evidence"]["explicit_start_required"] is True
        assert preflight["evidence"]["market_database_access"] == "none"

        task = service.create_optimization_task(
            {
                "task_id": "fa-opt-smoke",
                "artifact_id": artifact["artifact_id"],
                "group_counts": [3],
                "one_side_rates": [0.0, 0.001],
            }
        )
        assert task["status"] == "ready"
        assert task["artifact_id"] == artifact["artifact_id"]
        assert task["started_at"] is None
        assert task["report_id"] is None

        completed = service.start_optimization_task("fa-opt-smoke", wait=True)
        assert completed["status"] == "completed", completed
        report = service.get_optimization_report(str(completed["report_id"]))
        assert report["status"] == "ready"
        payload = report["payload"]
        assert payload["artifact"]["artifact_id"] == artifact["artifact_id"]
        assert payload["value_field"] == "aligned_value"
        assert payload["optimization"]["candidate_count"] == 2
        assert payload["optimization"]["best_candidate"]["objective_value"] > 0
        assert payload["credibility"]["market_data_access"] == "none"

        try:
            service.preflight_optimization({"artifact_id": "factor-artifact-missing"})
        except ValueError as error:
            assert "ready artifact_id" in str(error)
        else:
            raise AssertionError("optimization must not resolve a missing artifact by factor_id")

        with sqlite3.connect(factor_store.database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "factor_optimization_tasks" in tables
        assert "factor_optimization_reports" in tables

    print("factor optimization smoke test passed")


if __name__ == "__main__":
    main()
