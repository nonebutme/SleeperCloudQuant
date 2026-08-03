from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.a_share_sync_scheduler import AShareSyncScheduler
from data_platform.storage.a_share_governance_store import AShareGovernanceStore
from data_platform.storage.a_share_market_store import AShareMarketStore


with tempfile.TemporaryDirectory() as directory:
    database = Path(directory) / "market.sqlite3"
    market = AShareMarketStore(database)
    governance = AShareGovernanceStore(database)
    scheduler = AShareSyncScheduler(
        database,
        market_store=market,
        governance_store=governance,
        provider=object(),
    )
    scheduler.ensure_schema()
    market.upsert_symbols([{"symbol": "000001", "name": "测试股票"}])
    governance.upsert_trade_calendar(
        [
            {"market": "CN", "trade_date": "2026-07-27", "is_open": True},
            {"market": "CN", "trade_date": "2026-07-28", "is_open": True},
            {"market": "CN", "trade_date": "2026-07-29", "is_open": True},
        ]
    )
    governance.upsert_lifecycle_events([{
        "symbol": "000001", "event_type": "listed",
        "effective_from": "2026-07-27", "source": "fixture",
    }])
    governance.upsert_trading_statuses(
        [
            {
                "symbol": "000001",
                "trade_date": "2026-07-28",
                "status": "unknown",
                "source": "fixture",
            }
        ]
    )
    market.upsert_daily_prices(
        [
            {"symbol": "000001", "trade_date": "2026-07-29", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1, "amount": 1},
        ],
        adjustment="qfq",
        source="fixture",
    )
    inferred = scheduler._record_inferred_historical_suspensions(
        job_id="fixture-job",
        symbol="000001",
        adjustment="qfq",
        start_date="2026-07-28",
        end_date="2026-07-28",
    )
    assert inferred == 1
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute(
            "SELECT status, is_tradable, source FROM security_trading_status_daily WHERE symbol='000001' AND trade_date='2026-07-28'"
        ).fetchone()
    assert row == ("suspended", 0, "canonical_history_gap_inference")

print("historical suspension inference smoke passed")
