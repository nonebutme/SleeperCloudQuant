"""Isolated contracts for the M4 point-in-time market panorama."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.market_panorama_service import MarketPanoramaService
from data_platform import ClassificationHistoryStore, MarketPanoramaStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-panorama-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        market_database = root / "market.sqlite3"
        classification_database = root / "classification.sqlite3"
        panorama_database = root / "panorama.sqlite3"

        with sqlite3.connect(market_database) as connection:
            connection.executescript(
                """
                CREATE TABLE market_symbols (symbol TEXT PRIMARY KEY, name TEXT);
                CREATE TABLE market_daily_prices (
                    symbol TEXT, trade_date TEXT, adjustment TEXT,
                    change_pct REAL, amount REAL, turnover_rate REAL
                );
                INSERT INTO market_symbols VALUES ('000001', '平安银行'), ('000002', '万科A');
                INSERT INTO market_daily_prices VALUES
                    ('000001', '2026-07-28', 'qfq', 1.2, 1000000, 0.8),
                    ('000002', '2026-07-28', 'qfq', -0.4, 600000, 0.5);
                """
            )
        classifications = ClassificationHistoryStore(classification_database)
        classifications.upsert_intervals([
            {"symbol": "000001", "dimension": "industry", "category": "银行", "valid_from": "2020-01-01", "source": "test", "observed_at": "2026-07-28T00:00:00Z", "evidence": {"classification_standard": "测试行业标准"}},
            {"symbol": "000002", "dimension": "industry", "category": "房地产", "valid_from": "2020-01-01", "source": "test", "observed_at": "2026-07-28T00:00:00Z", "evidence": {"classification_standard": "测试行业标准"}},
        ])
        store = MarketPanoramaStore(panorama_database)
        store.upsert_board_catalog("concept", [{"board_code": "BK001", "board_name": "示例概念", "source": "test"}])
        store.upsert_board_daily("concept", "BK001", [{"trade_date": "2026-07-28", "change_pct": 2.5, "amount": 300000, "source": "test"}])
        store.upsert_fund_flows("concept", "BK001", [{"trade_date": "2026-07-28", "main_net_inflow": 120000, "main_net_ratio": 3.2, "source": "test"}])
        store.upsert_events([{"event_date": "2026-07-28", "published_at": "2026-07-28 09:00", "symbol": "000001", "event_type": "announcement", "title": "测试公告", "source": "test"}])

        service = MarketPanoramaService(
            store,
            market_database=market_database,
            classification_database=classification_database,
            max_workers=1,
        )
        payload = service.get_panorama(trade_date="2026-07-28", symbol="000001.XSHE", asset_type="stock")
        assert payload["status"] == "partial"
        assert payload["requested_trade_date"] == "2026-07-28"
        assert len(payload["sections"]["industry_heatmap"]["items"]) == 2
        assert payload["sections"]["industry_heatmap"]["coverage"]["coverage_ratio"] == 1.0
        assert payload["sections"]["concept_heatmap"]["items"][0]["board_name"] == "示例概念"
        assert payload["sections"]["concept_fund_flow"]["items"][0]["main_net_inflow"] == 120000.0
        assert payload["sections"]["events"]["items"][0]["title"] == "测试公告"
        preview = service.preview_job(datasets=["concept_board"], target_trade_date="2026-07-28")
        assert preview["datasets"] == ["concept_board"]
        assert preview["writes"] == 0

        service.governance_store.upsert_trade_calendar([
            {"market": "CN", "trade_date": day, "is_open": True, "source": "test"}
            for day in ("2026-07-27", "2026-07-28")
        ])
        service.governance_store.upsert_index_prices([{
            "index_symbol": "000001", "trade_date": "2026-07-28",
            "open": 10, "high": 11, "low": 9, "close": 10, "source": "test",
        }])
        index_gap = service.preview_job(
            datasets=["index_daily"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
        )
        assert index_gap["coverage_strategy"] == "exact_trading_day_gap"
        assert index_gap["missing_date_count"] == 11, index_gap
        assert any(item["shard_id"] == "000001" and item["missing_dates"] == ["2026-07-27"] for item in index_gap["shards"])

        concept_gap = service.preview_job(
            datasets=["concept_board"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
        )
        assert concept_gap["missing_date_count"] == 1, concept_gap
        assert concept_gap["shards"][0]["missing_dates"] == ["2026-07-27"]
        job = service.create_job(
            datasets=["concept_board"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
            selected_shards=["BK001"],
        )
        assert job["mode"] == "historical_gap"
        assert job["start_trade_date"] == "2026-07-27"

        event_range = service.preview_job(
            datasets=["events"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
            symbols=["000001.XSHE"],
        )
        assert event_range["coverage_strategy"] == "range_backfill"
        assert event_range["shards"][0]["start_date"] == "2026-07-27"

    print("Market panorama smoke passed")


if __name__ == "__main__":
    main()