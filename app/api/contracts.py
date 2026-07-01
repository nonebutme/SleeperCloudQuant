from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    method: str
    path: str
    name: str
    handler: object
    request_model: type[Any] | None = None
