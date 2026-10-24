"""Smoke test for the minimal factor-lab vertical slice."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path
import tempfile
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


def _bootstrap() -> None:
    ensure_project_root_on_sys_path()


def main() -> None:
    _bootstrap()

    from app.services import FactorResearchService, MarketDataService
    from data_platform import CachedMarketDataRepository, SqliteMetadataStore
    from factor_lab import SqliteFactorStore

    database_path = Path(tempfile.gettempdir()) / f"factor_lab_smoke_{os.getpid()}.sqlite3"
    metadata_store = SqliteMetadataStore(database_path)
    market_service = MarketDataService(
        CachedMarketDataRepository(FakeMarketDataRepository(), metadata_store)
    )
    factor_store = SqliteFactorStore(database_path)
    factor_service = FactorResearchService(market_service, factor_store)

    definitions = factor_service.list_factor_definitions()
    if len(definitions) != 7:
        raise SystemExit("factor lab smoke test failed: factor definitions count mismatch")

    result = factor_service.run_factor(
        factor_id="close_to_close_return_1d",
        symbol="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    if result.factor_id != "close_to_close_return_1d":
        raise SystemExit("factor lab smoke test failed: unexpected factor id")
    if result.row_count != 2:
        raise SystemExit("factor lab smoke test failed: unexpected factor row count")

    ma2_result = factor_service.run_factor(
        factor_id="close_to_ma2_bias",
        symbol="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    if ma2_result.factor_id != "close_to_ma2_bias":
        raise SystemExit("factor lab smoke test failed: unexpected ma2 factor id")
    if ma2_result.row_count != 2:
        raise SystemExit("factor lab smoke test failed: unexpected ma2 factor row count")

    pool_result = factor_service.run_factor_for_symbols(
        factor_id="close_to_close_return_1d",
        symbols=["000001.XSHE", "600000.XSHG"],
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    if pool_result.run_count != 2 or pool_result.row_count != 4:
        raise SystemExit("factor lab smoke test failed: symbols pool result mismatch")

    ma2_pool_result = factor_service.run_factor_for_symbols(
        factor_id="close_to_ma2_bias",
        symbols=["000001.XSHE", "600000.XSHG"],
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    if ma2_pool_result.run_count != 2 or ma2_pool_result.row_count != 4:
        raise SystemExit("factor lab smoke test failed: ma2 symbols pool result mismatch")

    index_pool_result = factor_service.run_factor_for_index(
        factor_id="close_to_close_return_1d",
        index_code="000300.XSHG",
        date="2020-01-02",
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    if index_pool_result.run_count != 2 or len(index_pool_result.symbols) != 2:
        raise SystemExit("factor lab smoke test failed: index pool result mismatch")

    ma2_index_pool_result = factor_service.run_factor_for_index(
        factor_id="close_to_ma2_bias",
        index_code="000300.XSHG",
        date="2020-01-02",
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    if ma2_index_pool_result.run_count != 2 or len(ma2_index_pool_result.symbols) != 2:
        raise SystemExit("factor lab smoke test failed: ma2 index pool result mismatch")

    rows = factor_service.get_factor_values(
        factor_id="close_to_close_return_1d",
        symbol="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    if len(rows) != 2:
        raise SystemExit("factor lab smoke test failed: persisted row count mismatch")

    expected_first = (10.7 / 10.2) - 1.0
    expected_second = (10.5 / 10.7) - 1.0
    if abs(rows[0].value - expected_first) > 1e-9:
        raise SystemExit("factor lab smoke test failed: first factor value mismatch")
    if abs(rows[1].value - expected_second) > 1e-9:
        raise SystemExit("factor lab smoke test failed: second factor value mismatch")

    ma2_rows = factor_service.get_factor_values(
        factor_id="close_to_ma2_bias",
        symbol="000001.XSHE",
        start_date="2020-01-01",
        end_date="2020-01-03",
    )
    if len(ma2_rows) != 2:
        raise SystemExit("factor lab smoke test failed: ma2 persisted row count mismatch")

    expected_ma2_first = (10.7 / ((10.2 + 10.7) / 2.0)) - 1.0
    expected_ma2_second = (10.5 / ((10.7 + 10.5) / 2.0)) - 1.0
    if abs(ma2_rows[0].value - expected_ma2_first) > 1e-9:
        raise SystemExit("factor lab smoke test failed: first ma2 factor value mismatch")
    if abs(ma2_rows[1].value - expected_ma2_second) > 1e-9:
        raise SystemExit("factor lab smoke test failed: second ma2 factor value mismatch")

    ranking = factor_service.get_factor_top_n(
        factor_id="close_to_close_return_1d",
        trade_date="2020-01-02",
        start_date="2020-01-01",
        end_date="2020-01-03",
        limit=1,
        descending=True,
    )
    if ranking.row_count != 1:
        raise SystemExit("factor lab smoke test failed: ranking row count mismatch")
    if ranking.rows[0].symbol != "600000.XSHG":
        raise SystemExit("factor lab smoke test failed: top ranking symbol mismatch")

    ma2_ranking = factor_service.get_factor_top_n(
        factor_id="close_to_ma2_bias",
        trade_date="2020-01-02",
        start_date="2020-01-01",
        end_date="2020-01-03",
        limit=1,
        descending=True,
    )
    if ma2_ranking.row_count != 1:
        raise SystemExit("factor lab smoke test failed: ma2 ranking row count mismatch")
    if ma2_ranking.rows[0].symbol != "600000.XSHG":
        raise SystemExit("factor lab smoke test failed: ma2 top ranking symbol mismatch")

    print("factor lab smoke test passed")


class FakeMarketDataRepository:
    """Deterministic market-data repository for factor-lab smoke validation."""

    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        if symbol == "600000.XSHG":
            return [
                {
                    "date": "2020-01-01",
                    "open": 8.0,
                    "high": 8.4,
                    "low": 7.9,
                    "close": 8.0,
                    "volume": 2000.0,
                },
                {
                    "date": "2020-01-02",
                    "open": 8.0,
                    "high": 8.8,
                    "low": 8.0,
                    "close": 8.8,
                    "volume": 2500.0,
                },
                {
                    "date": "2020-01-03",
                    "open": 8.8,
                    "high": 8.9,
                    "low": 8.6,
                    "close": 8.7,
                    "volume": 1800.0,
                },
            ]
        return [
            {
                "date": "2020-01-01",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 1000.0,
            },
            {
                "date": "2020-01-02",
                "open": 10.2,
                "high": 10.8,
                "low": 10.1,
                "close": 10.7,
                "volume": 1200.0,
            },
            {
                "date": "2020-01-03",
                "open": 10.7,
                "high": 11.0,
                "low": 10.6,
                "close": 10.5,
                "volume": 900.0,
            },
        ]

    def fetch_index_components(
        self,
        index_code: str,
        date: str | None = None,
    ) -> Sequence[str]:
        if index_code == "000300.XSHG":
            return ["000001.XSHE", "600000.XSHG"]
        return []

    def fetch_financial_indicators(
        self,
        symbol: str,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        return []

    def fetch_trading_calendar(self, start_date: str, end_date: str) -> Sequence[str]:
        return ["2020-01-01", "2020-01-02", "2020-01-03"]


if __name__ == "__main__":
    main()
