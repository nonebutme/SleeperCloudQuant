"""Minimal smoke check for the M1 dataset registry adapter."""

from data_platform.dataset_registry import DatasetRegistry


def main() -> None:
    registry = DatasetRegistry()
    daily = registry.require("a_share_daily")
    assert daily.availability_status == "connected"
    assert {field.name for field in daily.fields} >= {"symbol", "trade_date", "close"}
    assert daily.supported_adjustments == ("raw", "qfq", "hfq")
    classification = registry.require("industry_classification")
    assert classification.point_in_time_policy == "as_of_trade_date"
    assert len(registry.list()) >= 10
    assert len(registry.list(status="connected")) > 0
    print("[dataset-registry] passed")


if __name__ == "__main__":
    main()

