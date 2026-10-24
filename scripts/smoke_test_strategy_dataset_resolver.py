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


class _StrictIndexReader(_IndexReader):
    def __init__(self, *, status_overrides=None):
        self._status_overrides = dict(status_overrides or {})

    def fetch_trade_calendar(self, start_date=None, end_date=None):
        return [
            {"trade_date": f"2026-02-{index + 1:02d}", "is_open": True}
            for index in range(8)
        ]

    def fetch_trading_status_history(self, symbol, start_date=None, end_date=None):
        rows = []
        for index in range(8):
            trade_date = f"2026-02-{index + 1:02d}"
            rows.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "status": "normal",
                "is_tradable": self._status_overrides.get(trade_date, True),
            })
        return rows


class _MarketReader:
    def fetch_symbol_history(
        self, symbol, start_date=None, end_date=None, *, data_version_id=None,
    ):
        assert data_version_id == "test-security-version"
        return [{
            "symbol": symbol,
            "name": "历史名称",
            "listing_status": "listed",
            "risk_warning": False,
            "valid_from": "2020-01-01",
            "valid_to": None,
            "available_at": "2020-01-01T08:00:00+08:00",
        }]


class _LimitedMarketReader(_MarketReader):
    def fetch_symbol_history(
        self, symbol, start_date=None, end_date=None, *, data_version_id=None,
    ):
        rows = super().fetch_symbol_history(
            symbol, start_date, end_date, data_version_id=data_version_id,
        )
        rows[0]["valid_to"] = "2026-02-06"
        return rows


def main() -> None:
    example = get_dataset_example("index_daily", "index_daily-strategy")
    bars = [
        {"date": f"2026-01-{index + 1:02d}", "close": 10.0 + index}
        for index in range(25)
    ]
    resolver = StrategyDatasetResolver(_IndexReader(), market_reader=_MarketReader())
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
    strict_source = '''
DATASET_REQUIREMENTS = ["a_share_daily", "a_share_catalog"]
DATASET_CONTRACTS = [
    {"dataset_id": "a_share_daily", "required_fields": ["close"],
     "minimum_history": 3, "adjustment": "qfq", "coverage_mode": "same_trade_date"},
    {"dataset_id": "a_share_catalog", "required_fields": ["symbol", "name", "listing_status"],
     "coverage_mode": "as_of_trade_date"},
]
def generate_target_weights(bars, parameters):
    return [0.0 for _ in bars]
'''
    strict_bars = [
        {"symbol": "000001.XSHE", "date": f"2026-02-{index + 1:02d}", "close": 10.0 + index}
        for index in range(8)
    ]
    try:
        resolver.resolve(
            strict_source,
            strict_bars,
            {},
            {"evaluation_start_date": "2026-02-04", "evaluation_end_date": "2026-02-08",
             "adjustment": "qfq"},
        )
    except RuntimeError as error:
        assert "point_in_time_a_share_catalog_requires_data_version" in str(error)
    else:
        raise AssertionError("strict point-in-time catalog must require a frozen data version")
    strict = resolver.resolve(
        strict_source,
        strict_bars,
        {},
        {"evaluation_start_date": "2026-02-04", "evaluation_end_date": "2026-02-08",
         "adjustment": "qfq", "data_version_id": "test-security-version"},
    )
    assert strict["research_window"]["warmup"]["row_count"] == 3
    assert strict["bars"][0]["datasets"]["a_share_catalog"]["name"] == "历史名称"
    assert strict["evidence"][-1]["mode"] == "warmup_separated_from_evaluation"
    try:
        resolver.resolve(
            strict_source,
            strict_bars[1:],
            {},
            {"evaluation_start_date": "2026-02-04", "evaluation_end_date": "2026-02-08",
             "adjustment": "qfq", "data_version_id": "test-security-version"},
        )
    except RuntimeError as error:
        assert "warmup_history_incomplete" in str(error)
    else:
        raise AssertionError("strict contract must reject incomplete warm-up")

    status_source = '''
DATASET_REQUIREMENTS = [
    "a_share_daily", "a_share_catalog", "trade_calendar", "trading_status",
]
DATASET_CONTRACTS = [
    {"dataset_id": "a_share_daily", "required_fields": ["open", "high", "low", "close", "volume"],
     "minimum_history": 3, "adjustment": "qfq", "coverage_mode": "same_trade_date"},
    {"dataset_id": "a_share_catalog", "required_fields": ["symbol", "listing_status", "risk_warning", "valid_from", "available_at"],
     "coverage_mode": "as_of_trade_date"},
    {"dataset_id": "trade_calendar", "required_fields": ["trade_date", "is_open"],
     "coverage_mode": "same_trade_date"},
    {"dataset_id": "trading_status", "required_fields": ["trade_date", "is_tradable"],
     "coverage_mode": "same_trade_date"},
]
def generate_target_weights(bars, parameters):
    return [0.0 for _ in bars]
'''
    status_bars = [
        {
            "symbol": "000001.XSHE", "date": f"2026-02-{index + 1:02d}",
            "open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0,
            "volume": 1000.0,
        }
        for index in range(8)
    ]
    status_context = {
        "evaluation_start_date": "2026-02-04",
        "evaluation_end_date": "2026-02-08",
        "adjustment": "qfq",
        "data_version_id": "test-security-version",
    }
    status_resolver = StrategyDatasetResolver(
        _StrictIndexReader(), market_reader=_MarketReader()
    )
    status_result = status_resolver.resolve(
        status_source, status_bars, {}, status_context
    )
    assert status_result["bars"][-1]["datasets"]["trading_status"]["is_tradable"] is True
    try:
        status_resolver.resolve(
            status_source,
            status_bars,
            {},
            {**status_context, "adjustment": "raw"},
        )
    except ValueError as error:
        assert "strategy_adjustment_mismatch" in str(error)
    else:
        raise AssertionError("strict qfq contract must reject raw runtime adjustment")

    unknown_resolver = StrategyDatasetResolver(
        _StrictIndexReader(status_overrides={"2026-02-05": None}),
        market_reader=_MarketReader(),
    )
    try:
        unknown_resolver.resolve(status_source, status_bars, {}, status_context)
    except RuntimeError as error:
        assert "trading_status_value_incomplete" in str(error)
    else:
        raise AssertionError("unknown tradability must fail closed")

    conflict_resolver = StrategyDatasetResolver(
        _StrictIndexReader(status_overrides={"2026-02-05": False}),
        market_reader=_MarketReader(),
    )
    try:
        conflict_resolver.resolve(status_source, status_bars, {}, status_context)
    except RuntimeError as error:
        assert "trading_status_price_conflict" in str(error)
    else:
        raise AssertionError("suspended status with positive volume must fail closed")

    limited_catalog_resolver = StrategyDatasetResolver(
        _StrictIndexReader(), market_reader=_LimitedMarketReader()
    )
    try:
        limited_catalog_resolver.resolve(
            status_source, status_bars, {}, status_context
        )
    except RuntimeError as error:
        assert "point_in_time_a_share_catalog_ambiguous" in str(error)
        assert "2026-02-07" in str(error)
    else:
        raise AssertionError("catalog coverage ending before the run must fail closed")
    print("[strategy-dataset-resolver] passed")


if __name__ == "__main__":
    main()
