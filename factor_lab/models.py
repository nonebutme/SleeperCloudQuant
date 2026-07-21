"""Minimal factor-lab domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FactorDefinition:
    """Metadata for one factor implementation."""

    factor_id: str
    name: str
    version: str = "v1"
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FactorValue:
    """One factor value for one symbol on one trade date."""

    factor_id: str
    symbol: str
    trade_date: str
    value: float


@dataclass(frozen=True, slots=True)
class FactorRunResult:
    """Minimal result summary for one factor-computation run."""

    factor_id: str
    symbol: str
    start_date: str | None
    end_date: str | None
    row_count: int
    rows: list[FactorValue] = field(default_factory=list)
    stored_at: str | None = None


@dataclass(frozen=True, slots=True)
class FactorRankingResult:
    """Minimal ranking read model for one factor on one trade date."""

    factor_id: str
    trade_date: str
    row_count: int
    rows: list[FactorValue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FactorPoolRunResult:
    """Minimal batch result for one factor run over a stock pool."""

    factor_id: str
    symbols: list[str] = field(default_factory=list)
    run_count: int = 0
    row_count: int = 0
    results: list[FactorRunResult] = field(default_factory=list)
