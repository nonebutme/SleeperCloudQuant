"""Run the formal local API shell and serve the web-app MVP on one origin."""

from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime import build_demo_app, dispatch_request
    from app.runtime.http_adapter import DispatchError

    web_root = Path(__file__).resolve().parents[1] / "web"
    resolved_web_root = web_root.resolve()
    app = build_demo_app()

    class AppHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api_request(method="GET", path=parsed.path, query=parsed.query, body=None)
                return
            self._handle_static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                content_length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(content_length) if content_length > 0 else b""
                self._handle_api_request(method="POST", path=parsed.path, query=parsed.query, body=body)
                return
            self.send_error(501, "Unsupported method")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return None

        def _handle_api_request(self, method: str, path: str, query: str, body: bytes | None) -> None:
            try:
                status_code, payload = dispatch_request(
                    app,
                    method=method,
                    path=path,
                    query_string=query,
                    body=body,
                )
            except DispatchError as exc:
                encoded = json.dumps({"detail": exc.message}, ensure_ascii=False).encode("utf-8")
                self.send_response(exc.status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            except Exception as exc:
                encoded = json.dumps({"detail": str(exc)}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return

            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _handle_static(self, path: str) -> None:
            relative_path = path.lstrip("/") or "index.html"
            target = (resolved_web_root / relative_path).resolve()
            if resolved_web_root not in target.parents and target != resolved_web_root:
                self.send_error(404)
                return
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                self.send_error(404)
                return
            content = target.read_bytes()
            mime_type, _ = mimetypes.guess_type(target.name)
            if mime_type and (mime_type.startswith("text/") or mime_type in {"application/javascript", "application/json"}):
                mime_type = f"{mime_type}; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", mime_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    route_names = [route.name for route in app.routes]
    has_ai = "ai_analyze_stock" in route_names
    has_config = "config_status" in route_names
    port = int(os.environ.get("SCQ_WEB_PORT", "8010"))
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"formal web demo listening on http://127.0.0.1:{port} routes={len(route_names)} ai={has_ai} config={has_config}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
