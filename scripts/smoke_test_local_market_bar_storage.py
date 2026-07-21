"""Smoke test for stage 31 normalized local market bar storage and query API."""

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
    {"trade_date": "2020-07-01", "open_price": 70.0, "high_price": 71.0, "low_price": 69.5, "close_price": 70.8, "vol": 7000},
    {"trade_date": "2020-07-02", "open_price": 70.8, "high_price": 72.0, "low_price": 70.1, "close_price": 71.7, "vol": 7200},
    {"trade_date": "2020-07-03", "open_price": 71.7, "high_price": 73.0, "low_price": 71.0, "close_price": 72.5, "vol": 7500},
]


class Stage31ProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if self.headers.get("Authorization") != "Bearer stage31-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/stage31/kline":
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
    sync_task_path = Path("var/runtime/market_provider_sync_tasks.json")
    original_sync_tasks = sync_task_path.read_text(encoding="utf-8") if sync_task_path.exists() else None
    server = HTTPServer(("127.0.0.1", 0), Stage31ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage31-secret"
    base_url = f"http://127.0.0.1:{server.server_port}"
    token = uuid.uuid4().hex[:8]
    symbol = f"STAGE31{token}.XSHE"
    endpoint_spec = {
        "price_history_path": "/stage31/kline",
        "price_history_rows_path": "data.items",
        "field_mapping": {"date": ["trade_date"], "open": ["open_price"], "high": ["high_price"], "low": ["low_price"], "close": ["close_price"], "volume": ["vol"]},
        "pagination": {"enabled": False, "max_pages": 1},
        "retry": {"max_attempts": 1},
    }
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        status, payload = _dispatch(
            app,
            "POST",
            "/api/config/runtime-draft",
            {"settings": {"market_provider": {"enabled": True, "provider_name": "stage31-local-storage-provider", "base_url": base_url, "timeout_seconds": 5, "endpoint_spec": endpoint_spec}}},
        )
        if status != 200 or "stage31-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage31 smoke failed: config draft leaked secret")

        app = build_demo_app()
        status, payload = _dispatch(app, "POST", "/api/market/sync-price-history", {"symbol": symbol, "start_date": "2020-07-01", "end_date": "2020-07-03"})
        summary = payload.get("summary", {})
        if status != 200 or summary.get("row_count") != 3 or summary.get("stored_bar_count") not in {None, 3}:
            raise SystemExit("stage31 smoke failed: explicit sync did not return expected rows")

        status, payload = _dispatch(app, "GET", "/api/market/local-price-bars", query_string=f"symbol={symbol}&start_date=2020-07-02&end_date=2020-07-03")
        rows = payload.get("rows", [])
        storage_status = payload.get("storage_status", {})
        if status != 200 or len(rows) != 2 or rows[0].get("date") != "2020-07-02" or rows[-1].get("close") != 72.5:
            raise SystemExit("stage31 smoke failed: local bar range query invalid")
        if int(storage_status.get("row_count") or 0) < 3 or storage_status.get("min_date") != "2020-07-01":
            raise SystemExit("stage31 smoke failed: local bar status invalid")

        task_symbol = f"{symbol}TASK"
        status, payload = _dispatch(app, "POST", "/api/config/market-provider/sync-tasks", {"symbols": [task_symbol], "start_date": "2020-07-01", "end_date": "2020-07-03"})
        task_id = payload.get("task", {}).get("task_id")
        app = build_demo_app()
        status, payload = _dispatch(app, "POST", f"/api/config/market-provider/sync-tasks/{task_id}/run")
        if status != 200 or payload.get("task", {}).get("status") != "completed":
            raise SystemExit("stage31 smoke failed: sync task did not complete")
        status, payload = _dispatch(app, "GET", "/api/market/local-price-bars", query_string=f"symbol={task_symbol}&start_date=2020-07-01&end_date=2020-07-03")
        if status != 200 or len(payload.get("rows", [])) != 3:
            raise SystemExit("stage31 smoke failed: sync task rows were not written to local bar storage")

        if "stage31-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage31 smoke failed: secret leaked in local storage payload")
        print("stage31 local market bar storage smoke test passed")
    finally:
        server.shutdown()
        os.environ.pop("SCQ_MARKET_PROVIDER_API_KEY", None)
        if original_draft is None:
            if draft_path.exists():
                draft_path.unlink()
        else:
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text(original_draft, encoding="utf-8")
        if original_sync_tasks is None:
            if sync_task_path.exists():
                sync_task_path.unlink()
        else:
            sync_task_path.parent.mkdir(parents=True, exist_ok=True)
            sync_task_path.write_text(original_sync_tasks, encoding="utf-8")


if __name__ == "__main__":
    main()