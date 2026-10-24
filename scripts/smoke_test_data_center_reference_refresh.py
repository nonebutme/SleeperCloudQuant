"""Deterministic smoke test for the governed manual reference-data refresh."""

from __future__ import annotations

import sqlite3
import tempfile
import json
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


class _ReferenceProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def sync_symbol(self, *_args, **_kwargs):
        raise AssertionError("reference refresh must not start a price sync")

    def list_symbols(self):
        self.calls.append("catalog")
        return [{"symbol": "000001", "name": "平安银行", "source": "smoke"}]

    def fetch_trade_calendar(
        self, *, start_date: str, end_date: str, market: str = "CN",
    ):
        self.calls.append("calendar")
        days = ("2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09")
        return [
            {
                "market": market,
                "trade_date": day,
                "is_open": True,
                "source": "smoke",
                "source_observed_at": "2026-01-09T10:00:00+08:00",
            }
            for day in days
            if start_date <= day <= end_date
        ]

    def fetch_index_daily_prices(
        self, *, index_symbol: str, start_date: str, end_date: str,
    ):
        self.calls.append("index")
        return [{
            "index_symbol": index_symbol,
            "trade_date": end_date,
            "open": 4000,
            "high": 4010,
            "low": 3990,
            "close": 4005,
            "volume": 1,
            "amount": 1,
            "source": "smoke",
            "source_observed_at": "2026-01-09T10:00:00+08:00",
        }]


def _row_counts(database: Path) -> tuple[int, int, int]:
    with closing(sqlite3.connect(database)) as connection:
        return tuple(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "market_symbols", "market_trade_calendar", "market_index_daily_prices",
            )
        )


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.api.data_center import build_data_center_routes
    from app.main import SimpleApiApp
    from app.runtime.http_adapter import dispatch_request
    from app.services.data_center_service import DataCenterService
    from data_platform.a_share_sync_scheduler import AShareSyncScheduler
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.a_share_market_store import AShareMarketStore
    from data_platform.storage.data_center_store import DataCenterStore

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(
        prefix="scq-reference-refresh-",
        dir=root / "tmp",
        ignore_cleanup_errors=True,
    ) as temporary:
        database = Path(temporary) / "market.sqlite3"
        market = AShareMarketStore(database)
        governance = AShareGovernanceStore(database)
        provider = _ReferenceProvider()
        scheduler = AShareSyncScheduler(
            database,
            market_store=market,
            governance_store=governance,
            provider=provider,
            requests_per_minute=1_000_000,
            max_workers=1,
            retry_count=1,
            sleep=lambda _seconds: None,
        )
        scheduler.ensure_schema()
        market.replace_current_symbols(
            [{"symbol": "000001", "name": "旧目录", "source": "smoke"}]
        )
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "UPDATE market_symbols SET updated_at='2026-01-05T00:00:00+08:00'"
            )
        governance.upsert_trade_calendar([{
            "market": "CN",
            "trade_date": "2026-01-05",
            "is_open": True,
            "source": "smoke",
            "source_observed_at": "2026-01-05T10:00:00+08:00",
        }])
        governance.upsert_index_prices([{
            "index_symbol": "000300",
            "trade_date": "2026-01-05",
            "open": 3990,
            "high": 4000,
            "low": 3980,
            "close": 3995,
            "volume": 1,
            "amount": 1,
            "source": "smoke",
            "source_observed_at": "2026-01-05T10:00:00+08:00",
        }])
        service = DataCenterService(
            DataCenterStore(database), scheduler, governance,
            sync_worker_launcher=lambda _job_id: None,
        )
        app = SimpleApiApp(
            title="reference-refresh-smoke",
            routes=build_data_center_routes(service),
        )

        before = _row_counts(database)
        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/data-center/sync/reference-data/preview",
            body=json.dumps({"target_trade_date": "2026-01-09"}).encode("utf-8"),
        )
        assert status == 200
        preview = payload["result"]
        assert preview["status"] == "previewed"
        assert preview["writes"] == 0
        assert preview["current"]["status"] == "needs_refresh"
        assert _row_counts(database) == before
        assert provider.calls == []

        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/data-center/sync/reference-data/refresh",
            body=json.dumps({
                "target_trade_date": "2026-01-09",
                "preview_token": preview["preview_token"],
            }).encode("utf-8"),
        )
        assert status == 200
        refreshed = payload["result"]
        assert refreshed["status"] == "completed"
        assert refreshed["after"]["status"] == "ready"
        assert refreshed["after"]["calendar_latest_date"] == "2026-01-09"
        assert refreshed["after"]["latest_index_date"] == "2026-01-09"
        assert refreshed["writes"] == {
            "catalog_count": 1, "calendar_rows": 4, "index_rows": 1,
        }
        assert provider.calls == ["catalog", "calendar", "index"]

        governance.upsert_trade_calendar([{
            "market": "CN",
            "trade_date": "2026-01-12",
            "is_open": True,
            "source": "smoke-future-local-row",
            "source_observed_at": "2026-01-12T10:00:00+08:00",
        }])
        historical_status = scheduler.reference_data_status(target_date="2026-01-09")
        assert historical_status["latest_open_trade_date"] == "2026-01-09"
        assert historical_status["status"] == "ready"

        try:
            service.refresh_reference_data(
                target_trade_date="2026-01-09",
                preview_token=preview["preview_token"],
            )
        except ValueError as error:
            assert "preview is required" in str(error)
        else:
            raise AssertionError("reference preview tokens must be one-time")

        paths = {route.path for route in build_data_center_routes(service)}
        assert "/api/data-center/sync/reference-data/preview" in paths
        assert "/api/data-center/sync/reference-data/refresh" in paths

    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    script = (root / "web" / "data_center_stage_c.js").read_text(encoding="utf-8")
    assert 'id="dc-reference-preview"' in html
    assert 'id="dc-reference-refresh"' in html
    assert "previewReferenceRefresh" in script
    assert "refreshReferenceData" in script
    print("data-center reference refresh smoke test passed")


if __name__ == "__main__":
    main()
