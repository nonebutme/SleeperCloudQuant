"""Smoke test for stage 27 external market provider observability and fallback trace."""

from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from _project_bootstrap import ensure_project_root_on_sys_path

MOCK_ROWS = [
    {"date": "2020-03-02", "open": 31.0, "high": 32.0, "low": 30.5, "close": 31.6, "volume": 31000},
    {"date": "2020-03-03", "open": 31.6, "high": 33.2, "low": 31.2, "close": 32.8, "volume": 32800},
    {"date": "2020-03-04", "open": 32.8, "high": 34.0, "low": 32.1, "close": 33.4, "volume": 33400},
]


class MockMarketProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if self.headers.get("Authorization") != "Bearer stage27-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/price-history":
            self._send_json({"provider": "stage27-observability-provider", "symbol": query.get("symbol", [""])[0], "rows": MOCK_ROWS})
            return
        if parsed.path == "/trading-calendar":
            self._send_json({"days": [row["date"] for row in MOCK_ROWS]})
            return
        if parsed.path == "/index-components":
            self._send_json({"components": ["000001.XSHE"]})
            return
        if parsed.path == "/financial-indicators":
            self._send_json({"rows": []})
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

    server = HTTPServer(("127.0.0.1", 0), MockMarketProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        from app.runtime import build_demo_app, dispatch_request
        from data_platform.providers.external_market_provider import ExternalMarketProviderRepository

        unique_token = uuid.uuid4().hex[:8]
        success_symbol = f"STAGE27SUCCESS{unique_token}.XSHE"
        failure_symbol = f"STAGE27FAIL{unique_token}.XSHG"

        direct_provider = ExternalMarketProviderRepository(
            base_url=base_url,
            provider_name="stage27-observability-provider",
            enabled=True,
            api_key="wrong-secret",
            timeout_seconds=2,
        )
        direct_rows = direct_provider.fetch_price_history("000001.XSHE", "2020-03-02", "2020-03-04")
        direct_status = direct_provider.provider_status()
        direct_last_call = direct_status.get("last_call", {})
        if direct_rows or direct_last_call.get("status") != "http_error" or direct_last_call.get("status_code") != 401:
            raise SystemExit("stage27 smoke failed: direct provider 401 was not observable")
        if "wrong-secret" in json.dumps(direct_status, ensure_ascii=False):
            raise SystemExit("stage27 smoke failed: provider status leaked API key")

        os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage27-secret"
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
                            "provider_name": "stage27-observability-provider",
                            "base_url": base_url,
                            "timeout_seconds": 5,
                        }
                    }
                }
            ).encode("utf-8"),
        )
        if status != 200 or "stage27-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage27 smoke failed: config save leaked API key")

        app = build_demo_app()
        status, payload = dispatch_request(
            app,
            method="GET",
            path="/api/market/price-history",
            query_string=f"symbol={success_symbol}&start_date=2020-03-02-{unique_token}&end_date=2020-03-04-{unique_token}",
        )
        rows = payload.get("rows", [])
        source_trace = payload.get("source_trace", {})
        upstream_trace = source_trace.get("upstream", {})
        upstream_last_call = upstream_trace.get("last_call", {})
        provider_last_call = source_trace.get("primary", {}).get("last_call", {})
        if status != 200 or len(rows) != len(MOCK_ROWS) or rows[0].get("open") != 31.0:
            raise SystemExit("stage27 smoke failed: successful external provider rows not returned")
        if source_trace.get("last_call", {}).get("selected_source") != "upstream" or upstream_last_call.get("selected_source") != "primary":
            raise SystemExit("stage27 smoke failed: successful source trace did not select upstream/primary")
        if provider_last_call.get("status") != "success" or provider_last_call.get("row_count") != len(MOCK_ROWS):
            raise SystemExit("stage27 smoke failed: provider success last_call missing row count")

        os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "wrong-secret"
        app = build_demo_app()
        status, payload = dispatch_request(
            app,
            method="GET",
            path="/api/market/price-history",
            query_string=f"symbol={failure_symbol}&start_date=2020-03-05-{unique_token}&end_date=2020-03-06-{unique_token}",
        )
        rows = payload.get("rows", [])
        source_trace = payload.get("source_trace", {})
        upstream_trace = source_trace.get("upstream", {})
        provider_last_call = source_trace.get("primary", {}).get("last_call", {})
        serialized_trace = json.dumps(source_trace, ensure_ascii=False)
        if status != 200 or not rows:
            raise SystemExit("stage27 smoke failed: fallback rows not returned after provider failure")
        if upstream_trace.get("last_call", {}).get("selected_source") != "fallback":
            raise SystemExit("stage27 smoke failed: upstream trace did not select fallback after provider failure")
        if provider_last_call.get("status") != "http_error" or provider_last_call.get("status_code") != 401:
            raise SystemExit("stage27 smoke failed: provider HTTP error not exposed in source trace")
        if "wrong-secret" in serialized_trace or "stage27-secret" in serialized_trace:
            raise SystemExit("stage27 smoke failed: source trace leaked API key")

        print("stage27 external market observability smoke test passed")
    finally:
        server.shutdown()
        os.environ.pop("SCQ_MARKET_PROVIDER_API_KEY", None)


if __name__ == "__main__":
    main()
