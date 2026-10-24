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

        store.mark_item(job["job_id"], "concept_board", "BK001", status="completed", row_count=3)
        store.mark_item(
            job["job_id"], "concept_board", "BK002", status="failed",
            error="RuntimeError: curl transport failed (56): Failure when receiving data from the peer",
        )
        failed_job = store.finish_job(job["job_id"])
        assert failed_job["status"] == "partial_failure"
        assert failed_job["last_error"] != "one or more panorama items failed"
        detail = service.get_job(job["job_id"])
        assert detail["failure_summary"]["failed_item_count"] == 1
        assert detail["resolution"]["code"] == "upstream_connection_interrupted"
        assert detail["resolution"]["retry_scope"] == "failed_items_only"
        assert len(service.get_job_items(job["job_id"])) == 2
        retried = service.retry_job(job["job_id"], run_now=False)
        assert retried["status"] == "queued"
        retry_items = {item["item_key"]: item for item in service.get_job_items(job["job_id"])}
        assert retry_items["BK001"]["status"] == "completed"
        assert retry_items["BK002"]["status"] == "queued"
        event_range = service.preview_job(
            datasets=["events"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
            symbols=["000001.XSHE"],
        )
        assert event_range["coverage_strategy"] == "range_backfill"
        assert event_range["shards"][0]["start_date"] == "2026-07-27"

        global_preview = service.preview_job(
            datasets=["global_index_daily"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
            selected_shards=["SPX", "N225"],
        )
        assert global_preview["coverage_strategy"] == "range_backfill"
        assert {item["shard_id"] for item in global_preview["shards"]} == {"SPX", "N225"}
        n225_preview = next(
            item for item in global_preview["shards"] if item["shard_id"] == "N225"
        )
        assert n225_preview["coverage"] == "仅上游最近1000条日线"

        global_calls: list[tuple[str, str]] = []

        def fetch_global_index_daily_prices(**kwargs):
            global_calls.append((kwargs["index_symbol"], kwargs["endpoint"]))
            return [{
                "index_symbol": kwargs["index_symbol"],
                "trade_date": "2026-07-28",
                "open": 100, "high": 102, "low": 99, "close": 101,
                "volume": 1000, "amount": 2000,
                "source": f"test:{kwargs['endpoint']}",
            }]

        service.governance_provider.fetch_global_index_daily_prices = (
            fetch_global_index_daily_prices
        )
        global_job = service.create_job(
            datasets=["global_index_daily"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
            selected_shards=["SPX", "N225"],
        )
        service.run_job(global_job["job_id"], routes=[
            {"route_id": "global-index-us-sina", "partition_key": "US", "endpoint": "index_us_stock_sina", "priority": 10, "requests_per_minute": 600000, "timeout_seconds": 2, "retry_count": 1, "backoff_seconds": 0},
            {"route_id": "global-index-international-sina", "partition_key": "INTERNATIONAL", "endpoint": "index_global_hist_sina", "priority": 20, "requests_per_minute": 600000, "timeout_seconds": 2, "retry_count": 1, "backoff_seconds": 0},
        ])
        global_detail = service.get_job(global_job["job_id"])
        assert global_detail["status"] == "published"
        release = global_detail["global_index_release"]
        assert release["status"] == "published"
        assert release["inserted_rows"] == 2
        assert release["conflict_rows"] == 0
        assert all(item["quality"]["append_only"] for item in release["items"])
        assert all(
            item["quality"]["runtime_config"]["timeout_seconds"] == 2
            and item["quality"]["runtime_config"]["retry_count"] == 1
            for item in release["items"]
        )
        assert set(global_calls) == {
            ("SPX", "index_us_stock_sina"),
            ("N225", "index_global_hist_sina"),
        }
        with sqlite3.connect(market_database) as connection:
            stored_global = connection.execute(
                "SELECT index_symbol, trade_date FROM market_index_daily_prices "
                "WHERE index_symbol IN ('SPX', 'N225') ORDER BY index_symbol"
            ).fetchall()
        assert stored_global == [("N225", "2026-07-28"), ("SPX", "2026-07-28")]

        exact_global_preview = service.preview_job(
            datasets=["global_index_daily"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
            selected_shards=["SPX", "N225"],
        )
        assert exact_global_preview["coverage_strategy"] == "market_session_gap"
        assert exact_global_preview["request_count"] == 0
        us_gap_preview = service.preview_job(
            datasets=["global_index_daily"], start_trade_date="2026-07-27",
            target_trade_date="2026-07-28", mode="historical_gap",
            selected_shards=["IXIC"],
        )
        assert us_gap_preview["coverage_strategy"] == "market_session_gap"
        assert us_gap_preview["shards"][0]["missing_dates"] == ["2026-07-28"]

        controlled_attempts = []

        def flaky_global_read(**kwargs):
            controlled_attempts.append(kwargs["index_symbol"])
            if len(controlled_attempts) < 3:
                raise RuntimeError("transient source error")
            return [{
                "index_symbol": kwargs["index_symbol"],
                "trade_date": "2026-07-28", "open": 1, "high": 1,
                "low": 1, "close": 1, "source": "retry-test",
            }]

        service.governance_provider.fetch_global_index_daily_prices = flaky_global_read
        _, runtime = service._fetch_global_index_with_controls(
            item={"code": "IXIC", "endpoint": "index_us_stock_sina"},
            route={
                "route_id": "retry-route", "requests_per_minute": 600000,
                "timeout_seconds": 1, "retry_count": 2,
                "backoff_seconds": 0,
            },
            start_date="2026-07-28", target_date="2026-07-28",
        )
        assert runtime["attempts"] == 3
        assert len(runtime["previous_errors"]) == 2
        try:
            service._call_with_timeout(
                lambda: __import__("time").sleep(0.05) or [], 0.01,
            )
        except TimeoutError:
            pass
        else:
            raise AssertionError("frozen route timeout must be enforced")

        def conflicting_global_read(**kwargs):
            return [{
                "index_symbol": kwargs["index_symbol"],
                "trade_date": "2026-07-28",
                "open": 100, "high": 106, "low": 99, "close": 105,
                "volume": 1000, "amount": 2000,
                "source": "conflict-test",
            }]

        service.governance_provider.fetch_global_index_daily_prices = conflicting_global_read
        conflict_job_id = "panorama-sync-global-conflict"
        store.create_job(
            conflict_job_id, ["global_index_daily"], "2026-07-28", ["SPX"],
            mode="historical_gap", start_trade_date="2026-07-27",
        )
        conflict = service.run_job(conflict_job_id, routes=[{
            "route_id": "global-index-us-sina", "partition_key": "US",
            "endpoint": "index_us_stock_sina", "priority": 10,
            "requests_per_minute": 600000, "timeout_seconds": 2,
            "retry_count": 0, "backoff_seconds": 0,
        }])
        assert conflict["status"] == "partial_failure"
        assert conflict["global_index_release"]["conflict_rows"] == 1
        assert conflict["global_index_release"]["status"] == "partial_failure"
        with sqlite3.connect(market_database) as connection:
            original_close = connection.execute(
                "SELECT close FROM market_index_daily_prices "
                "WHERE index_symbol='SPX' AND trade_date='2026-07-28'"
            ).fetchone()[0]
        assert original_close == 101

        route_calls: list[str] = []

        def failed_primary(*_args, **_kwargs):
            route_calls.append("eastmoney")
            raise RuntimeError("primary unavailable")

        def successful_fallback(*_args, **_kwargs):
            route_calls.append("ths")
            return [{"trade_date": "2026-07-28", "source": "ths"}]

        service._fetch_board_daily_range = failed_primary
        service._fetch_board_daily_range_ths = successful_fallback
        routed_rows = service._fetch_board_daily_routed(
            "concept", {"board_code": "BK001", "board_name": "示例概念"},
            "2026-07-27", "2026-07-28", [
                {"route_id": "em", "endpoint": "stock_board_concept_hist_em", "priority": 10},
                {"route_id": "ths", "endpoint": "stock_board_concept_index_ths", "priority": 20},
            ],
        )
        assert routed_rows[0]["source"] == "ths"
        assert route_calls == ["eastmoney", "ths"]

        route_calls.clear()
        try:
            service._fetch_board_daily_routed(
                "concept", {"board_code": "BK001", "board_name": "示例概念"},
                "2026-07-27", "2026-07-28", [
                    {"route_id": "em", "endpoint": "stock_board_concept_hist_em", "priority": 10},
                ],
            )
        except RuntimeError as error:
            assert "primary unavailable" in str(error)
        else:
            raise AssertionError("disabled fallback route must not be called")
        assert route_calls == ["eastmoney"]

    print("Market panorama smoke passed")


if __name__ == "__main__":
    main()
