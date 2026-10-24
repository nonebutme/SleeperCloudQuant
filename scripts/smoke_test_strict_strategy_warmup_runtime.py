"""Verify strict strategy warm-up is fetched but excluded from evaluation metrics."""

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.strategy_dataset_resolver import StrategyDatasetResolver
from backtest_kernel.adapters.local_sqlite_runtime import LocalSQLiteBacktestRuntime


SOURCE = '''
DATASET_REQUIREMENTS = ["a_share_daily"]
DATASET_CONTRACTS = [
    {"dataset_id": "a_share_daily", "required_fields": ["open", "high", "low", "close", "volume"],
     "minimum_history": 3, "adjustment": "qfq", "coverage_mode": "same_trade_date"},
]
def generate_target_weights(bars, parameters):
    return [1.0 if index >= 2 else 0.0 for index in range(len(bars))]
'''


class _Repository:
    def __init__(self) -> None:
        self.requested_start = ""

    def fetch_price_history(self, symbol, start_date, end_date, adjustment="raw"):
        self.requested_start = start_date
        return [
            {
                "symbol": symbol,
                "date": f"2026-01-{day:02d}",
                "open": 10.0 + day,
                "high": 10.2 + day,
                "low": 9.8 + day,
                "close": 10.1 + day,
                "volume": 1000 + day,
            }
            for day in range(1, 9)
        ]


class _Reader:
    pass


def main() -> None:
    repository = _Repository()
    resolver = StrategyDatasetResolver(_Reader())
    runtime = LocalSQLiteBacktestRuntime(
        repository,
        strategy_resolver=lambda strategy_id, version: {
            "strategy_id": strategy_id,
            "latest_version": version or "v1",
            "source_code": SOURCE,
            "source_sha256": "strict-source",
            "execution_contract": "target-weights-v1",
        },
        dataset_resolver=resolver.resolve,
    )
    result = runtime.run(
        {
            "run_id": "strict-warmup-smoke",
            "strategy_name": "strict-warmup",
            "symbol": "000001.XSHE",
            "start_date": "2026-01-04",
            "end_date": "2026-01-08",
            "parameters": {"adjustment": "qfq"},
            "extra_config": {"strategy_id": "strict-warmup", "strategy_version": "v1"},
        }
    )
    raw = result["raw_result"]
    assert repository.requested_start < "2026-01-04"
    assert raw["warmup_bar_count"] == 3
    assert raw["bar_count"] == 5
    assert len(raw["accounts"]) == 5
    assert raw["accounts"][0]["snapshot_time"].startswith("2026-01-04")
    adjustment_evidence = raw["strategy_binding"]["datasets"][0]
    assert adjustment_evidence["declared_adjustment"] == "qfq"
    assert adjustment_evidence["runtime_adjustment"] == "qfq"
    assert raw["strategy_binding"]["datasets"][-1]["mode"] == "warmup_separated_from_evaluation"
    assert raw["strategy_binding"]["causality"]["status"] == "passed"
    try:
        runtime.run(
            {
                "run_id": "strict-adjustment-mismatch-smoke",
                "strategy_name": "strict-warmup",
                "symbol": "000001.XSHE",
                "start_date": "2026-01-04",
                "end_date": "2026-01-08",
                "parameters": {"adjustment": "raw"},
                "extra_config": {
                    "strategy_id": "strict-warmup", "strategy_version": "v1",
                },
            }
        )
    except ValueError as error:
        assert "strategy_adjustment_mismatch" in str(error)
    else:
        raise AssertionError("strict qfq strategy must reject raw runtime bars")
    print("[strict-strategy-warmup-runtime] passed")


if __name__ == "__main__":
    main()
