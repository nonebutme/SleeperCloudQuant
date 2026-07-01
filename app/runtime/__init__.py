"""Runtime-layer public exports with lazy loading to avoid import cycles."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "build_demo_app",
    "build_demo_service_registry",
    "create_http_handler",
    "create_http_server",
    "dispatch_request",
    "SqliteRuntimeStore",
]


def __getattr__(name: str) -> Any:
    if name in {"build_demo_app", "build_demo_service_registry"}:
        module = import_module("app.runtime.demo_registry")
        return getattr(module, name)
    if name in {"create_http_handler", "create_http_server", "dispatch_request"}:
        module = import_module("app.runtime.http_adapter")
        return getattr(module, name)
    if name == "SqliteRuntimeStore":
        module = import_module("app.runtime.sqlite_runtime_store")
        return getattr(module, name)
    raise AttributeError(f"module 'app.runtime' has no attribute {name!r}")
