"""HTTP runtime adapter for the minimal formal API shell."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.api import RouteDefinition
from app.main import SimpleApiApp


class DispatchError(Exception):
    """Raised when an incoming request cannot be dispatched."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message



def dispatch_request(
    app: SimpleApiApp,
    *,
    method: str,
    path: str,
    query_string: str = "",
    body: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    """Dispatch one request against the framework-agnostic app shell."""

    route, path_params = _match_route(app.routes, method=method, path=path)
    payload = _build_route_payload(route, query_string=query_string, body=body)
    try:
        if payload is None and path_params:
            result = route.handler(*path_params.values())
        elif payload is None:
            result = route.handler()
        else:
            result = route.handler(payload)
    except TypeError:
        result = route.handler(*path_params.values())
    if result is None:
        return 404, {"detail": "resource not found"}
    return 200, _to_jsonable(result)



def create_http_handler(app: SimpleApiApp) -> type[BaseHTTPRequestHandler]:
    """Create a stdlib request handler bound to the provided app shell."""

    class AppHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._handle_request("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle_request("POST")

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return None

        def _handle_request(self, method: str) -> None:
            parsed = urlparse(self.path)
            body = None
            if method == "POST":
                content_length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(content_length) if content_length > 0 else b""
            try:
                status_code, payload = dispatch_request(
                    app,
                    method=method,
                    path=parsed.path,
                    query_string=parsed.query,
                    body=body,
                )
            except DispatchError as exc:
                status_code = exc.status_code
                payload = {"detail": exc.message}
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return AppHandler



def create_http_server(
    app: SimpleApiApp,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> ThreadingHTTPServer:
    """Create a stdlib HTTP server for the provided app shell."""

    return ThreadingHTTPServer((host, port), create_http_handler(app))



def _match_route(
    routes: list[RouteDefinition],
    *,
    method: str,
    path: str,
) -> tuple[RouteDefinition, dict[str, str]]:
    for route in routes:
        if route.method.upper() != method.upper():
            continue
        matched, params = _match_path_pattern(route.path, path)
        if matched:
            return route, params
    raise DispatchError(404, f"no route for {method} {path}")



def _match_path_pattern(pattern: str, path: str) -> tuple[bool, dict[str, str]]:
    pattern_parts = [part for part in pattern.strip("/").split("/") if part]
    path_parts = [part for part in path.strip("/").split("/") if part]
    if len(pattern_parts) != len(path_parts):
        return False, {}
    params: dict[str, str] = {}
    for pattern_part, path_part in zip(pattern_parts, path_parts, strict=True):
        if pattern_part.startswith("{") and pattern_part.endswith("}"):
            params[pattern_part[1:-1]] = path_part
            continue
        if pattern_part != path_part:
            return False, {}
    return True, params



def _build_route_payload(
    route: RouteDefinition,
    *,
    query_string: str,
    body: bytes | None,
) -> Any:
    if route.request_model is None:
        return None
    if route.method.upper() == "GET":
        raw_query = {
            key: values[-1]
            for key, values in parse_qs(query_string, keep_blank_values=True).items()
        }
        return route.request_model(**raw_query)
    if route.method.upper() == "POST":
        if body is None:
            raise DispatchError(400, "missing request body")
        raw_body = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(raw_body, dict):
            raise DispatchError(400, "request body must be a JSON object")
        return route.request_model(**raw_body)
    return None



def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, SimpleNamespace):
        return _to_jsonable(vars(value))
    return value
