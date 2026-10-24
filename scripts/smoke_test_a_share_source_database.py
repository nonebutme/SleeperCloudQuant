"""Immutable read-only smoke for the formal full-market A-share source."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.api.market import build_market_routes
    from app.runtime.demo_registry import FakeMarketDataRepository
    from app.runtime.http_adapter import dispatch_request
    from app.main import SimpleApiApp
    from app.services.market_data_service import MarketDataService
    from _formal_read_only_a_share import (
        ImmutableAShareMarketStore,
        resolve_formal_source_database_path,
    )

    store = ImmutableAShareMarketStore(resolve_formal_source_database_path())
    app = SimpleApiApp(
        title="SleeperCloudQuant immutable A-share source verification",
        routes=build_market_routes(
            MarketDataService(FakeMarketDataRepository(), a_share_repository=store)
        ),
    )
    status, payload = dispatch_request(
        app,
        method="GET",
        path="/api/market/a-share/overview",
    )
    overview = payload.get("overview", {})
    raw = overview.get("adjustments", {}).get("raw", {})
    if status != 200 or overview.get("status") != "ready":
        raise SystemExit("A-share source smoke failed: repository is not ready")
    if int(overview.get("current_symbol_count") or 0) < 5000:
        raise SystemExit("A-share source smoke failed: current symbol coverage is too small")
    if int(overview.get("history_symbol_count") or 0) < 5000:
        raise SystemExit("A-share source smoke failed: historical symbols are missing")
    if int(raw.get("row_count") or 0) < 10_000_000 or raw.get("min_date") != "2015-01-05":
        raise SystemExit("A-share source smoke failed: raw daily coverage is incomplete")
    if set(overview.get("adjustments", {})) != {"raw", "qfq", "hfq"}:
        raise SystemExit("A-share source smoke failed: adjustment coverage mismatch")

    if overview.get("source") != "canonical_a_share_sqlite":
        raise SystemExit("A-share source smoke failed: canonical source is unavailable")
    if overview.get("read_only") is not True or overview.get("query_only") is not True:
        raise SystemExit("A-share source smoke failed: immutable read-only mode is not enforced")
    for mode, item in overview["adjustments"].items():
        if item.get("quality_status") != "passed":
            raise SystemExit(f"A-share source smoke failed: {mode} quality is not passed")
        if float(item.get("fresh_coverage_pct") or 0) < 98:
            raise SystemExit(f"A-share source smoke failed: {mode} latest-day coverage is too small")
        if int(item.get("duplicate_row_count") or 0) != 0:
            raise SystemExit(f"A-share source smoke failed: {mode} duplicates remain")

    status, payload = dispatch_request(
        app,
        method="GET",
        path="/api/market/a-share/symbols",
        query_string="query=000001&limit=10",
    )
    catalog = payload.get("catalog", {})
    items = catalog.get("items", [])
    if status != 200 or catalog.get("read_only") is not True or not items or items[0].get("name") != "\u5e73\u5b89\u94f6\u884c":
        raise SystemExit("A-share source smoke failed: symbol catalog mismatch")

    latest_date = str(raw.get("max_date") or "")
    if not latest_date:
        raise SystemExit("A-share source smoke failed: latest raw trade date is missing")
    sample_start_date = (
        date.fromisoformat(latest_date) - timedelta(days=7)
    ).isoformat()
    status, payload = dispatch_request(
        app,
        method="GET",
        path="/api/market/a-share/daily",
        query_string=(
            "symbol=000001&adjustment=raw"
            f"&start_date={sample_start_date}&end_date={latest_date}&limit=10"
        ),
    )
    daily = payload.get("daily", {})
    rows = daily.get("rows", [])
    if status != 200 or not rows:
        raise SystemExit("A-share source smoke failed: real daily rows are missing")
    if daily.get("read_only") is not True or daily.get("query_only") is not True:
        raise SystemExit("A-share source smoke failed: repository write-mode mismatch")
    if rows[0].get("date") != latest_date or float(rows[0].get("close") or 0) <= 0:
        raise SystemExit("A-share source smoke failed: latest daily row mismatch")

    project_root = Path(__file__).resolve().parents[1]
    html = (project_root / "web" / "index.html").read_text(encoding="utf-8-sig")
    javascript = (project_root / "web" / "app.js").read_text(encoding="utf-8-sig")
    required_markers = (
        "a-share-overview",
        "a-share-symbol-form",
        "a-share-daily-form",
        "/api/market/a-share/daily",
    )
    if any(marker not in html + javascript for marker in required_markers):
        raise SystemExit("A-share source smoke failed: Web controls are incomplete")

    print(
        "A-share source smoke passed:",
        f"source={overview['source']}",
        f"current={overview['current_symbol_count']}",
        f"history={overview['history_symbol_count']}",
        f"raw_rows={raw['row_count']}",
        f"latest={latest_date}",
        f"coverage={raw.get('fresh_coverage_pct')}",
        f"quality={raw['quality_status']}",
        "connection=immutable-query-only",
    )


if __name__ == "__main__":
    main()
