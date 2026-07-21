"""Smoke test for stage 29 market provider preflight API."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from _project_bootstrap import ensure_project_root_on_sys_path

ROWS = [
    {"trade_date": "2020-06-01", "open_price": 50.0, "high_price": 51.0, "low_price": 49.5, "close_price": 50.8, "vol": 5000},
    {"trade_date": "2020-06-02", "open_price": 50.8, "high_price": 52.0, "low_price": 50.1, "close_price": 51.7, "vol": 5200},
]


class Stage29ProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parse_qs(parsed.query)
        if self.headers.get("Authorization") != "Bearer stage29-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/preflight/kline":
            self._send_json({"payload": {"bars": ROWS, "next": ""}})
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
    server = HTTPServer(("127.0.0.1", 0), Stage29ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage29-secret"
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        from app.runtime import build_demo_app, dispatch_request

        app = build_demo_app()
        endpoint_spec = {
            "price_history_path": "/preflight/kline",
            "price_history_rows_path": "payload.bars",
            "field_mapping": {"date": ["trade_date"], "open": ["open_price"], "high": ["high_price"], "low": ["low_price"], "close": ["close_price"], "volume": ["vol"]},
            "pagination": {"enabled": True, "page_param": "page", "page_size_param": "page_size", "page_size": 2, "next_cursor_path": "payload.next", "next_cursor_param": "cursor", "max_pages": 2},
            "retry": {"max_attempts": 2},
        }
        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/config/runtime-draft",
            body=json.dumps({"settings": {"market_provider": {"enabled": True, "provider_name": "stage29-preflight-provider", "base_url": base_url, "timeout_seconds": 5, "endpoint_spec": endpoint_spec}}}).encode("utf-8"),
        )
        if status != 200 or "stage29-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage29 smoke failed: config draft leaked secret")

        app = build_demo_app()
        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/config/market-provider/preflight",
            body=json.dumps({"symbol": "000001.XSHE", "start_date": "2020-06-01", "end_date": "2020-06-02"}).encode("utf-8"),
        )
        result = payload.get("result", {})
        provider_status = result.get("provider_status", {})
        checks = result.get("checks", {})
        if status != 200 or result.get("status") != "passed" or result.get("row_count") != 2:
            raise SystemExit("stage29 smoke failed: preflight did not pass")
        if not checks.get("required_fields_present") or checks.get("secret_leak_detected"):
            raise SystemExit("stage29 smoke failed: field coverage or secret check invalid")
        if provider_status.get("last_call", {}).get("path") != "/preflight/kline":
            raise SystemExit("stage29 smoke failed: preflight did not use configured path")
        if provider_status.get("last_call", {}).get("pagination_enabled") is not True:
            raise SystemExit("stage29 smoke failed: pagination trace missing")
        serialized = json.dumps(result, ensure_ascii=False)
        if "stage29-secret" in serialized:
            raise SystemExit("stage29 smoke failed: result leaked secret")

        print("stage29 market provider preflight smoke test passed")
    finally:
        server.shutdown()
        os.environ.pop("SCQ_MARKET_PROVIDER_API_KEY", None)


if __name__ == "__main__":
    main()
