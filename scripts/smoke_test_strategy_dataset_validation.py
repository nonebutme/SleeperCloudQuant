"""Smoke checks for M3 strategy dataset dependency validation."""

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.strategy_dataset_validation import validate_strategy_data_contract


def main() -> None:
    source = (
        'DATASET_REQUIREMENTS = ["a_share_daily", "factor_values"]\n'
        'FACTOR_REQUIREMENTS = ["close_to_ma2_bias"]\n'
        "def generate_target_weights(bars, parameters):\n"
        "    return [0.0 for _ in bars]\n"
    )
    result = validate_strategy_data_contract(source)
    assert result["ok"] is True
    assert result["execution_contract"] == "target-weights-v1"
    assert result["factors"][0]["dataset_id"] == "factor_values"
    strict_source = (
        'DATASET_REQUIREMENTS = ["a_share_daily"]\n'
        'DATASET_CONTRACTS = [{"dataset_id": "a_share_daily", '
        '"required_fields": ["close"], "adjustment": "qfq"}]\n'
        "def generate_target_weights(bars, parameters):\n"
        "    return [0.0 for _ in bars]\n"
    )
    strict = validate_strategy_data_contract(strict_source)
    assert strict["ok"] is True, strict
    assert strict["strict_contract"]["contracts"][0]["required_fields"] == ["close"]
    undeclared_field_source = strict_source.replace(
        "return [0.0 for _ in bars]",
        'return [float(bar.get("volume") or 0.0) * 0.0 for bar in bars]',
    )
    undeclared = validate_strategy_data_contract(undeclared_field_source)
    assert undeclared["ok"] is False
    assert any(
        item["code"] == "strategy_field_access_undeclared"
        for item in undeclared["issues"]
    )
    missing = validate_strategy_data_contract(source, dataset_ids=["missing_dataset"])
    assert missing["ok"] is False
    assert missing["issues"][0]["code"] == "unknown_dataset"
    print("[strategy-dataset-validation] passed")


if __name__ == "__main__":
    main()
