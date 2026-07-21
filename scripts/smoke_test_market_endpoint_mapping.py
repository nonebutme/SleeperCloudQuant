"""Smoke test for stage 28 market endpoint mapping, pagination, and sync trace."""

from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from _project_bootstrap import ensure_project_root_on_sys_path

PAGE_ROWS = {
    "": [
        {"trade_date": "2020-05-01", "open_price": 40.0, "high_price": 41.0, "low_price": 39.5, "close_price": 40.8, "vol": 4000},
        {"trade_date": "2020-05-02", "open_price": 40.8, "high_price": 42.0, "low_price": 40.2, "close_price": 41.6, "vol": 4200},
    ],
    "cursor-2": [
        {"trade_date": "2020-05-03", "open_price": 41.6, "high_price": 43.0, "low_price": 41.0, "close_price": 42.5, "vol": 4500},
    ],
}


class Stage28ProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if self.headers.get("Authorization") != "Bearer stage28-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/v1/kline":
            cursor = query.get("cursor", [""])[0]
            next_cursor = "cursor-2" if cursor == "" else ""
            self._send_json({"data": {"items": PAGE_ROWS.get(cursor, []), "next": next_cursor}})
            return
        if parsed.path == "/v1/calendar":
            self._send_json({"data": {"days": ["2020-05-01", "2020-05-02", "2020-05-03"]}})
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: dict[str, object], *, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    ensure_project_root_on_sys_path()

    server = HTTPServer(("127.0.0.1", 0), Stage28ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    token = uuid.uuid4().hex[:8]
    symbol = f"STAGE28{token}.XSHE"
    os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage28-secret"

    endpoint_spec = {
        "price_history_path": "/v1/kline",
        "price_history_rows_path": "data.items",
        "trading_calendar_path": "/v1/calendar",
        "trading_calendar_days_path": "data.days",
        "field_mapping": {
            "date": ["trade_date"],
            "open": ["open_price"],
            "high": ["high_price"],
            "low": ["low_price"],
            "close": ["close_price"],
            "volume": ["vol"],
        },
        "pagination": {
            "enabled": True,
            "page_param": "page",
            "page_size_param": "page_size",
            "page_size": 2,
            "next_cursor_path": "data.next",
            "next_cursor_param": "cursor",
            "max_pages": 3,
        },
        "retry": {"max_attempts": 2},
    }

    try:
        from app.runtime import build_demo_app, dispatch_request

        app = build_demo_app()
        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/config/runtime-draft",
            body=json.dumps(
                {
                    "settings": {
                        "market_provider": {
                            "enabled": True,
                            "provider_name": "stage28-paginated-provider",
                            "base_url": base_url,
                            "timeout_seconds": 5,
                            "endpoint_spec": endpoint_spec,
                        }
                    }
                }
            ).encode("utf-8"),
        )
        if status != 200 or "stage28-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage28 smoke failed: config draft leaked API key")

        app = build_demo_app()
        status, payload = dispatch_request(app, method="GET", path="/api/config/status")
        market_status = payload.get("status", {}).get("market_provider_status", {})
        if status != 200 or market_status.get("endpoint_spec", {}).get("price_history_rows_path") != "data.items":
            raise SystemExit("stage28 smoke failed: endpoint spec not visible in config status")

        status, payload = dispatch_request(
            app,
            method="GET",
            path="/api/market/price-history",
            query_string=f"symbol={symbol}&start_date=2020-05-01-{token}&end_date=2020-05-03-{token}",
        )
        rows = payload.get("rows", [])
        source_trace = payload.get("source_trace", {})
        provider_last_call = source_trace.get("primary", {}).get("last_call", {})
        if status != 200 or len(rows) != 3 or rows[0].get("open") != 40.0 or rows[-1].get("close") != 42.5:
            raise SystemExit("stage28 smoke failed: mapped paginated rows not returned")
        if provider_last_call.get("page_count") != 2 or provider_last_call.get("pagination_enabled") is not True:
            raise SystemExit("stage28 smoke failed: provider pagination trace missing")

        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/market/sync-price-history",
            body=json.dumps({"symbol": f"{symbol}SYNC", "start_date": f"2020-05-01-{token}", "end_date": f"2020-05-03-{token}"}).encode("utf-8"),
        )
        summary = payload.get("summary", {})
        sync_trace = summary.get("source_trace", {})
        if status != 200 or summary.get("row_count") != 3:
            raise SystemExit("stage28 smoke failed: sync summary row count invalid")
        if sync_trace.get("upstream", {}).get("last_call", {}).get("selected_source") != "primary":
            raise SystemExit("stage28 smoke failed: sync summary source trace missing primary selection")
        if "stage28-secret" in json.dumps({"status": market_status, "trace": source_trace, "summary": summary}, ensure_ascii=False):
            raise SystemExit("stage28 smoke failed: secret leaked in public payloads")

        print("stage28 market endpoint mapping and sync smoke test passed")
    finally:
        server.shutdown()
        os.environ.pop("SCQ_MARKET_PROVIDER_API_KEY", None)


if __name__ == "__main__":
    main()
