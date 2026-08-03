"""Windows-safe P2 Strategy Manifest persistence smoke checks."""

from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.sqlite_strategy_manifest_service import SqliteStrategyManifestService
from domain.dataset.product_models import DatasetRequirement
from domain.strategy import StrategyManifest


class _Products:
    def get_product(self, dataset_id: str):
        if dataset_id != "a_share_daily":
            raise KeyError(dataset_id)
        return {
            "dataset_id": dataset_id,
            "status": "connected",
            "fields": [],
            "schema_status": "metadata_pending",
        }


def main() -> None:
    with TemporaryDirectory() as directory:
        service = SqliteStrategyManifestService(
            Path(directory) / "strategy.sqlite3",
            dataset_product_service=_Products(),
        )
        requirement = DatasetRequirement(
            dataset_id="a_share_daily",
            required_fields=("symbol", "trade_date", "close"),
            adjustment="qfq",
        )
        manifest = StrategyManifest(
            strategy_id="momentum-rotation",
            strategy_version="v1",
            name="Momentum Rotation",
            source_sha256="source-hash",
            dataset_requirements=(requirement,),
            assets={"universe": "explicit_symbols"},
        )
        saved = service.save(manifest)
        assert saved["validation"]["status"] == "valid_with_warnings"
        assert service.save(manifest)["manifest_sha256"] == saved["manifest_sha256"]
        assert service.get("momentum-rotation", "v1")["name"] == "Momentum Rotation"
        changed = StrategyManifest(
            strategy_id="momentum-rotation",
            strategy_version="v1",
            name="Changed",
            source_sha256="source-hash",
        )
        try:
            service.save(changed)
        except ValueError as exc:
            assert "immutable" in str(exc)
        else:
            raise AssertionError("changed immutable manifest must be rejected")
    print("[sqlite-strategy-manifest-service] passed")


if __name__ == "__main__":
    main()

