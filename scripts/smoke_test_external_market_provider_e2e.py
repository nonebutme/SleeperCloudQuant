"""Smoke test for stage 26 external market provider end-to-end flow."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlparse

from _project_bootstrap import ensure_project_root_on_sys_path

MOCK_ROWS = [
    {"date": "2020-01-02", "open": 20.0, "high": 21.0, "low": 19.5, "close": 20.5, "volume": 10000},
    {"date": "2020-01-03", "open": 20.5, "high": 22.0, "low": 20.2, "close": 21.8, "volume": 12000},
    {"date": "2020-01-06", "open": 21.8, "high": 23.2, "low": 21.5, "close": 22.9, "volume": 14000},
    {"date": "2020-01-07", "open": 22.9, "high": 24.0, "low": 22.4, "close": 23.7, "volume": 16000},
    {"date": "2020-01-08", "open": 23.7, "high": 24.5, "low": 23.0, "close": 24.1, "volume": 18000},
    {"date": "2020-01-09", "open": 24.1, "high": 25.0, "low": 23.8, "close": 24.7, "volume": 20000},
]


class MockMarketProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if self.headers.get("Authorization") != "Bearer stage26-secret":
            self._send_json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/price-history":
            symbol = query.get("symbol", [""])[0]
            self._send_json({"provider": "stage26-mock-provider", "symbol": symbol, "rows": MOCK_ROWS})
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
    os.environ["SCQ_MARKET_PROVIDER_API_KEY"] = "stage26-secret"

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
                            "provider_name": "stage26-mock-provider",
                            "base_url": base_url,
                            "timeout_seconds": 5,
                        }
                    }
                }
            ).encode("utf-8"),
        )
        if status != 200 or "stage26-secret" in json.dumps(payload, ensure_ascii=False):
            raise SystemExit("stage26 smoke failed: config save leaked API key")

        app = build_demo_app()
        status, payload = dispatch_request(app, method="GET", path="/api/config/status")
        market_status = payload.get("status", {}).get("market_provider_status", {})
        if status != 200 or market_status.get("status") != "configured" or not market_status.get("enabled"):
            raise SystemExit("stage26 smoke failed: provider status not configured")
        if not market_status.get("api_key_configured"):
            raise SystemExit("stage26 smoke failed: env API key not detected")

        status, payload = dispatch_request(
            app,
            method="GET",
            path="/api/market/price-history",
            query_string="symbol=000001.XSHE&start_date=2020-01-02&end_date=2020-01-09",
        )
        rows = payload.get("rows", [])
        if status != 200 or len(rows) != len(MOCK_ROWS) or rows[0].get("open") != 20.0:
            raise SystemExit("stage26 smoke failed: market API did not use external mock rows")

        run_id = "stage26-external-provider-e2e-smoke"
        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/backtest/run-once",
            body=json.dumps(
                {
                    "run_id": run_id,
                    "strategy_name": "moving_average_strategy",
                    "strategy_id": "moving_average_strategy",
                    "strategy_version": "v1",
                    "symbol": "000001.XSHE",
                    "benchmark": "000300.XSHG",
                    "start_date": "2020-01-02",
                    "end_date": "2020-01-09",
                    "parameters": {"short_window": 2, "long_window": 3, "position_size": 1.0},
                    "extra_config": {"rqalpha_local": {"benchmark_alignment": "same_symbol_buy_hold"}},
                }
            ).encode("utf-8"),
        )
        result = payload.get("result", {})
        if status != 200 or result.get("status") != "completed" or "benchmark_return" not in result.get("metrics", {}):
            raise SystemExit("stage26 smoke failed: backtest did not complete on external mock rows")

        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/ai/workflow/run",
            body=json.dumps({"symbol": "000001.XSHE", "analysis_date": "2020-01-09", "report_id": run_id}).encode("utf-8"),
        )
        workflow = payload.get("workflow", {})
        if status != 200 or workflow.get("report_id") != run_id:
            raise SystemExit("stage26 smoke failed: AI workflow bind failed")

        status, payload = dispatch_request(
            app,
            method="POST",
            path=f"/api/reporting/run-detail/{quote(run_id)}/report-package",
            body=json.dumps({"symbol": "000001.XSHE", "workflow_id": workflow.get("workflow_id"), "title": "Stage 26 external provider package"}).encode("utf-8"),
        )
        package = payload.get("package", {})
        manifest_text = json.dumps(package.get("manifest", {}), ensure_ascii=False)
        if status != 200 or "external_market_provider" not in manifest_text:
            raise SystemExit("stage26 smoke failed: report package manifest missing external provider trace")
        if "stage26-secret" in json.dumps(package, ensure_ascii=False):
            raise SystemExit("stage26 smoke failed: report package leaked API key")

        print("stage26 external market provider e2e smoke test passed")
    finally:
        server.shutdown()
        os.environ.pop("SCQ_MARKET_PROVIDER_API_KEY", None)


if __name__ == "__main__":
    main()
