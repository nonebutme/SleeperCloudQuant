"""Smoke checks for M2 factor dataset dependency bindings."""

from factor_lab.dataset_bindings import (
    get_factor_dataset_binding,
    resolve_factor_input_provenance,
)


def main() -> None:
    binding = get_factor_dataset_binding("close_to_ma2_bias")
    assert binding.dataset_id == "a_share_daily"
    assert binding.required_fields == ("symbol", "trade_date", "close")
    unavailable = resolve_factor_input_provenance(
        factor_id=binding.factor_id,
        symbol="000001.XSHE",
        start_date=None,
        end_date=None,
        published_version_resolver=None,
    )
    assert unavailable.status == "unavailable"
    assert unavailable.reason == "published_version_resolver_unavailable"
    resolved = resolve_factor_input_provenance(
        factor_id=binding.factor_id,
        symbol="000001.XSHE",
        start_date="2026-01-01",
        end_date="2026-01-02",
        published_version_resolver=lambda **_: {"status": "published", "version_id": "scq-test"},
    )
    assert resolved.status == "published"
    assert resolved.version_id == "scq-test"
    print("[factor-dataset-bindings] passed")


if __name__ == "__main__":
    main()

