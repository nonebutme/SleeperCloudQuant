"""Smoke test for the stdlib HTTP adapter."""

from __future__ import annotations

import io
import json

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.runtime import build_demo_app, create_http_handler, dispatch_request
    from app.runtime.database_paths import backtest_runtime_database_path
    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore

    app = build_demo_app()
    handler_class = create_http_handler(app)

    class _SmokeHandlerContext:
        def __init__(self, path: str) -> None:
            self.path = path
            self.headers = {"Content-Length": "0"}
            self.rfile = io.BytesIO(b"")
            self.wfile = io.BytesIO()
            self.sent_status: int | None = None
            self.sent_headers: list[tuple[str, str]] = []
            self.ended = False

        def send_response(self, status_code: int) -> None:
            self.sent_status = status_code

        def send_header(self, name: str, value: str) -> None:
            self.sent_headers.append((name, value))

        def end_headers(self) -> None:
            self.ended = True

    def _handle_get(path: str):
        context = _SmokeHandlerContext(path)
        handler_class._handle_request(context, "GET")
        return context.sent_status, json.loads(context.wfile.getvalue().decode("utf-8"))

    def _handle_post(path: str, body: bytes):
        context = _SmokeHandlerContext(path)
        context.headers["Content-Length"] = str(len(body))
        context.rfile = io.BytesIO(body)
        handler_class._handle_request(context, "POST")
        return context.sent_status, json.loads(context.wfile.getvalue().decode("utf-8"))
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/definitions")
    if status_code != 200 or len(payload.get("definitions", [])) != 7:
        raise SystemExit("formal HTTP adapter smoke test failed: factor definitions dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/pool-members", query_string="index_code=000300.XSHG")
    if status_code != 200 or payload.get("symbols", []) != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: default factor pool-members dispatch mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/pool-members", query_string="index_code=000300.XSHG&date=2020-01-02")
    if status_code != 200 or payload.get("symbols", []) != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: factor pool-members dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/pool-members", query_string="index_code=000300.XSHG&date=2020-01-01")
    if status_code != 200 or payload.get("symbols", []) != ["000001.XSHE"]:
        raise SystemExit("formal HTTP adapter smoke test failed: dated factor pool-members dispatch mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/pool-members", query_string="index_code=000300.XSHG&date=2020-01-03")
    if status_code != 200 or payload.get("symbols", []) != ["600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: later factor pool-members dispatch mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/pool-members", query_string="index_code=UNKNOWN.XSHG")
    if status_code != 200 or payload.get("symbols", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown default factor pool-members dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/pool-members", query_string="index_code=UNKNOWN.XSHG&date=2020-01-02")
    if status_code != 200 or payload.get("symbols", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown factor pool-members dispatch should be empty")
    status_code, payload = _handle_get("/api/factors/summary?trade_date=2020-01-02")
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: missing required summary query should return HTTP 400")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or len(payload.get("rows", [])) != 2:
        raise SystemExit("formal HTTP adapter smoke test failed: factor summary dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=close_to_ma2_bias")
    if status_code != 200 or len(payload.get("rows", [])) != 1 or payload.get("rows", [])[0].get("factor_id") != "close_to_ma2_bias":
        raise SystemExit("formal HTTP adapter smoke test failed: filtered factor summary dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-02&factor_ids=unknown_factor")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: default-scope unknown factor summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=unknown_factor")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown factor summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=UNKNOWN.XSHG&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=unknown_factor")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown symbol and unknown factor summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=UNKNOWN.XSHG&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown symbol summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-01&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: empty trade-date summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-01&start_date=2020-01-01&end_date=2020-01-02&factor_ids=close_to_ma2_bias")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: filtered empty trade-date summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=")
    if status_code != 200 or len(payload.get("rows", [])) != 2:
        raise SystemExit("formal HTTP adapter smoke test failed: blank factor_ids summary should fall back to all factors")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=,,close_to_ma2_bias,,")
    if status_code != 200 or len(payload.get("rows", [])) != 1 or payload.get("rows", [])[0].get("factor_id") != "close_to_ma2_bias":
        raise SystemExit("formal HTTP adapter smoke test failed: comma factor_ids summary parse mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"] or any(len(item.get("rows", [])) != 2 for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: default factor cross-section summary dispatch mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-02&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: factor cross-section summary dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-01&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE"] or any(len(item.get("rows", [])) != 2 for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: dated factor cross-section summary dispatch mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-03&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["600000.XSHG"] or any(len(item.get("rows", [])) != 2 for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: later factor cross-section summary dispatch mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-02&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=close_to_close_return_1d")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"] or any(len(item.get("rows", [])) != 1 or item.get("rows", [])[0].get("factor_id") != "close_to_close_return_1d" for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: filtered factor cross-section summary dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-02&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=unknown_factor")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"] or any(item.get("rows", []) for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown factor cross-section summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-03&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=unknown_factor")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["600000.XSHG"] or any(item.get("rows", []) for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: later unknown factor cross-section summary dispatch should preserve symbols and return empty rows")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-02&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"] or any(len(item.get("rows", [])) != 2 for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: blank factor_ids cross-section should fall back to all factors")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-02&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&factor_ids=,,close_to_close_return_1d,,")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"] or any(len(item.get("rows", [])) != 1 or item.get("rows", [])[0].get("factor_id") != "close_to_close_return_1d" for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: comma factor_ids cross-section parse mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-02&trade_date=2020-01-01&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"] or any(item.get("rows", []) for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: empty trade-date cross-section summary dispatch should preserve symbols and return empty rows")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&date=2020-01-02&trade_date=2020-01-01&start_date=2020-01-01&end_date=2020-01-02&factor_ids=close_to_close_return_1d")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"] or any(item.get("rows", []) for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: filtered empty trade-date cross-section summary dispatch should preserve symbols and return empty rows")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=UNKNOWN.XSHG&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or payload.get("summaries", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown default pool cross-section summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=UNKNOWN.XSHG&date=2020-01-02&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or payload.get("summaries", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown pool cross-section summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/values", query_string="factor_id=close_to_close_return_1d&symbol=000001.XSHE")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: default-scope factor values dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/values", query_string="factor_id=unknown_factor&symbol=000001.XSHE")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: default-scope unknown factor values dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/values", query_string="factor_id=close_to_close_return_1d&symbol=000001.XSHE&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or len(payload.get("rows", [])) != 1 or payload.get("rows", [])[0].get("trade_date") != "2020-01-02":
        raise SystemExit("formal HTTP adapter smoke test failed: factor values dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/values", query_string="factor_id=close_to_close_return_1d&symbol=000001.XSHE&start_date=2020-01-02&end_date=2020-01-02")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unmatched scope factor values dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/values", query_string="factor_id=unknown_factor&symbol=000001.XSHE&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown factor values dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/values", query_string="factor_id=unknown_factor&symbol=UNKNOWN.XSHG&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown symbol and unknown factor values dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/values", query_string="factor_id=close_to_close_return_1d&symbol=UNKNOWN.XSHG&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown symbol factor values dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/values", query_string="factor_id=close_to_close_return_1d&symbol=UNKNOWN.XSHG")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown symbol default-scope factor values dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal HTTP adapter smoke test failed: default top-n dispatch mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=&descending=")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal HTTP adapter smoke test failed: empty-parse top-n dispatch mismatch")
    status_code, payload = _handle_get("/api/factors/top-n?factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=abc&descending=true")
    if status_code != 400 or payload.get("detail") != "limit must be an integer":
        raise SystemExit("formal HTTP adapter smoke test failed: non-numeric limit should return HTTP 400")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=2&descending=false")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: false descending parse mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=2&descending=0")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: zero descending parse mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=2&descending=no")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: no descending parse mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/summary", query_string="symbol=000001.XSHE&trade_date=2020-01-02")
    if status_code != 200 or payload.get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: default-scope summary dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/cross-section-summary", query_string="index_code=000300.XSHG&trade_date=2020-01-02")
    if status_code != 200 or [item.get("symbol") for item in payload.get("summaries", [])] != ["000001.XSHE", "600000.XSHG"] or any(item.get("rows", []) for item in payload.get("summaries", [])):
        raise SystemExit("formal HTTP adapter smoke test failed: default-scope cross-section summary dispatch should preserve symbols and return empty rows")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=1&descending=true")
    if status_code != 200 or payload.get("ranking", {}).get("row_count") != 1:
        raise SystemExit("formal HTTP adapter smoke test failed: factor top-n dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=2&descending=true")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal HTTP adapter smoke test failed: descending top-n dispatch order mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=2&descending=false")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: ascending top-n dispatch order mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=0&descending=true")
    if status_code != 200 or payload.get("ranking", {}).get("row_count") != 1 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: zero-limit top-n dispatch clamp mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=tie_rank_factor&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=2&descending=true")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: tie descending top-n dispatch symbol order mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=tie_rank_factor&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=2&descending=false")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["000001.XSHE", "600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: tie ascending top-n dispatch symbol order mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-02&end_date=2020-01-02&limit=5&descending=true")
    if status_code != 200 or payload.get("ranking", {}).get("row_count") != 0 or payload.get("ranking", {}).get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unmatched scope top-n dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=99&descending=true")
    if status_code != 200 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["600000.XSHG", "000001.XSHE"]:
        raise SystemExit("formal HTTP adapter smoke test failed: large-limit top-n dispatch mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=-3&descending=true")
    if status_code != 200 or payload.get("ranking", {}).get("row_count") != 1 or [item.get("symbol") for item in payload.get("ranking", {}).get("rows", [])] != ["600000.XSHG"]:
        raise SystemExit("formal HTTP adapter smoke test failed: negative-limit top-n dispatch clamp mismatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=unknown_factor&trade_date=2020-01-02&start_date=2020-01-01&end_date=2020-01-02&limit=5&descending=true")
    if status_code != 200 or payload.get("ranking", {}).get("row_count") != 0 or payload.get("ranking", {}).get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown factor top-n dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/factors/top-n", query_string="factor_id=close_to_ma2_bias&trade_date=2020-01-03&start_date=2020-01-01&end_date=2020-01-02&limit=5&descending=true")
    if status_code != 200 or payload.get("ranking", {}).get("row_count") != 0 or payload.get("ranking", {}).get("rows", []):
        raise SystemExit("formal HTTP adapter smoke test failed: unknown trade-date top-n dispatch should be empty")
    status_code, payload = dispatch_request(app, method="GET", path="/api/market/price-history", query_string="symbol=000001.XSHE&start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or len(payload.get("rows", [])) != 2:
        raise SystemExit("formal HTTP adapter smoke test failed: price-history dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/market/trading-calendar", query_string="start_date=2020-01-01&end_date=2020-01-02")
    if status_code != 200 or len(payload.get("days", [])) < 2:
        raise SystemExit("formal HTTP adapter smoke test failed: trading-calendar dispatch")
    status_code, payload = dispatch_request(app, method="POST", path="/api/market/sync-price-history", body=json.dumps({"symbol": "000001.XSHE", "start_date": "2020-01-01", "end_date": "2020-01-02"}).encode("utf-8"))
    if status_code != 200 or payload.get("summary", {}).get("row_count") != 2:
        raise SystemExit("formal HTTP adapter smoke test failed: price sync dispatch")
    status_code, payload = _handle_post("/api/market/sync-price-history", b"{")
    if status_code != 400 or payload.get("detail") != "request body must be valid JSON":
        raise SystemExit("formal HTTP adapter smoke test failed: invalid JSON body should return HTTP 400")
    status_code, payload = _handle_post("/api/market/sync-price-history", json.dumps(["not-an-object"]).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "request body must be a JSON object":
        raise SystemExit("formal HTTP adapter smoke test failed: non-object JSON body should return HTTP 400")
    status_code, payload = _handle_post("/api/market/sync-trading-calendar", json.dumps({"start_date": "2020-01-01"}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: missing required POST field should return HTTP 400")
    status_code, payload = dispatch_request(app, method="POST", path="/api/market/sync-trading-calendar", body=json.dumps({"start_date": "2020-01-01", "end_date": "2020-01-03"}).encode("utf-8"))
    if status_code != 200 or payload.get("summary", {}).get("row_count") != 3:
        raise SystemExit("formal HTTP adapter smoke test failed: calendar sync dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/market/sync-status/price_history")
    if status_code != 200 or not payload.get("status", {}).get("cache_status"):
        raise SystemExit("formal HTTP adapter smoke test failed: sync-status dispatch")
    status_code, payload = dispatch_request(app, method="POST", path="/api/backtest/run-once", body=json.dumps({"run_id": "http-adapter-run-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}).encode("utf-8"))
    if status_code != 200 or payload.get("result", {}).get("status") != "completed":
        raise SystemExit("formal HTTP adapter smoke test failed: backtest dispatch")
    status_code, payload = _handle_post("/api/backtest/run-once", json.dumps({"run_id": "http-adapter-run-003", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01"}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: backtest missing required POST field should return HTTP 400")
    status_code, payload = dispatch_request(app, method="POST", path="/api/backtest/run-batch", body=json.dumps({"experiment_id": "http-batch-001", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-002", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}]}).encode("utf-8"))
    if status_code != 200 or payload.get("summary", {}).get("status") != "completed":
        raise SystemExit("formal HTTP adapter smoke test failed: batch dispatch")
    if payload.get("summary", {}).get("successful_run_ids") != ["http-adapter-run-002"]:
        raise SystemExit("formal HTTP adapter smoke test failed: batch summary successful_run_ids mismatch")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-empty-002", "profile": "default_a_share", "runs": []}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: empty backtest batch should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-duplicate-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-duplicate", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}, {"run_id": "http-adapter-run-duplicate", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: duplicate backtest batch run_id should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-benchmark-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-benchmark-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}, {"run_id": "http-adapter-run-benchmark-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000905.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: inconsistent backtest batch benchmark should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-strategy-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-strategy-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}, {"run_id": "http-adapter-run-strategy-002", "strategy_name": "mean_reversion_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31"}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: inconsistent backtest batch strategy_name should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-frequency-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-frequency-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "frequency": "1d"}, {"run_id": "http-adapter-run-frequency-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "frequency": "1m"}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: inconsistent backtest batch frequency should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-initial-cash-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-initial-cash-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000}, {"run_id": "http-adapter-run-initial-cash-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 2000000}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: inconsistent backtest batch initial_cash should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-start-date-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-start-date-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000}, {"run_id": "http-adapter-run-start-date-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-02-01", "end_date": "2020-12-31", "initial_cash": 1000000}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: inconsistent backtest batch start_date should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-end-date-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-end-date-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000}, {"run_id": "http-adapter-run-end-date-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2021-12-31", "initial_cash": 1000000}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: inconsistent backtest batch end_date should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-parameters-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-parameters-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000, "parameters": {"window": 5}}, {"run_id": "http-adapter-run-parameters-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000, "parameters": {"window": 10}}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: inconsistent backtest batch parameters should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-extra-config-002", "profile": "default_a_share", "runs": [{"run_id": "http-adapter-run-extra-config-001", "strategy_name": "moving_average_strategy", "symbol": "000001.XSHE", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000, "parameters": {"window": 5}, "extra_config": {"slippage": 0.001}}, {"run_id": "http-adapter-run-extra-config-002", "strategy_name": "moving_average_strategy", "symbol": "600000.XSHG", "benchmark": "000300.XSHG", "start_date": "2020-01-01", "end_date": "2020-12-31", "initial_cash": 1000000, "parameters": {"window": 5}, "extra_config": {"slippage": 0.002}}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: inconsistent backtest batch extra_config should return HTTP 400")
    status_code, payload = _handle_post("/api/backtest/run-batch", json.dumps({"experiment_id": "http-batch-002", "profile": "default_a_share", "runs": [{}]}).encode("utf-8"))
    if status_code != 400 or payload.get("detail") != "invalid request parameters":
        raise SystemExit("formal HTTP adapter smoke test failed: backtest batch missing required POST field should return HTTP 400")
    status_code, payload = dispatch_request(app, method="GET", path="/api/reporting/run-detail/http-adapter-run-001")
    if status_code != 200 or not payload.get("detail", {}).get("metrics"):
        raise SystemExit("formal HTTP adapter smoke test failed: run-detail dispatch")
    status_code, payload = dispatch_request(app, method="POST", path="/api/ai/workflow/run", body=json.dumps({"symbol": "000001.XSHE", "analysis_date": "2020-01-02", "max_debate_rounds": 2}).encode("utf-8"))
    if status_code != 200 or payload.get("workflow", {}).get("status") != "completed":
        raise SystemExit("formal HTTP adapter smoke test failed: AI workflow seed dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/reporting/run-detail/phase1-demo-run-001/ai-workflow", query_string="symbol=000001.XSHE")
    if status_code != 200 or not payload.get("replay", {}).get("linked") or payload.get("replay", {}).get("portfolio_decision", {}).get("action") != "watchlist_only":
        raise SystemExit("formal HTTP adapter smoke test failed: reporting AI workflow replay dispatch")
    status_code, payload = dispatch_request(app, method="POST", path="/api/reporting/run-detail/phase1-demo-run-001/report-package", body=json.dumps({"symbol": "000001.XSHE", "title": "HTTP smoke research package"}).encode("utf-8"))
    package = payload.get("package", {})
    if status_code != 200 or package.get("run_id") != "phase1-demo-run-001" or not package.get("snapshot_id") or not package.get("workflow_id"):
        raise SystemExit("formal HTTP adapter smoke test failed: report package create dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/reporting/run-detail/phase1-demo-run-001/report-packages")
    if status_code != 200 or not payload.get("packages") or payload.get("packages", [])[0].get("package_id") != package.get("package_id"):
        raise SystemExit("formal HTTP adapter smoke test failed: report package list dispatch")
    status_code, payload = dispatch_request(app, method="GET", path=f"/api/reporting/report-packages/{package.get('package_id')}")
    if status_code != 200 or payload.get("package", {}).get("workflow_id") != package.get("workflow_id"):
        raise SystemExit("formal HTTP adapter smoke test failed: report package detail dispatch")
    status_code, payload = dispatch_request(app, method="GET", path=f"/api/reporting/report-packages/{package.get('package_id')}/export", query_string="format=html")
    if status_code != 200 or payload.get("export", {}).get("format") != "html" or "<!doctype html>" not in payload.get("export", {}).get("content", ""):
        raise SystemExit("formal HTTP adapter smoke test failed: report package HTML export dispatch")
    status_code, payload = dispatch_request(app, method="GET", path=f"/api/reporting/report-packages/{package.get('package_id')}/export", query_string="format=json")
    if status_code != 200 or payload.get("export", {}).get("format") != "json" or package.get("workflow_id") not in payload.get("export", {}).get("content", ""):
        raise SystemExit("formal HTTP adapter smoke test failed: report package JSON export dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/reporting/run-detail/http-adapter-missing-run-001")
    if status_code != 404 or payload.get("detail") != "resource not found":
        raise SystemExit("formal HTTP adapter smoke test failed: missing run-detail should return HTTP 404")
    status_code, payload = dispatch_request(app, method="GET", path="/api/reporting/batch-summary/http-batch-001")
    if status_code != 200 or not payload.get("summary", {}).get("rows"):
        raise SystemExit("formal HTTP adapter smoke test failed: batch-summary dispatch")
    status_code, payload = dispatch_request(app, method="GET", path="/api/reporting/batch-summary/http-missing-batch-001")
    if status_code != 404 or payload.get("detail") != "resource not found":
        raise SystemExit("formal HTTP adapter smoke test failed: missing batch-summary should return HTTP 404")
    SqliteRuntimeStore(backtest_runtime_database_path()).upsert_research_run(
        run_id="http-batch-failure-001",
        strategy_name="default_a_share",
        status="partial_failed",
        started_at="2020-01-01T09:30:00+08:00",
        finished_at="2020-01-01T09:35:00+08:00",
        parameters={
            "profile": "default_a_share",
            "request_count": 2,
            "success_count": 0,
            "failure_count": 2,
            "run_ids": [],
            "failures": [
                {"run_id": "http-failed-run-001", "failure_type": "runtime_error", "failure_stage": "run_once", "failure_code": "BACKTEST_RUN_ONCE_RUNTIME_ERROR"},
                {"run_id": "http-failed-run-002", "failure_type": "unexpected_status", "failure_stage": "result_status_check", "failure_code": "BACKTEST_UNEXPECTED_RESULT_STATUS"},
            ],
        },
    )
    status_code, payload = dispatch_request(app, method="GET", path="/api/reporting/batch-summary/http-batch-failure-001")
    if status_code != 200 or payload.get("summary", {}).get("failure_type_counts") != {"runtime_error": 1, "unexpected_status": 1}:
        raise SystemExit("formal HTTP adapter smoke test failed: batch-summary should expose failure_type_counts")
    if payload.get("summary", {}).get("failure_stage_counts") != {"result_status_check": 1, "run_once": 1}:
        raise SystemExit("formal HTTP adapter smoke test failed: batch-summary should expose failure_stage_counts")
    if payload.get("summary", {}).get("failure_code_counts") != {"BACKTEST_RUN_ONCE_RUNTIME_ERROR": 1, "BACKTEST_UNEXPECTED_RESULT_STATUS": 1}:
        raise SystemExit("formal HTTP adapter smoke test failed: batch-summary should expose failure_code_counts")

    from app.runtime import http_adapter as http_adapter_module

    original_dispatch = http_adapter_module.dispatch_request
    handler_class = http_adapter_module.create_http_handler(app)

    class _FakeHandlerContext:
        def __init__(self) -> None:
            self.path = "/api/factors/top-n?factor_id=close_to_ma2_bias"
            self.headers = {"Content-Length": "0"}
            self.rfile = io.BytesIO(b"")
            self.wfile = io.BytesIO()
            self.sent_status: int | None = None
            self.sent_headers: list[tuple[str, str]] = []
            self.ended = False

        def send_response(self, status_code: int) -> None:
            self.sent_status = status_code

        def send_header(self, name: str, value: str) -> None:
            self.sent_headers.append((name, value))

        def end_headers(self) -> None:
            self.ended = True

    try:
        def _raise_dispatch_error(*args, **kwargs):
            raise http_adapter_module.DispatchError(422, "bad query")

        http_adapter_module.dispatch_request = _raise_dispatch_error
        dispatch_error_context = _FakeHandlerContext()
        handler_class._handle_request(dispatch_error_context, "GET")
        if dispatch_error_context.sent_status != 422 or b'bad query' not in dispatch_error_context.wfile.getvalue():
            raise SystemExit("formal HTTP adapter smoke test failed: handler should translate DispatchError into HTTP response")

        def _raise_value_error(*args, **kwargs):
            raise ValueError("bad limit")

        http_adapter_module.dispatch_request = _raise_value_error
        value_error_context = _FakeHandlerContext()
        try:
            handler_class._handle_request(value_error_context, "GET")
        except ValueError:
            pass
        else:
            raise SystemExit("formal HTTP adapter smoke test failed: handler should propagate non-DispatchError exceptions")
        if value_error_context.sent_status is not None or value_error_context.wfile.getvalue():
            raise SystemExit("formal HTTP adapter smoke test failed: propagated non-DispatchError should not write HTTP response")
    finally:
        http_adapter_module.dispatch_request = original_dispatch

    print("formal HTTP adapter smoke test passed")


if __name__ == "__main__":
    main()



