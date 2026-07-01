"""Minimal runtime setting models for phase-1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DataSourceSettings:
    """Minimal data source settings required in phase-1."""

    name: str
    enabled: bool = True
    priority: int = 0
    config_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Minimal runtime settings bundle for phase-1."""

    backtest_profile_name: str = "default_a_share"
    data_sources: tuple[DataSourceSettings, ...] = ()
