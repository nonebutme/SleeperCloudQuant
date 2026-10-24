"""Governed fail-closed point-in-time A-share universe construction.

This module supersedes the unverified ``point_in_time_universe_gate`` draft.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_LISTED_STATUSES = frozenset({"listed", "active", "normal"})


def build_point_in_time_a_share_universe(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of_date: str,
    structural_exclusion_prefixes: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one dated universe and reject missing, future or overlapping facts.

    Structural exclusions are evaluated before risk-warning facts. This permits
    a strategy to exclude an entire board from an all-A-share mother universe
    without inventing an unused historical risk state for that board.
    """

    date = str(as_of_date)[:10]
    if len(date) != 10:
        raise ValueError("as_of_date must be YYYY-MM-DD")
    issues: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    excluded_prefixes = tuple(str(item) for item in structural_exclusion_prefixes if str(item))
    for raw in rows:
        row = dict(raw)
        symbol = str(row.get("symbol") or "").strip()
        valid_from = str(row.get("valid_from") or "")[:10]
        valid_to = str(row.get("valid_to") or "")[:10]
        if not symbol or len(valid_from) != 10:
            issues.append({"code": "universe_interval_identity_missing", "symbol": symbol})
            continue
        if valid_from > date or (valid_to and valid_to < date):
            continue
        bare_symbol = symbol.split(".")[0]
        structurally_excluded = bool(excluded_prefixes and bare_symbol.startswith(excluded_prefixes))
        required_fields = ["listing_status", "available_at"]
        if not structurally_excluded:
            required_fields.append("risk_warning")
        missing = [
            field
            for field in required_fields
            if row.get(field) is None or str(row.get(field)).strip() == ""
        ]
        if missing:
            issues.append(
                {"code": "point_in_time_security_fields_missing", "symbol": symbol, "fields": missing}
            )
            continue
        available_at = str(row.get("available_at") or "")[:10]
        if len(available_at) != 10:
            issues.append({"code": "available_at_invalid", "symbol": symbol})
            continue
        if available_at > date:
            issues.append(
                {
                    "code": "security_fact_not_yet_available",
                    "symbol": symbol,
                    "available_at": str(row.get("available_at")),
                }
            )
            continue
        risk_warning = _parse_bool(row.get("risk_warning"))
        if risk_warning is None and not structurally_excluded:
            issues.append({"code": "risk_warning_value_invalid", "symbol": symbol})
            continue
        if symbol in seen:
            issues.append({"code": "overlapping_security_intervals", "symbol": symbol})
            continue
        seen.add(symbol)
        listing_status = str(row.get("listing_status") or "").strip().lower()
        eligible = (
            listing_status in _LISTED_STATUSES
            and not structurally_excluded
            and risk_warning is False
        )
        exclusion_reason = None
        if not eligible:
            if listing_status not in _LISTED_STATUSES:
                exclusion_reason = "not_listed"
            elif structurally_excluded:
                exclusion_reason = "structural_symbol_scope"
            else:
                exclusion_reason = "risk_warning"
        selected.append(
            {
                "symbol": symbol,
                "name": str(row.get("name") or ""),
                "market": str(row.get("market") or ""),
                "listing_status": listing_status,
                "risk_warning": risk_warning,
                "valid_from": valid_from,
                "valid_to": valid_to or None,
                "available_at": str(row.get("available_at")),
                "eligible": eligible,
                "exclusion_reason": exclusion_reason,
            }
        )
    eligible_rows = sorted((item for item in selected if item["eligible"]), key=lambda item: item["symbol"])
    excluded_rows = sorted((item for item in selected if not item["eligible"]), key=lambda item: item["symbol"])
    return {
        "ok": not issues,
        "as_of_date": date,
        "universe_policy": "point_in_time_all_a_share_fail_closed",
        "structural_exclusion_prefixes": list(excluded_prefixes),
        "eligible": eligible_rows if not issues else [],
        "excluded": excluded_rows,
        "issues": issues,
    }


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None
