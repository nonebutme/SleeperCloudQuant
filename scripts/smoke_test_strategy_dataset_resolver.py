"""Checks point-in-time Dataset injection into target-weights-v1 bars."""

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.strategy_dataset_resolver import StrategyDatasetResolver
from backtest_kernel.strategy_execution import execute_target_weights
from data_platform.dataset_examples import get_dataset_example


class _IndexReader:
    def fetch_index_price_history(self, index_symbol, start_date=None, end_date=None):
        return [
            {"date": f"2026-01-{index + 1:02d}", "close": 100.0 + index}
            for index in range(25)
        ]


def main() -> None:
    example = get_dataset_example("index_daily", "index_daily-strategy")
    bars = [
        {"date": f"2026-01-{index + 1:02d}", "close": 10.0 + index}
        for index in range(25)
    ]
    resolver = StrategyDatasetResolver(_IndexReader())
    result = resolver.resolve(example.source_code, bars, example.parameters)
    assert len(result["bars"]) == 25
    assert result["bars"][-1]["datasets"]["index_daily"]["close"] == 124.0
    assert {item["dataset_id"] for item in result["evidence"]} == {
        "a_share_daily",
        "index_daily",
    }
    weights = execute_target_weights(example.source_code, result["bars"], example.parameters)
    assert len(weights) == 25
    assert weights[-1] == 1.0
    print("[strategy-dataset-resolver] passed")


if __name__ == "__main__":
    main()
