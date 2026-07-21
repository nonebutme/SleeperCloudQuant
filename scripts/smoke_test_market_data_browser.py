"""Smoke test for stage 33 local market data browser API."""

from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from _project_bootstrap import ensure_project_root_on_sys_path

ROWS = [
    {"trade_date": "2020-09-01", "open_price": 90.0, "high_price": 91.0, "low_price": 89.5, "close_price": 90.8, "vol": 9000},
    {"trade_date": "2020-09-02", "open_price": 90.8, "high_price": 92.0, "low_price": 90.1, "close_price": 91.7, "vol": 9200},
]


class Stage33ProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if self.headers.get("Authorization") != "Bearer stage33-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/stage33/kline":
            self._send_json({"data": {"items": ROWS}})
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


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None, query_string: str = ""):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    return dispatch_request(app, method=method, path=path, query_string=query_string, body=body)


def main() -> None:
    ensure_project_root_on_sys_path()
    draft_path = Path("var/runtime/config_runtime_draft.json")
    original_draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else None
    server = HTTPServer(("127.0.0.1", 0), Stage33ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage33-secret"
    base_url = f"http://127.0.0.1:{server.server_port}"
    token = uuid.uuid4().hex[:8]
    symbol_a = f"STAGE33A{token}.XSHE"
    symbol_b = f"STAGE33B{token}.XSHE"
    endpoint_spec = {
        "price_history_path": "/stage33/kline",
        "price_history_rows_path": "data.items",
        "field_mapping": {"date": ["trade_date"], "open": ["open_price"], "high": ["high_price"], "low": ["low_price"], "close": ["close_price"], "volume": ["vol"]},
        "pagination": {"enabled": False, "max_pages": 1},
        "retry": {"max_attempts": 1},
    }
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        status, payload = _dispatch(app, "POST", "/api/config/runtime-draft", {"settings": {"market_provider": {"enabled": True, "provider_name": "stage33-browser-provider", "base_url": base_url, "timeout_seconds": 5, "endpoint_spec": endpoint_spec}}})
        if status != 200 or "stage33-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage33 smoke failed: config draft leaked secret")
        app = build_demo_app()
        for symbol in (symbol_a, symbol_b):
            status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-09-01", "end_date": "2020-09-02"})
            if status != 200 or payload.get("summary", {}).get("row_count") != 2:
                raise SystemExit("stage33 smoke failed: sync did not write browser rows")
        status, payload = _dispatch(app, "GET", "/api/market/data-browser", query_string=f"symbol={symbol_a}&start_date=2020-09-01&end_date=2020-09-02&limit=20")
        browser = payload.get("browser", {})
        symbols = {item.get("symbol") for item in browser.get("symbols", [])}
        if status != 200 or browser.get("selected_symbol") != symbol_a:
            raise SystemExit("stage33 smoke failed: browser selected symbol invalid")
        if symbol_a not in symbols or symbol_b not in symbols:
            raise SystemExit("stage33 smoke failed: browser symbols missing synced symbols")
        if len(browser.get("bars", [])) != 2 or browser.get("quality", {}).get("status") != "passed":
            raise SystemExit("stage33 smoke failed: browser bars or quality invalid")
        if not browser.get("sync_runs"):
            raise SystemExit("stage33 smoke failed: browser sync history missing")
        if "stage33-secret" in json.dumps(browser, ensure_ascii=False):
            raise SystemExit("stage33 smoke failed: browser leaked secret")
        print("stage33 market data browser smoke test passed")
    finally:
        server.shutdown()
        os.environ.pop("SCQ_MARKET_PROVIDER_API_KEY", None)
        if original_draft is None:
            if draft_path.exists():
                draft_path.unlink()
        else:
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text(original_draft, encoding="utf-8")


if __name__ == "__main__":
    main()