"""Smoke verification for the persistent stage-78.3 context backfill."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


class FakeProvider:
    request_gate = None

    def fetch_daily_security_states(
        self, *, symbol: str, start_date: str, end_date: str,
    ):
        if self.request_gate:
            self.request_gate()
        return [
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "risk_warning": symbol == "000002" and trade_date == "2026-01-05",
                "listing_status": "listed",
                "available_at": trade_date,
                "source": "fake:daily-security-state",
                "source_observed_at": "2026-01-07T00:00:00+00:00",
                "evidence": {"test": True},
            }
            for trade_date in ("2026-01-02", "2026-01-05", "2026-01-06")
            if start_date <= trade_date <= end_date
        ]

    def fetch_security_lifecycle_events(self, *, symbol: str):
        if self.request_gate:
            self.request_gate()
        if symbol == "000002":
            return []
        return [{
            "symbol": symbol,
            "event_type": "listed",
            "effective_from": "2026-01-02",
            "source": "fake:lifecycle",
            "evidence": {"symbol": symbol},
        }]

    def fetch_corporate_actions(self, *, symbol: str):
        if self.request_gate:
            self.request_gate()
        return []

    def fetch_suspensions(self, *, trade_date: str):
        if self.request_gate:
            self.request_gate()
        if trade_date != "2026-01-05":
            return []
        return [{
            "symbol": "000002",
            "trade_date": trade_date,
            "status": "suspended",
            "is_tradable": False,
            "source": "fake:suspension",
            "evidence": {"reason": "test"},
        }]


def main() -> None:
    ensure_project_root_on_sys_path()
    from data_platform.a_share_context_backfill import AShareContextBackfill
    from data_platform.storage.a_share_market_store import AShareMarketStore
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore

    with tempfile.TemporaryDirectory(prefix="scq-stage783-") as temp:
        path = Path(temp) / "market.sqlite3"
        AShareMarketStore(path).ensure_schema()
        AShareGovernanceStore(path).ensure_schema()
        _seed(path)
        service = AShareContextBackfill(
            path,
            provider=FakeProvider(),
            requests_per_minute=100000,
            max_workers=2,
            retry_count=2,
            base_backoff_seconds=0,
        )
        job = service.create_job(
            start_date="2026-01-02",
            end_date="2026-01-06",
            symbols=["000001", "000002"],
        )
        partial = service.run_job(
            str(job["job_id"]),
            publish=False,
            max_items=2,
        )
        assert partial["status"] == "queued", partial
        result = service.run_job(str(job["job_id"]), publish=True)
        assert result["status"] == "published", result
        assert result["quarantined_items"] == 0, result
        assert result["unknown_items"] >= 1, result
        with closing(sqlite3.connect(path)) as connection:
            connection.row_factory = sqlite3.Row
            status = connection.execute(
                """
                SELECT status, is_tradable FROM security_trading_status_daily
                WHERE symbol='000002' AND trade_date='2026-01-05'
                """
            ).fetchone()
            factors = int(connection.execute(
                "SELECT COUNT(*) FROM price_adjustment_factors"
            ).fetchone()[0])
            published = int(connection.execute(
                "SELECT COUNT(*) FROM data_versions WHERE status='published'"
            ).fetchone()[0])
            security_intervals = int(connection.execute(
                "SELECT COUNT(*) FROM security_master_intervals"
            ).fetchone()[0])
        assert dict(status) == {"status": "suspended", "is_tradable": 0}, status
        assert factors == 8, factors
        assert published == 1, published
        assert security_intervals == 4, security_intervals
        print({
            "status": "passed",
            "job_id": result["job_id"],
            "unknown_items": result["unknown_items"],
            "factor_rows": factors,
        })


def _seed(path: Path) -> None:
    now = "2026-01-07T00:00:00+00:00"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executemany(
            """
            INSERT INTO market_symbols (
                symbol, rqalpha_symbol, name, market, listing_status,
                source, updated_at
            ) VALUES (?, ?, ?, 'SZ', 'current', 'fake', ?)
            """,
            (
                ("000001", "000001.XSHE", "A", now),
                ("000002", "000002.XSHE", "B", now),
            ),
        )
        connection.executemany(
            """
            INSERT INTO market_trade_calendar (
                market, trade_date, is_open, session_status, source,
                source_observed_at, source_payload_hash
            ) VALUES ('CN', ?, 1, 'open', 'fake', ?, 'hash')
            """,
            (("2026-01-02", now), ("2026-01-05", now), ("2026-01-06", now)),
        )
        for symbol in ("000001", "000002"):
            for trade_date in ("2026-01-02", "2026-01-05"):
                for adjustment, close in (
                    ("raw", 10.0),
                    ("qfq", 8.0),
                    ("hfq", 12.0),
                ):
                    connection.execute(
                        """
                        INSERT INTO market_daily_prices (
                            symbol, trade_date, adjustment, open, high, low,
                            close, volume, source, imported_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 100, 'fake', ?)
                        """,
                        (
                            symbol, trade_date, adjustment, close, close,
                            close, close, now,
                        ),
                    )
        connection.executemany(
            """
            INSERT INTO market_index_daily_prices (
                index_symbol, trade_date, open, high, low, close, volume,
                amount, source, source_observed_at, source_payload_hash
            ) VALUES ('000300', ?, 1, 1, 1, 1, 1, 1, 'fake', ?, 'hash')
            """,
            (("2026-01-02", now), ("2026-01-05", now), ("2026-01-06", now)),
        )


if __name__ == "__main__":
    main()
