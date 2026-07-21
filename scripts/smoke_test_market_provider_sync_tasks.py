"""Smoke test for stage 30 market provider sync task queue."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from _project_bootstrap import ensure_project_root_on_sys_path

ROWS = [
    {"trade_date": "2020-06-01", "open_price": 50.0, "high_price": 51.0, "low_price": 49.5, "close_price": 50.8, "vol": 5000},
    {"trade_date": "2020-06-02", "open_price": 50.8, "high_price": 52.0, "low_price": 50.1, "close_price": 51.7, "vol": 5200},
]


class Stage30ProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if self.headers.get("Authorization") != "Bearer stage30-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/sync/kline":
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


def _dispatch(app, method: str, path: str, payload: dict[str, object] | None = None):
    from app.runtime import dispatch_request

    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
    return dispatch_request(app, method=method, path=path, body=body)


def main() -> None:
    ensure_project_root_on_sys_path()
    draft_path = Path("var/runtime/config_runtime_draft.json")
    original_draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else None
    sync_task_path = Path("var/runtime/market_provider_sync_tasks.json")
    original_sync_tasks = sync_task_path.read_text(encoding="utf-8") if sync_task_path.exists() else None
    server = HTTPServer(("127.0.0.1", 0), Stage30ProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage30-secret"
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        from app.runtime import build_demo_app

        app = build_demo_app()
        endpoint_spec = {
            "price_history_path": "/sync/kline",
            "price_history_rows_path": "payload.bars",
            "field_mapping": {"date": ["trade_date"], "open": ["open_price"], "high": ["high_price"], "low": ["low_price"], "close": ["close_price"], "volume": ["vol"]},
            "pagination": {"enabled": False, "max_pages": 1},
            "retry": {"max_attempts": 2},
        }
        status, payload = _dispatch(
            app,
            "POST",
            "/api/config/runtime-draft",
            {"settings": {"market_provider": {"enabled": True, "provider_name": "stage30-sync-provider", "base_url": base_url, "timeout_seconds": 5, "endpoint_spec": endpoint_spec}}},
        )
        if status != 200 or "stage30-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage30 smoke failed: config draft leaked secret")

        status, payload = _dispatch(
            app,
            "POST",
            "/api/config/market-provider/sync-tasks",
            {"symbols": ["000001.XSHE", "600000.XSHG"], "start_date": "2020-06-01", "end_date": "2020-06-02", "interval_seconds": 60},
        )
        task = payload.get("task", {})
        task_id = task.get("task_id")
        if status != 200 or not task_id or task.get("status") != "created":
            raise SystemExit("stage30 smoke failed: sync task was not created")
        if task.get("schedule", {}).get("mode") != "fixed_interval":
            raise SystemExit("stage30 smoke failed: interval schedule missing")

        app = build_demo_app()
        status, payload = _dispatch(app, "POST", f"/api/config/market-provider/sync-tasks/{task_id}/run")
        task = payload.get("task", {})
        if status != 200 or task.get("status") != "completed" or task.get("row_count") != 4:
            raise SystemExit("stage30 smoke failed: sync task did not complete")
        if task.get("cursor_by_symbol", {}).get("000001.XSHE") != "2020-06-02":
            raise SystemExit("stage30 smoke failed: cursor did not advance")
        if not task.get("checks", {}).get("cursor_advanced") or task.get("checks", {}).get("secret_leak_detected"):
            raise SystemExit("stage30 smoke failed: checks are invalid")
        serialized = json.dumps(task, ensure_ascii=False)
        if "stage30-secret" in serialized:
            raise SystemExit("stage30 smoke failed: sync task leaked secret")

        status, payload = _dispatch(app, "POST", f"/api/config/market-provider/sync-tasks/{task_id}/retry")
        retried = payload.get("task", {})
        if status != 200 or retried.get("retry_count") != 1:
            raise SystemExit("stage30 smoke failed: retry count not recorded")

        os.environ.pop("SCQ_MARKET_PROVIDER_API_KEY", None)
        status, payload = _dispatch(
            app,
            "POST",
            "/api/config/market-provider/sync-tasks",
            {"symbols": ["000001.XSHE"], "start_date": "2020-06-01", "end_date": "2020-06-02"},
        )
        skipped_id = payload.get("task", {}).get("task_id")
        status, payload = _dispatch(app, "POST", f"/api/config/market-provider/sync-tasks/{skipped_id}/run")
        skipped = payload.get("task", {})
        if status != 200 or skipped.get("status") not in {"skipped", "needs_attention"}:
            raise SystemExit("stage30 smoke failed: missing API key did not degrade safely")
        if skipped.get("cursor_by_symbol"):
            raise SystemExit("stage30 smoke failed: skipped task advanced cursor")

        status, payload = _dispatch(app, "GET", "/api/config/market-provider/sync-tasks")
        if status != 200 or len(payload.get("tasks", [])) < 2:
            raise SystemExit("stage30 smoke failed: task list missing entries")

        print("stage30 market provider sync task smoke test passed")
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