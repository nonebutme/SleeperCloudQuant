"""Strategy Studio manifest payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StrategyManifestSaveRequest:
    strategy_id: str
    strategy_version: str
    name: str
    source_sha256: str
    dataset_requirements: list[dict[str, Any]] = field(default_factory=list)
    factor_ids: list[str] = field(default_factory=list)
    assets: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    portfolio: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    code: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyManifestResponse:
    manifest: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyManifestListResponse:
    manifests: list[dict[str, Any]] = field(default_factory=list)

