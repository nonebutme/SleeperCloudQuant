"""Stage-four factor artifact consumption and strategy export smoke test."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.api.factor_research import build_factor_research_routes
from app.main import SimpleApiApp
from app.runtime.http_adapter import dispatch_request
from app.services.factor_analysis_service import FactorAnalysisService
from app.services.strategy_dataset_resolver import StrategyDatasetResolver
from backtest_kernel.strategy_execution import execute_target_weights
from data_platform.dataset_examples import get_dataset_example
from data_platform.dataset_registry import DatasetRegistry
from factor_lab.dataset_bindings import get_factor_dataset_binding
from factor_lab.research_core import canonical_hash
from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore


class _IndexReader:
    pass


def _seed_artifact(store: SqliteFactorResearchStore) -> dict[str, object]:
    config = {
        "factor_id": "stage4_signal",
        "factor_version": "v1",
        "factor_adjustment": "raw",
        "preprocessing": {"direction": "positive"},
    }
    context = {"effective_range": {"start_date": "2026-08-06", "end_date": "2026-08-07"}}
    store.create_task(
        task_id="stage4-factor-task",
        config=config,
        context=context,
        context_hash=canonical_hash(context),
        preflight={"status": "ready"},
        data_version_id="dv-stage4",
        quality_report_id="qr-stage4",
        pool_snapshot={"symbols": ["300333"], "source": "controlled-test"},
    )
    store.replace_observations(
        "stage4-factor-task",
        [
            {
                "trade_date": "2026-08-06",
                "symbol": "300333",
                "raw_value": -2.0,
                "processed_value": -2.0,
                "aligned_value": -2.0,
            },
            {
                "trade_date": "2026-08-07",
                "symbol": "300333",
                "raw_value": 3.0,
                "processed_value": 3.0,
                "aligned_value": 3.0,
            },
        ],
    )
    artifact = store.publish_artifact("stage4-factor-task")
    store.review_artifact(
        artifact["artifact_id"],
        decision="approved",
        policy_id="stage4-smoke-fixture",
        reviewer="stage4-smoke",
        note="fixture-only registration for strategy consumption plumbing",
    )
    store.register_artifact(artifact["artifact_id"])
    return store.get_artifact(artifact["artifact_id"])


def main() -> None:
    definition = DatasetRegistry().require("factor_values")
    fields = [field.name for field in definition.fields]
    assert fields == [
        "symbol", "trade_date", "factor_id", "artifact_id", "value", "aligned_value"
    ]
    assert definition.point_in_time_policy == "as_of_trade_date"
    binding = get_factor_dataset_binding("stage4_signal")
    assert binding.required_fields[-1] == "aligned_value"
    catalog_example = get_dataset_example("factor_values", "factor_values-strategy")
    assert 'FACTOR_VALUE_FIELD = "aligned_value"' in catalog_example.source_code
    assert catalog_example.runtime_status == "template_only"

    with tempfile.TemporaryDirectory(prefix="scq-stage4-factor-", ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        store = SqliteFactorResearchStore(root / "factor.sqlite3")
        artifact = _seed_artifact(store)
        service = FactorAnalysisService(
            market_database_path=root / "market.sqlite3",
            research_store=store,
        )
        declaration = service.export_strategy_factor_declaration(str(artifact["artifact_id"]))
        assert declaration["artifact"]["artifact_id"] == artifact["artifact_id"]
        assert declaration["value_field"] == "aligned_value"
        assert declaration["parameters"]["factor_artifacts"] == {
            "stage4_signal": artifact["artifact_id"]
        }
        assert declaration["execution_policy"] == "explicit_start_required"
        assert declaration["writes"] == 0
        assert declaration["task_started"] is False

        resolver = StrategyDatasetResolver(_IndexReader(), factor_store=store)
        source = declaration["source_code"]
        parameters = declaration["parameters"]
        frozen = resolver.freeze_parameters(source, parameters)
        bars = [
            {"symbol": "300333", "trade_date": "2026-08-06", "close": 10.0},
            {"symbol": "300333", "trade_date": "2026-08-07", "close": 11.0},
        ]
        resolved = resolver.resolve(source, bars, frozen)
        assert resolved["evidence"][-1]["artifact_id"] == artifact["artifact_id"]
        assert resolved["bars"][-1]["datasets"]["factor_values"]["stage4_signal"][
            "aligned_value"
        ] == 3.0
        assert execute_target_weights(source, resolved["bars"], frozen) == [0.0, 1.0]

        try:
            resolver.resolve(
                source, bars, frozen, {"data_version_id": "dv-other"},
            )
        except RuntimeError as error:
            assert "data version mismatch" in str(error)
        else:
            raise AssertionError("factor artifact from another data version must fail")

        with_warmup = resolver.resolve(
            source,
            [{"symbol": "300333", "trade_date": "2026-08-05", "close": 9.0}, *bars],
            frozen,
            {
                "evaluation_start_date": "2026-08-06",
                "evaluation_end_date": "2026-08-07",
            },
        )
        assert with_warmup["bars"][0]["datasets"]["factor_values"]["stage4_signal"] is None
        assert with_warmup["evidence"][-1]["coverage_policy"] == (
            "evaluation_complete_warmup_optional"
        )
        assert with_warmup["evidence"][-1]["required_matched_rows"] == 2

        try:
            resolver.freeze_parameters(source, {})
        except RuntimeError as error:
            assert "binding is required" in str(error)
        else:
            raise AssertionError("factor artifact must never fall back to latest")

        bad = {**parameters, "factor_artifacts": {"stage4_signal": "factor-artifact-missing"}}
        try:
            resolver.freeze_parameters(source, bad)
        except RuntimeError as error:
            assert "unavailable" in str(error)
        else:
            raise AssertionError("missing exact artifact_id must fail")

        try:
            resolver.resolve(
                source,
                [*bars, {"symbol": "300333", "trade_date": "2026-08-08", "close": 9.0}],
                frozen,
            )
        except RuntimeError as error:
            assert "coverage is incomplete" in str(error)
        else:
            raise AssertionError("missing artifact date coverage must fail")

        ineligible_missing = resolver.resolve(
            source,
            [
                *bars,
                {
                    "symbol": "300333",
                    "trade_date": "2026-08-08",
                    "close": 9.0,
                    "datasets": {
                        "a_share_catalog": {
                            "listing_status": "listed",
                            "risk_warning": True,
                        }
                    },
                },
            ],
            frozen,
        )
        assert ineligible_missing["evidence"][-1]["required_rows"] == 2
        assert ineligible_missing["evidence"][-1]["required_matched_rows"] == 2
        assert ineligible_missing["evidence"][-1]["decision_ineligible_rows"] == 1
        assert (
            ineligible_missing["bars"][-1]["datasets"]["factor_values"]["stage4_signal"]
            is None
        )

        try:
            service.export_strategy_factor_declaration("factor-artifact-missing")
        except ValueError as error:
            assert "not found" in str(error)
        else:
            raise AssertionError("missing export artifact_id must fail")

        app = SimpleApiApp("test", build_factor_research_routes(service))
        status, payload = dispatch_request(
            app,
            method="GET",
            path=(
                "/api/factor-research/artifacts/"
                f"{artifact['artifact_id']}/strategy-declaration"
            ),
        )
        assert status == 200
        assert payload["artifact"]["artifact_id"] == artifact["artifact_id"]
        assert payload["task_started"] is False

    print("stage-four factor consumption smoke test passed")


if __name__ == "__main__":
    main()
