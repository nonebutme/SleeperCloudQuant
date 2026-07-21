"""Smoke test for stage 32 local market data quality checks and gap repair."""

from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from _project_bootstrap import ensure_project_root_on_sys_path

MODE = "gap"
GAP_ROWS = [
    {"trade_date": "2020-08-01", "open_price": 80.0, "high_price": 81.0, "low_price": 79.5, "close_price": 80.8, "vol": 8000},
    {"trade_date": "2020-08-03", "open_price": 80.8, "high_price": 82.0, "low_price": 80.1, "close_price": 81.7, "vol": 8200},
]
FULL_ROWS = [
    {"trade_date": "2020-08-01", "open_price": 80.0, "high_price": 81.0, "low_price": 79.5, "close_price": 80.8, "vol": 8000},
    {"trade_date": "2020-08-02", "open_price": 80.8, "high_price": 81.4, "low_price": 80.2, "close_price": 81.1, "vol": 8100},
    {"trade_date": "2020-08-03", "open_price": 81.1, "high_price": 82.0, "low_price": 80.1, "close_price": 81.7, "vol": 8200},
]
BAD_ROWS = [
    {"trade_date": "2020-08-04", "open_price": 10.0, "high_price": 9.0, "low_price": 11.0, "close_price": 10.5, "vol": -1},
]


class Stage32ProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if self.headers.get("Authorization") != "Bearer stage32-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/stage32/kline":
            rows = BAD_ROWS if MODE == "bad" else (FULL_ROWS if MODE == "full" else GAP_ROWS)
            self._send_json({"data": {"items": rows}})
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
    global MODE
    ensure_project_root_on_sys_path()
    draft_path = Path("var/runtime/config_runtime_draft.json")
    original_draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else None
    server = HTTPServer(("127.0.0.1", 0), Stage32ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage32-secret"
    base_url = f"http://127.0.0.1:{server.server_port}"
    token = uuid.uuid4().hex[:8]
    symbol = f"STAGE32{token}.XSHE"
    bad_symbol = f"STAGE32BAD{token}.XSHE"
    endpoint_spec = {
        "price_history_path": "/stage32/kline",
        "price_history_rows_path": "data.items",
        "field_mapping": {"date": ["trade_date"], "open": ["open_price"], "high": ["high_price"], "low": ["low_price"], "close": ["close_price"], "volume": ["vol"]},
        "pagination": {"enabled": False, "max_pages": 1},
        "retry": {"max_attempts": 1},
    }
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        status, payload = _dispatch(app, "POST", "/api/config/runtime-draft", {"settings": {"market_provider": {"enabled": True, "provider_name": "stage32-quality-provider", "base_url": base_url, "timeout_seconds": 5, "endpoint_spec": endpoint_spec}}})
        if status != 200 or "stage32-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage32 smoke failed: config draft leaked secret")

        app = build_demo_app()
        MODE = "gap"
        status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-08-01", "end_date": "2020-08-03"})
        if status != 200 or payload.get("summary", {}).get("row_count") != 2:
            raise SystemExit("stage32 smoke failed: initial gap sync invalid")
        status, payload = _dispatch(app, "GET", "/api/market/local-price-bars/quality", query_string=f"symbol={symbol}&start_date=2020-08-01&end_date=2020-08-03")
        report = payload.get("report", {})
        if status != 200 or report.get("status") != "needs_attention" or report.get("missing_dates") != ["2020-08-02"]:
            raise SystemExit("stage32 smoke failed: quality report did not detect gap")

        MODE = "full"
        status, payload = _dispatch(app, "POST", "/api/market/local-price-bars/repair-gaps", {"symbol": symbol, "start_date": "2020-08-01", "end_date": "2020-08-03"})
        result = payload.get("result", {})
        if status != 200 or result.get("repair_count") != 1 or result.get("after", {}).get("status") != "passed":
            raise SystemExit("stage32 smoke failed: gap repair did not pass")

        MODE = "bad"
        status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": bad_symbol, "start_date": "2020-08-04", "end_date": "2020-08-04"})
        if status != 200:
            raise SystemExit("stage32 smoke failed: bad row sync failed")
        status, payload = _dispatch(app, "GET", "/api/market/local-price-bars/quality", query_string=f"symbol={bad_symbol}&start_date=2020-08-04&end_date=2020-08-04")
        bad_report = payload.get("report", {})
        reasons = bad_report.get("invalid_rows", [{}])[0].get("reasons", []) if bad_report.get("invalid_rows") else []
        if status != 200 or bad_report.get("invalid_count") != 1 or "high_below_low" not in reasons or "negative_volume" not in reasons:
            raise SystemExit("stage32 smoke failed: invalid OHLCV row not detected")
        if "stage32-secret" in json.dumps({"report": report, "result": result, "bad": bad_report}, ensure_ascii=False):
            raise SystemExit("stage32 smoke failed: secret leaked")
        print("stage32 market data quality smoke test passed")
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