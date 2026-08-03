"""Canonical dataset-product contracts for governed local research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PRODUCT_STATUSES = {"connected", "unavailable", "disabled"}
RELEASE_STATUSES = {"draft", "validated", "published", "retired"}
POINT_IN_TIME_POLICIES = {"point_in_time", "as_of_trade_date", "not_applicable"}
MISSING_DATA_POLICIES = {"unavailable", "skip", "forward_fill", "fail"}


@dataclass(frozen=True, slots=True)
class DatasetSchemaField:
    name: str
    data_type: str
    description: str = ""
    unit: str | None = None
    nullable: bool = True
    available_at_field: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.data_type.strip():
            raise ValueError("dataset field name and data_type must not be empty")


@dataclass(frozen=True, slots=True)
class DatasetProduct:
    """Stable research-facing product backed by the data-center catalog."""

    dataset_id: str
    name: str
    layer_id: str
    description: str = ""
    producer_type: str = "external_source"
    producer_id: str = ""
    market_scope: tuple[str, ...] = ()
    asset_types: tuple[str, ...] = ()
    frequencies: tuple[str, ...] = ()
    primary_key: tuple[str, ...] = ()
    event_time_field: str | None = None
    availability_time_field: str | None = None
    supported_adjustments: tuple[str, ...] = ()
    point_in_time_policy: str = "not_applicable"
    fields: tuple[DatasetSchemaField, ...] = ()
    status: str = "unavailable"
    license_scope: str = "local_noncommercial_research"
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.dataset_id.strip() or not self.name.strip():
            raise ValueError("dataset_id and name must not be empty")
        if self.status not in PRODUCT_STATUSES:
            raise ValueError(f"unsupported dataset product status: {self.status}")
        if self.point_in_time_policy not in POINT_IN_TIME_POLICIES:
            raise ValueError(f"unsupported point-in-time policy: {self.point_in_time_policy}")


@dataclass(frozen=True, slots=True)
class DatasetRelease:
    """Immutable published snapshot of one dataset product."""

    version_id: str
    dataset_id: str
    status: str
    coverage_start: str | None = None
    coverage_end: str | None = None
    symbol_count: int | None = None
    coverage_ratio: float | None = None
    quality_report_id: str | None = None
    source_task_id: str | None = None
    content_sha256: str | None = None
    published_at: str | None = None

    def __post_init__(self) -> None:
        if not self.version_id.strip() or not self.dataset_id.strip():
            raise ValueError("version_id and dataset_id must not be empty")
        if self.status not in RELEASE_STATUSES:
            raise ValueError(f"unsupported dataset release status: {self.status}")
        if self.coverage_ratio is not None and not 0.0 <= self.coverage_ratio <= 1.0:
            raise ValueError("coverage_ratio must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class DatasetRequirement:
    """A strategy or factor declaration for a governed dataset slice."""

    dataset_id: str
    required_fields: tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None
    minimum_history: int = 0
    adjustment: str | None = None
    point_in_time_required: bool = True
    missing_data_policy: str = "unavailable"
    version_policy: str = "latest_published"

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be empty")
        if self.minimum_history < 0:
            raise ValueError("minimum_history must not be negative")
        if self.missing_data_policy not in MISSING_DATA_POLICIES:
            raise ValueError(f"unsupported missing data policy: {self.missing_data_policy}")


@dataclass(frozen=True, slots=True)
class ResolvedDatasetBinding:
    requirement: DatasetRequirement
    release: DatasetRelease
    asset_key: str | None = None
    quality_status: str = "unknown"
    coverage_status: str = "unknown"

    def __post_init__(self) -> None:
        if self.requirement.dataset_id != self.release.dataset_id:
            raise ValueError("dataset requirement and release must reference the same dataset")
        if self.release.status != "published":
            raise ValueError("formal input bindings require a published dataset release")


@dataclass(frozen=True, slots=True)
class RunInputBundle:
    """Immutable strategy, data, factor and universe bindings for one run."""

    bundle_id: str
    strategy_id: str
    strategy_version: str
    strategy_source_sha256: str
    datasets: tuple[ResolvedDatasetBinding, ...] = ()
    factor_bindings: tuple[dict[str, Any], ...] = ()
    universe_snapshot_id: str | None = None
    parameter_snapshot: dict[str, Any] = field(default_factory=dict)
    execution_snapshot: dict[str, Any] = field(default_factory=dict)
    execution_contract: str = "target-weights-v1"
    bundle_sha256: str | None = None

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.bundle_id,
                self.strategy_id,
                self.strategy_version,
                self.strategy_source_sha256,
            )
        ):
            raise ValueError("run input bundle identity fields must not be empty")

