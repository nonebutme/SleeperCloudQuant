"""API smoke test for stage-78.2 scheduler controls."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path
from smoke_test_stage78_2_incremental_scheduler import (
    FakeProvider,
    _publish_initial,
    _seed_governance,
)


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.api import build_config_routes
    from app.main import SimpleApiApp
    from app.runtime import dispatch_request
    from app.services.config_center_service import ConfigCenterService
    from config_center import UnifiedConfigManager
    from data_platform.a_share_sync_scheduler import AShareSyncScheduler
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.a_share_market_store import AShareMarketStore

    with tempfile.TemporaryDirectory(prefix="scq-stage782-api-") as directory:
        root = Path(directory)
        database = root / "market.sqlite3"
        market = AShareMarketStore(database)
        governance = AShareGovernanceStore(database)
        market.ensure_schema()
        governance.ensure_schema()
        market.replace_current_symbols(
            [{"symbol": "000001", "name": "sample", "source": "smoke"}]
        )
        for adjustment in ("raw", "qfq", "hfq"):
            market.upsert_daily_prices(
                [{
                    "symbol": "000001",
                    "date": "2026-01-02",
                    "open": 10,
                    "high": 10.5,
                    "low": 9.5,
                    "close": 10.2,
                    "volume": 1000,
                    "amount": 10200,
                }],
                adjustment=adjustment,
                source="smoke",
            )
        _seed_governance(governance)
        _publish_initial(governance)
        scheduler = AShareSyncScheduler(
            database,
            market_store=market,
            governance_store=governance,
            provider=FakeProvider(),
            requests_per_minute=1_000_000,
            max_workers=3,
            retry_count=2,
            base_backoff_seconds=0,
            sleep=lambda _: None,
        )
        service = ConfigCenterService(
            UnifiedConfigManager(),
            draft_path=root / "draft.json",
            sync_task_path=root / "legacy-sync.json",
            a_share_scheduler=scheduler,
        )
        app = SimpleApiApp(
            title="stage78.2 scheduler api smoke",
            routes=build_config_routes(service),
        )

        status, payload = dispatch_request(
            app,
            method="GET",
            path="/api/config/a-share-scheduler/status",
        )
        _require(status == 200 and payload["result"]["status"] == "ready", "status endpoint failed")

        status, payload = _post(
            dispatch_request,
            app,
            "/api/config/a-share-scheduler/settings",
            {
                "enabled": False,
                "run_time": "18:15",
                "timezone_name": "Asia/Shanghai",
                "adjustments": ["raw", "qfq", "hfq"],
            },
        )
        _require(status == 200 and payload["result"]["enabled"] is False, "settings endpoint failed")

        status, payload = _post(
            dispatch_request,
            app,
            "/api/config/a-share-sync/jobs",
            {
                "target_trade_date": "2026-01-05",
                "symbols": ["000001"],
                "all_current": False,
                "adjustments": ["raw", "qfq", "hfq"],
                "run_now": True,
            },
        )
        job = payload["result"]
        _require(status == 200 and job["status"] == "published", "create/run endpoint failed")
        job_id = job["job_id"]

        status, payload = dispatch_request(
            app,
            method="GET",
            path=f"/api/config/a-share-sync/jobs/{job_id}",
        )
        _require(
            status == 200
            and payload["result"]["data_version_id"]
            and len(payload["result"]["items"]) == 3,
            "job detail endpoint failed",
        )

        status, payload = dispatch_request(
            app,
            method="GET",
            path="/api/config/a-share-sync/jobs",
        )
        _require(status == 200 and payload["jobs"][0]["job_id"] == job_id, "job list endpoint failed")

        status, payload = _post(
            dispatch_request,
            app,
            "/api/config/a-share-scheduler/recover",
            {},
        )
        _require(status == 200 and payload["result"]["status"] == "completed", "recovery endpoint failed")
        print(f"stage78.2 scheduler API smoke passed job={job_id}")


def _post(dispatch_request, app, path: str, payload: dict[str, object]):
    return dispatch_request(
        app,
        method="POST",
        path=path,
        body=json.dumps(payload).encode("utf-8"),
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"stage78.2 scheduler API smoke failed: {message}")


if __name__ == "__main__":
    main()
