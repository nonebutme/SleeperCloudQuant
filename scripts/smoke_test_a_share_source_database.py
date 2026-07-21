"""Smoke test for the active full-market A-share SQLite repository."""

from __future__ import annotations

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request

    app = build_demo_app()
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

    is_canonical = overview.get("source") == "canonical_a_share_sqlite"
    if is_canonical:
        if overview.get("read_only") is not False:
            raise SystemExit("A-share source smoke failed: canonical repository mode mismatch")
        for mode, item in overview["adjustments"].items():
            if item.get("quality_status") != "passed":
                raise SystemExit(f"A-share source smoke failed: {mode} quality is not passed")
            if float(item.get("fresh_coverage_pct") or 0) < 98:
                raise SystemExit(f"A-share source smoke failed: {mode} latest-day coverage is too small")
            if int(item.get("duplicate_row_count") or 0) != 0:
                raise SystemExit(f"A-share source smoke failed: {mode} duplicates remain")
    elif overview.get("read_only") is not True:
        raise SystemExit("A-share source smoke failed: legacy repository is not read-only")

    status, payload = dispatch_request(
        app,
        method="GET",
        path="/api/market/a-share/symbols",
        query_string="query=000001&limit=10",
    )
    items = payload.get("catalog", {}).get("items", [])
    if status != 200 or not items or items[0].get("name") != "\u5e73\u5b89\u94f6\u884c":
        raise SystemExit("A-share source smoke failed: symbol catalog mismatch")

    query = (
        "symbol=000001&adjustment=raw&start_date=2026-07-13&end_date=2026-07-17&limit=10"
        if is_canonical
        else "symbol=000001&adjustment=raw&start_date=2026-03-30&end_date=2026-03-31&limit=10"
    )
    status, payload = dispatch_request(
        app,
        method="GET",
        path="/api/market/a-share/daily",
        query_string=query,
    )
    daily = payload.get("daily", {})
    rows = daily.get("rows", [])
    expected_latest = "2026-07-17" if is_canonical else "2026-03-31"
    if status != 200 or not rows:
        raise SystemExit("A-share source smoke failed: real daily rows are missing")
    if daily.get("read_only") is not (not is_canonical):
        raise SystemExit("A-share source smoke failed: repository write-mode mismatch")
    if rows[0].get("date") != expected_latest or float(rows[0].get("close") or 0) <= 0:
        raise SystemExit("A-share source smoke failed: latest daily row mismatch")

    html = open("web/index.html", "r", encoding="utf-8-sig").read()
    javascript = open("web/app.js", "r", encoding="utf-8-sig").read()
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
        f"latest={raw['max_date']}",
        f"coverage={raw.get('fresh_coverage_pct', 'legacy')}",
        f"quality={raw['quality_status']}",
    )


if __name__ == "__main__":
    main()
