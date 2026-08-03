"""Smoke checks for M3 strategy dataset dependency validation."""

from app.services.strategy_dataset_validation import validate_strategy_data_contract


def main() -> None:
    source = (
        'DATASET_REQUIREMENTS = ["a_share_daily"]\n'
        'FACTOR_REQUIREMENTS = ["close_to_ma2_bias"]\n'
        "def generate_target_weights(bars, parameters):\n"
        "    return [0.0 for _ in bars]\n"
    )
    result = validate_strategy_data_contract(source)
    assert result["ok"] is True
    assert result["execution_contract"] == "target-weights-v1"
    assert result["factors"][0]["dataset_id"] == "a_share_daily"
    missing = validate_strategy_data_contract(source, dataset_ids=["missing_dataset"])
    assert missing["ok"] is False
    assert missing["issues"][0]["code"] == "unknown_dataset"
    print("[strategy-dataset-validation] passed")


if __name__ == "__main__":
    main()

