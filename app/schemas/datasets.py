"""Read-only dataset-product API payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DatasetProductListQuery:
    status: str = ""
    layer_id: str = ""
    search: str = ""


@dataclass(frozen=True, slots=True)
class DatasetProductListResponse:
    items: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DatasetProductResponse:
    product: dict[str, Any] = field(default_factory=dict)

