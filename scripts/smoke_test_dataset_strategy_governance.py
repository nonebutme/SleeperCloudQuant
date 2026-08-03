"""P0 contract smoke checks for Dataset Product and Strategy Manifest."""

from domain.dataset.product_models import (
    DatasetProduct,
    DatasetRelease,
    DatasetRequirement,
    ResolvedDatasetBinding,
    RunInputBundle,
)
from domain.strategy import StrategyManifest


def main() -> None:
    product = DatasetProduct(
        dataset_id="a_share_daily",
        name="A-share daily",
        layer_id="L1",
        status="connected",
        supported_adjustments=("raw", "qfq", "hfq"),
    )
    requirement = DatasetRequirement(
        dataset_id=product.dataset_id,
        required_fields=("symbol", "trade_date", "close"),
        adjustment="qfq",
    )
    release = DatasetRelease(
        version_id="scq-test",
        dataset_id=product.dataset_id,
        status="published",
    )
    binding = ResolvedDatasetBinding(requirement=requirement, release=release)
    manifest = StrategyManifest(
        strategy_id="strategy-test",
        strategy_version="v1",
        name="Strategy Test",
        source_sha256="abc123",
        dataset_requirements=(requirement,),
    )
    bundle = RunInputBundle(
        bundle_id="bundle-test",
        strategy_id=manifest.strategy_id,
        strategy_version=manifest.strategy_version,
        strategy_source_sha256=manifest.source_sha256,
        datasets=(binding,),
    )
    assert manifest.section_names()[0] == "assets"
    assert bundle.datasets[0].release.status == "published"
    print("[dataset-strategy-governance] passed")


if __name__ == "__main__":
    main()

