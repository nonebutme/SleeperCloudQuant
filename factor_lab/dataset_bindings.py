"""Compatibility-side factor dataset dependency and provenance bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class FactorDatasetBinding:
    factor_id: str
    dataset_id: str = "a_share_daily"
    required_fields: tuple[str, ...] = ("symbol", "trade_date", "close")
    point_in_time_policy: str = "as_of_trade_date"
    adjustment: str = "raw"


@dataclass(frozen=True, slots=True)
class FactorInputProvenance:
    factor_id: str
    dataset_id: str
    version_id: str | None
    status: str
    reason: str | None = None


BUILTIN_FACTOR_DATASET_BINDINGS: tuple[FactorDatasetBinding, ...] = (
    FactorDatasetBinding("close_to_close_return_1d"),
    FactorDatasetBinding("close_to_ma2_bias"),
)


def get_factor_dataset_binding(factor_id: str) -> FactorDatasetBinding:
    normalized = str(factor_id).strip().lower()
    for binding in BUILTIN_FACTOR_DATASET_BINDINGS:
        if binding.factor_id == normalized:
            return binding
    raise KeyError(f"no dataset binding for factor_id: {factor_id}")


def resolve_factor_input_provenance(
    *,
    factor_id: str,
    symbol: str,
    start_date: str | None,
    end_date: str | None,
    published_version_resolver: Callable[..., dict[str, Any]] | None,
) -> FactorInputProvenance:
    binding = get_factor_dataset_binding(factor_id)
    if published_version_resolver is None:
        return FactorInputProvenance(
            factor_id=binding.factor_id,
            dataset_id=binding.dataset_id,
            version_id=None,
            status="unavailable",
            reason="published_version_resolver_unavailable",
        )
    if not start_date or not end_date:
        return FactorInputProvenance(
            factor_id=binding.factor_id,
            dataset_id=binding.dataset_id,
            version_id=None,
            status="unavailable",
            reason="date_range_required_for_published_binding",
        )
    try:
        payload = dict(
            published_version_resolver(
                symbol=symbol,
                adjustment=binding.adjustment,
                start_date=start_date,
                end_date=end_date,
            )
        )
    except Exception as exc:
        return FactorInputProvenance(
            factor_id=binding.factor_id,
            dataset_id=binding.dataset_id,
            version_id=None,
            status="unavailable",
            reason=f"version_resolution_failed:{type(exc).__name__}",
        )
    version_id = payload.get("version_id") or payload.get("data_version")
    return FactorInputProvenance(
        factor_id=binding.factor_id,
        dataset_id=binding.dataset_id,
        version_id=str(version_id) if version_id else None,
        status=str(payload.get("status") or "unavailable"),
        reason=payload.get("reason"),
    )

