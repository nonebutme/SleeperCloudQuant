"""Strategy Dataset API payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StrategyDatasetListQuery:
    status: str = ""
    layer_id: str = ""
    search: str = ""
    consumer_scope: str = ""


@dataclass(frozen=True, slots=True)
class StrategyDatasetListResponse:
    items: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyDatasetObjectResponse:
    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyDatasetValidationRequest:
    source_code: str = ""
    dataset_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StrategyDatasetPreviewRequest:
    symbol: str = "000001.XSHE"
    start_date: str = ""
    end_date: str = ""
    adjustment: str = "raw"
    limit: int = 100
