"""Canonical Strategy Manifest for the new strategy studio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.dataset.product_models import DatasetRequirement


MANIFEST_SECTIONS = (
    "assets",
    "datasets",
    "signals",
    "portfolio",
    "risk",
    "execution",
    "code",
    "validation",
)


@dataclass(frozen=True, slots=True)
class StrategyManifest:
    strategy_id: str
    strategy_version: str
    name: str
    source_sha256: str
    dataset_requirements: tuple[DatasetRequirement, ...] = ()
    factor_ids: tuple[str, ...] = ()
    assets: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    portfolio: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    code: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    execution_contract: str = "target-weights-v1"
    manifest_version: str = "v1"

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.strategy_id,
                self.strategy_version,
                self.name,
                self.source_sha256,
            )
        ):
            raise ValueError("strategy manifest identity fields must not be empty")
        dataset_ids = [item.dataset_id for item in self.dataset_requirements]
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError("strategy manifest dataset requirements must be unique")

    def section_names(self) -> tuple[str, ...]:
        return MANIFEST_SECTIONS

