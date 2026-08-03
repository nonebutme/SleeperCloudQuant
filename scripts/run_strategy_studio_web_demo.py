"""Serve the parallel Strategy Studio candidate without replacing the existing editor."""

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

    from app.runtime.http_adapter import DispatchError, dispatch_request
    from app.runtime.strategy_studio_app import build_strategy_studio_app

    web_root = (Path(__file__).resolve().parents[1] / "web").resolve()
    app = build_strategy_studio_app()

    class StrategyStudioHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._api("GET", parsed.path, parsed.query, None)
                return
            self._static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                self.send_error(501, "Unsupported method")
                return
            length = int(self.headers.get("Content-Length") or "0")
            self._api("POST", parsed.path, parsed.query, self.rfile.read(length) if length else b"")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return None

        def _api(self, method: str, path: str, query: str, body: bytes | None) -> None:
            try:
                status, payload = dispatch_request(app, method=method, path=path, query_string=query, body=body)
            except DispatchError as exc:
                status, payload = exc.status_code, {"detail": exc.message}
            except Exception as exc:  # pragma: no cover - HTTP boundary
                status, payload = 500, {"detail": str(exc)}
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _static(self, path: str) -> None:
            relative = path.lstrip("/") or "strategy-studio.html"
            target = (web_root / relative).resolve()
            if (web_root not in target.parents and target != web_root) or not target.is_file():
                self.send_error(404)
                return
            content = target.read_bytes()
            mime, _ = mimetypes.guess_type(target.name)
            if mime and (mime.startswith("text/") or mime in {"application/javascript", "application/json"}):
                mime = f"{mime}; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    port = int(os.environ.get("SCQ_STRATEGY_STUDIO_PORT", "8020"))
    server = ThreadingHTTPServer(("127.0.0.1", port), StrategyStudioHandler)
    print(f"strategy studio candidate listening on http://127.0.0.1:{port} routes={len(app.routes)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
