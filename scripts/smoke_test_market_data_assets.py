"""Smoke test for stage 45 local market data asset governance API."""

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
    {"trade_date": "2020-10-01", "open_price": 100.0, "high_price": 101.0, "low_price": 99.5, "close_price": 100.8, "vol": 10000},
    {"trade_date": "2020-10-02", "open_price": 100.8, "high_price": 102.0, "low_price": 100.1, "close_price": 101.7, "vol": 10200},
]


class Stage45ProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if self.headers.get("Authorization") != "Bearer stage45-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/stage45/kline":
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
    server = HTTPServer(("127.0.0.1", 0), Stage45ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage45-secret"
    base_url = f"http://127.0.0.1:{server.server_port}"
    token = uuid.uuid4().hex[:8]
    symbol = f"STAGE45{token}.XSHE"
    endpoint_spec = {
        "price_history_path": "/stage45/kline",
        "price_history_rows_path": "data.items",
        "field_mapping": {"date": ["trade_date"], "open": ["open_price"], "high": ["high_price"], "low": ["low_price"], "close": ["close_price"], "volume": ["vol"]},
        "pagination": {"enabled": False, "max_pages": 1},
        "retry": {"max_attempts": 1},
    }
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        status, payload = _dispatch(app, "POST", "/api/config/runtime-draft", {"settings": {"market_provider": {"enabled": True, "provider_name": "stage45-assets-provider", "base_url": base_url, "timeout_seconds": 5, "endpoint_spec": endpoint_spec}}})
        if status != 200 or "stage45-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage45 smoke failed: config draft leaked secret")

        app = build_demo_app()
        status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-10-01", "end_date": "2020-10-02"})
        if status != 200 or payload.get("summary", {}).get("row_count") != 2:
            raise SystemExit("stage45 smoke failed: sync did not write expected rows")

        status, payload = _dispatch(app, "GET", "/api/market/local-price-bars/assets", query_string=f"symbol={symbol}&limit=10")
        assets_payload = payload.get("assets", {})
        assets = assets_payload.get("assets", [])
        if status != 200 or assets_payload.get("dataset") != "price_history" or assets_payload.get("asset_count") != 1:
            raise SystemExit("stage45 smoke failed: asset response envelope invalid")
        asset = assets[0] if assets else {}
        if asset.get("symbol") != symbol or asset.get("row_count") != 2:
            raise SystemExit("stage45 smoke failed: asset row summary invalid")
        if asset.get("quality_status") != "passed" or asset.get("missing_count") != 0 or asset.get("invalid_count") != 0:
            raise SystemExit("stage45 smoke failed: asset quality summary invalid")
        if asset.get("source_counts", {}).get("explicit_sync") != 2:
            raise SystemExit("stage45 smoke failed: asset source counts invalid")
        if not asset.get("data_version") or len(str(asset.get("data_version"))) != 16:
            raise SystemExit("stage45 smoke failed: asset data version invalid")
        manifest = assets_payload.get("manifest", {})
        if manifest.get("scope") != "local_price_bars" or "market_price_bars" not in str(manifest.get("storage")):
            raise SystemExit("stage45 smoke failed: asset manifest invalid")
        if "stage45-secret" in json.dumps(assets_payload, ensure_ascii=False):
            raise SystemExit("stage45 smoke failed: secret leaked")
        print("stage45 market data assets smoke test passed")
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
