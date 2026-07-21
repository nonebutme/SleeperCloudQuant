"""Factor request and response payloads."""

from __future__ import annotations

from dataclasses import dataclass, field

from factor_lab.models import FactorDefinition, FactorRankingResult, FactorValue


@dataclass(frozen=True, slots=True)
class FactorValuesQuery:
    """Minimal request payload for one factor-values query."""

    factor_id: str
    symbol: str
    start_date: str | None = None
    end_date: str | None = None


@dataclass(frozen=True, slots=True)
class FactorValuesResponse:
    """Minimal response payload for one factor-values query."""

    factor_id: str
    symbol: str
    rows: list[FactorValue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FactorTopNQuery:
    """Minimal request payload for one factor top-n query."""

    factor_id: str
    trade_date: str
    start_date: str | None = None
    end_date: str | None = None
    limit: str | None = None
    descending: str | None = None


@dataclass(frozen=True, slots=True)
class FactorPoolMembersQuery:
    """Minimal request payload for one stock-pool member query."""

    index_code: str
    date: str | None = None


@dataclass(frozen=True, slots=True)
class FactorSummaryQuery:
    """Minimal request payload for one multi-factor snapshot query."""

    symbol: str
    trade_date: str
    start_date: str | None = None
    end_date: str | None = None
    factor_ids: str | None = None


@dataclass(frozen=True, slots=True)
class FactorCrossSectionSummaryQuery:
    """Minimal request payload for one stock-pool cross-section summary query."""

    index_code: str
    trade_date: str
    date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    factor_ids: str | None = None


@dataclass(frozen=True, slots=True)
class FactorTopNResponse:
    """Minimal response payload for one factor top-n query."""

    ranking: FactorRankingResult


@dataclass(frozen=True, slots=True)
class FactorDefinitionsResponse:
    """Minimal response payload for factor definition listing."""

    definitions: list[FactorDefinition] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FactorPoolMembersResponse:
    """Minimal response payload for one stock-pool member query."""

    index_code: str
    date: str | None = None
    symbols: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FactorSummaryResponse:
    """Minimal response payload for one multi-factor snapshot query."""

    symbol: str
    trade_date: str
    rows: list[FactorValue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FactorCrossSectionSummaryItem:
    """Minimal per-symbol payload for one stock-pool cross-section summary."""

    symbol: str
    rows: list[FactorValue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FactorCrossSectionSummaryResponse:
    """Minimal response payload for one stock-pool cross-section summary query."""

    index_code: str
    trade_date: str
    date: str | None = None
    summaries: list[FactorCrossSectionSummaryItem] = field(default_factory=list)
