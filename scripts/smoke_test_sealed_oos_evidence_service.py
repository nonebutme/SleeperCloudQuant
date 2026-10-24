"""Smoke checks for append-only sealed OOS evidence persistence."""

from pathlib import Path
from tempfile import TemporaryDirectory

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.sealed_oos_evidence_service import SealedOosEvidenceService


def main() -> None:
    with TemporaryDirectory() as directory:
        service = SealedOosEvidenceService(Path(directory) / "sealed-oos.sqlite3")
        values = {
            "strategy_id": "fujing_v2",
            "strategy_version": "v7",
            "source_sha256": "source-sha",
            "parameters": {"amplitude_ratio_min": 0.01},
            "dataset_bindings": [{
                "dataset_id": "a_share_daily",
                "version_id": "release-001",
                "quality_report_id": "quality-001",
            }],
            "factor_bindings": [{
                "factor_id": "winner_proxy_120d",
                "artifact_id": "artifact-001",
            }],
            "universe_snapshot_id": "universe-001",
            "development_window": {"start_date": "2022-01-01", "end_date": "2024-12-31"},
            "oos_window": {"start_date": "2025-01-01", "end_date": "2025-12-31"},
            "primary_metrics": ("annualized_return", "max_drawdown"),
            "decision_thresholds": {"max_drawdown_gte": -0.25},
        }
        manifest = service.seal(**values)
        assert service.seal(**values)["freeze_id"] == manifest["freeze_id"]
        verified = service.verify_inputs(
            manifest["freeze_id"],
            source_sha256="source-sha",
            parameters={"amplitude_ratio_min": 0.01},
            dataset_bindings=values["dataset_bindings"],
            factor_bindings=values["factor_bindings"],
            universe_snapshot_id="universe-001",
        )
        assert verified["ok"] is True
        record = service.mark_viewed(
            manifest["freeze_id"],
            result_sha256="result-sha",
            viewed_at="2026-08-16T18:00:00+08:00",
        )
        assert record["status"] == "viewed_no_longer_unseen"
        assert service.get(manifest["freeze_id"])["view_record"]["result_sha256"] == "result-sha"
        try:
            service.mark_viewed(
                manifest["freeze_id"],
                result_sha256="changed-result",
                viewed_at="2026-08-16T18:05:00+08:00",
            )
        except ValueError as error:
            assert "immutable" in str(error)
        else:
            raise AssertionError("view evidence must be immutable")
    print("[sealed-oos-evidence-service] passed")


if __name__ == "__main__":
    main()
