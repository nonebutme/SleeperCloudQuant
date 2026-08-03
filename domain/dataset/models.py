"""Versioned dataset contracts for local quant research.

These models are intentionally persistence-agnostic.  They establish the M0
contract without changing the existing data-center or backtest tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_DATASET_STATUSES = {"connected", "unavailable", "disabled"}
_VERSION_STATUSES = {"draft", "validated", "published", "retired"}
_POINT_IN_TIME_POLICIES = {"point_in_time", "as_of_trade_date", "not_applicable"}


@dataclass(frozen=True, slots=True)
class DatasetField:
    """One field in a dataset schema."""

    name: str
    data_type: str
    description: str = ""
    unit: str | None = None
    nullable: bool = True


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    """Stable identity and access contract for one governed dataset."""

    dataset_id: str
    name: str
    layer_id: str
    description: str = ""
    frequency: str = "daily"
    security_types: tuple[str, ...] = ()
    supported_adjustments: tuple[str, ...] = ()
    fields: tuple[DatasetField, ...] = ()
    source_id: str | None = None
    availability_status: str = "unavailable"
    point_in_time_policy: str = "not_applicable"
    license_note: str = ""
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be empty")
        if self.availability_status not in _DATASET_STATUSES:
            raise ValueError(f"unsupported dataset status: {self.availability_status}")
        if self.point_in_time_policy not in _POINT_IN_TIME_POLICIES:
            raise ValueError(f"unsupported point-in-time policy: {self.point_in_time_policy}")


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    """Immutable publication record for one dataset snapshot."""

    version_id: str
    dataset_id: str
    status: str
    coverage_start: str | None = None
    coverage_end: str | None = None
    symbol_count: int | None = None
    coverage_ratio: float | None = None
    quality_report_id: str | None = None
    source_run_id: str | None = None
    content_sha256: str | None = None
    published_at: str | None = None

    def __post_init__(self) -> None:
        if not self.version_id.strip() or not self.dataset_id.strip():
            raise ValueError("version_id and dataset_id must not be empty")
        if self.status not in _VERSION_STATUSES:
            raise ValueError(f"unsupported dataset version status: {self.status}")
        if self.symbol_count is not None and self.symbol_count < 0:
            raise ValueError("symbol_count must not be negative")
        if self.coverage_ratio is not None and not 0.0 <= self.coverage_ratio <= 1.0:
            raise ValueError("coverage_ratio must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class DatasetSubscription:
    """A consumer's frozen request for a dataset slice."""

    dataset_id: str
    version_id: str | None = None
    symbols: tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None
    fields: tuple[str, ...] = ()
    adjustment: str | None = None
    as_of_date: str | None = None
    minimum_history: int = 0
    missing_data_policy: str = "unavailable"
    consumer: str = ""

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be empty")
        if self.minimum_history < 0:
            raise ValueError("minimum_history must not be negative")


@dataclass(frozen=True, slots=True)
class BacktestInputBundle:
    """Reproducible set of all data and code bindings used by a backtest."""

    bundle_id: str
    subscriptions: tuple[DatasetSubscription, ...] = ()
    dataset_versions: tuple[DatasetVersion, ...] = ()
    strategy_id: str | None = None
    strategy_version: str | None = None
    strategy_source_sha256: str | None = None
    factor_bindings: tuple[dict[str, Any], ...] = ()
    universe_snapshot_id: str | None = None
    execution_contract: str = "target-weights-v1"
    bundle_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.bundle_id.strip():
            raise ValueError("bundle_id must not be empty")
        version_ids = {version.version_id for version in self.dataset_versions}
        for subscription in self.subscriptions:
            if subscription.version_id and subscription.version_id not in version_ids:
                raise ValueError(
                    f"subscription version is not bound in bundle: {subscription.version_id}"
                )

