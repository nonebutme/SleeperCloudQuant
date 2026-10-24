"""Isolated smoke for the explicit demo-only governed OHLCV fixture."""

from __future__ import annotations

from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from _project_bootstrap import ensure_project_root_on_sys_path


@contextmanager
def _environment(updates: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _paths(root: Path, name: str) -> dict[str, str | None]:
    area = root / name
    return {
        "SCQ_A_SHARE_CANONICAL_DB_PATH": str((area / "market.sqlite3").resolve()),
        "SCQ_A_SHARE_DB_PATH": str((area / "missing-legacy.sqlite3").resolve()),
        "SCQ_LEGACY_MARKET_DB_PATH": str((area / "missing-cache.sqlite3").resolve()),
        "SCQ_BACKTEST_RUNTIME_DB_PATH": str((area / "runtime.sqlite3").resolve()),
        "SCQ_AKSHARE_PROXY": None,
    }


def main() -> None:
    project_root = ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request
    from app.runtime.demo_registry import _seed_demo_governed_market_data
    from data_platform import AShareGovernanceStore, AShareMarketStore

    temp_parent = Path(project_root) / "tmp"
    temp_parent.mkdir(parents=True, exist_ok=True)
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="demo-governed-seed-", dir=temp_parent) as raw_root:
        root = Path(raw_root).resolve()
        os.chdir(root)
        try:
            disabled_paths = _paths(root, "disabled")
            with _environment({**disabled_paths, "SCQ_ENABLE_DEMO_SEED": None}):
                build_demo_app()
                disabled_market = AShareMarketStore(disabled_paths["SCQ_A_SHARE_CANONICAL_DB_PATH"])
                disabled_governance = AShareGovernanceStore(disabled_paths["SCQ_A_SHARE_CANONICAL_DB_PATH"])
                if disabled_market.has_daily_data():
                    raise SystemExit("demo governed seed smoke failed: disabled seed wrote market rows")
                if disabled_governance.fetch_current_published_data_version().get("status") != "not_found":
                    raise SystemExit("demo governed seed smoke failed: disabled seed published a version")

            ungoverned_paths = _paths(root, "ungoverned")
            with _environment({**ungoverned_paths, "SCQ_ENABLE_DEMO_SEED": "1"}):
                ungoverned_market = AShareMarketStore(
                    ungoverned_paths["SCQ_A_SHARE_CANONICAL_DB_PATH"]
                )
                ungoverned_governance = AShareGovernanceStore(
                    ungoverned_paths["SCQ_A_SHARE_CANONICAL_DB_PATH"]
                )
                ungoverned_governance.ensure_schema()
                ungoverned_market.upsert_daily_prices(
                    [
                        {
                            "symbol": "000001.XSHE",
                            "date": "2020-01-02",
                            "open": 10.0,
                            "high": 10.2,
                            "low": 9.9,
                            "close": 10.1,
                            "volume": 1000.0,
                        }
                    ],
                    adjustment="raw",
                    source="unknown-user-data",
                )
                try:
                    _seed_demo_governed_market_data(
                        ungoverned_market,
                        ungoverned_governance,
                    )
                except RuntimeError as error:
                    if "refuses to label" not in str(error):
                        raise
                else:
                    raise SystemExit(
                        "demo governed seed smoke failed: existing ungoverned data was relabeled"
                    )
                if (
                    ungoverned_governance.fetch_current_published_data_version().get("status")
                    != "not_found"
                ):
                    raise SystemExit(
                        "demo governed seed smoke failed: fail-closed path published a version"
                    )

            enabled_paths = _paths(root, "enabled")
            with _environment({**enabled_paths, "SCQ_ENABLE_DEMO_SEED": "1"}):
                app = build_demo_app()
                market = AShareMarketStore(enabled_paths["SCQ_A_SHARE_CANONICAL_DB_PATH"])
                governance = AShareGovernanceStore(enabled_paths["SCQ_A_SHARE_CANONICAL_DB_PATH"])
                first = governance.fetch_current_published_data_version()
                raw_member = next(
                    (
                        item for item in first.get("members") or []
                        if item.get("dataset") == "market_daily_prices"
                        and item.get("adjustment") == "raw"
                    ),
                    {},
                )
                if (
                    first.get("status") != "published"
                    or first.get("quality_report_id") != "scq-demo-governed-market-v1-quality"
                    or raw_member.get("quality_status") != "passed"
                    or int(raw_member.get("symbol_count") or 0) != 3
                    or raw_member.get("min_date") != "2020-01-01"
                    or raw_member.get("max_date") != "2020-12-31"
                ):
                    raise SystemExit("demo governed seed smoke failed: published manifest mismatch")
                first_identity = {
                    "data_version_id": first.get("data_version_id"),
                    "published_at": first.get("published_at"),
                    "manifest_hash": first.get("manifest_hash"),
                    "row_count": raw_member.get("row_count"),
                    "content_hash": raw_member.get("content_hash"),
                }

                build_demo_app()
                second = governance.fetch_current_published_data_version()
                second_member = next(
                    item for item in second.get("members") or []
                    if item.get("dataset") == "market_daily_prices"
                    and item.get("adjustment") == "raw"
                )
                second_identity = {
                    "data_version_id": second.get("data_version_id"),
                    "published_at": second.get("published_at"),
                    "manifest_hash": second.get("manifest_hash"),
                    "row_count": second_member.get("row_count"),
                    "content_hash": second_member.get("content_hash"),
                }
                if second_identity != first_identity:
                    raise SystemExit("demo governed seed smoke failed: repeated build was not idempotent")

                request = {
                    "run_id": "demo-governed-seed-smoke-run",
                    "strategy_name": "moving_average_strategy",
                    "strategy_id": "moving_average_strategy",
                    "strategy_version": "v1",
                    "symbol": "000001.XSHE",
                    "benchmark": "000300.XSHG",
                    "start_date": "2020-01-02",
                    "end_date": "2020-06-30",
                    "parameters": {"short_window": 3, "long_window": 5, "position_size": 1.0},
                    "extra_config": {"runtime_mode": "local_sqlite_backtest"},
                }
                status, payload = dispatch_request(
                    app,
                    method="POST",
                    path="/api/backtest/run-once",
                    body=json.dumps(request).encode("utf-8"),
                )
                if status != 200 or payload.get("result", {}).get("status") != "completed":
                    raise SystemExit("demo governed seed smoke failed: governed backtest did not complete")
                status, payload = dispatch_request(
                    app,
                    method="GET",
                    path="/api/backtest/results/demo-governed-seed-smoke-run/panel",
                )
                panel = payload.get("result") or {}
                trace = panel.get("data_asset_trace") or {}
                if (
                    status != 200
                    or trace.get("status") != "bound"
                    or (trace.get("asset") or {}).get("data_version") != first.get("data_version_id")
                ):
                    raise SystemExit("demo governed seed smoke failed: backtest trace was not governed")

                with closing(
                    sqlite3.connect(enabled_paths["SCQ_A_SHARE_CANONICAL_DB_PATH"])
                ) as connection:
                    connection.execute(
                        """
                        UPDATE market_daily_prices
                        SET close = close + 1
                        WHERE rowid = (
                            SELECT rowid
                            FROM market_daily_prices
                            WHERE adjustment = 'raw'
                            ORDER BY symbol, trade_date
                            LIMIT 1
                        )
                        """
                    )
                    connection.commit()
                try:
                    _seed_demo_governed_market_data(market, governance)
                except RuntimeError as error:
                    if "does not match its published physical rows" not in str(error):
                        raise
                else:
                    raise SystemExit(
                        "demo governed seed smoke failed: same-shape OHLCV tampering was accepted"
                    )
        finally:
            os.chdir(original_cwd)

    print("demo governed seed smoke passed")


if __name__ == "__main__":
    main()
