"""Point-in-time security-master interval normalization without source I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any


def build_security_master_intervals(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_trade_dates: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Coalesce complete daily security states into non-overlapping intervals.

    Source adapters must provide ``trade_date``, ``symbol`` and
    ``risk_warning``.  A missing expected trade date is rejected instead of
    being silently bridged, because doing so could hide a historical ST change.
    """

    ordered = sorted((dict(row) for row in rows), key=lambda row: str(row.get("trade_date") or ""))
    if not ordered:
        return []
    dates = [str(row.get("trade_date") or "")[:10] for row in ordered]
    if any(len(item) != 10 for item in dates) or len(set(dates)) != len(dates):
        raise ValueError("security status history requires unique YYYY-MM-DD trade dates")
    expected = {str(item)[:10] for item in expected_trade_dates if str(item)}
    missing = sorted(expected.difference(dates))
    if missing:
        raise ValueError(
            f"security status history coverage is incomplete: {len(missing)} missing dates; "
            f"first={missing[0]} last={missing[-1]}"
        )

    normalized = [_normalize_daily_state(row, trade_date) for row, trade_date in zip(ordered, dates)]
    symbol = normalized[0]["symbol"]
    if any(row["symbol"] != symbol for row in normalized):
        raise ValueError("security status history must contain exactly one symbol")

    intervals: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    previous_date = ""
    for row in normalized:
        state = (row["name"], row["listing_status"], row["risk_warning"])
        current_state = (
            (current["name"], current["listing_status"], current["risk_warning"])
            if current is not None else None
        )
        if current is None or state != current_state:
            if current is not None:
                current["valid_to"] = previous_date
                intervals.append(current)
            current = {
                "symbol": symbol,
                "name": row["name"],
                "listing_status": row["listing_status"],
                "risk_warning": row["risk_warning"],
                "valid_from": row["trade_date"],
                "valid_to": None,
                "available_at": row["available_at"],
                "source": row["source"],
                "source_observed_at": row["source_observed_at"],
                "evidence": {
                    "derivation": "coalesced_complete_daily_security_state",
                    "first_source_trade_date": row["trade_date"],
                    "source_payload_hash": row.get("source_payload_hash"),
                },
            }
        previous_date = row["trade_date"]
    assert current is not None
    current["valid_to"] = previous_date
    intervals.append(current)
    return intervals


def validate_security_master_intervals(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate identity, dates, point-in-time availability and overlap."""

    issues: list[dict[str, Any]] = []
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        symbol = str(row.get("symbol") or "").strip().split(".", 1)[0].zfill(6)
        valid_from = str(row.get("valid_from") or "")[:10]
        valid_to = str(row.get("valid_to") or "")[:10]
        available_at = str(row.get("available_at") or "")[:10]
        if not symbol or len(valid_from) != 10 or (valid_to and len(valid_to) != 10):
            issues.append({"code": "security_interval_identity_invalid", "symbol": symbol})
            continue
        if valid_to and valid_to < valid_from:
            issues.append({"code": "security_interval_date_order_invalid", "symbol": symbol})
        if len(available_at) != 10 or available_at > valid_from:
            issues.append({"code": "security_interval_available_at_invalid", "symbol": symbol})
        if _bool_or_none(row.get("risk_warning")) is None:
            issues.append({"code": "security_interval_risk_warning_invalid", "symbol": symbol})
        if not str(row.get("listing_status") or "").strip():
            issues.append({"code": "security_interval_listing_status_missing", "symbol": symbol})
        by_symbol.setdefault(symbol, []).append(row)
    for symbol, items in by_symbol.items():
        ordered = sorted(items, key=lambda row: str(row.get("valid_from") or ""))
        previous_to = ""
        for row in ordered:
            valid_from = str(row.get("valid_from") or "")[:10]
            if previous_to and valid_from <= previous_to:
                issues.append({"code": "security_intervals_overlap", "symbol": symbol})
            previous_to = str(row.get("valid_to") or "9999-12-31")[:10]
    return {"ok": not issues, "row_count": len(rows), "symbol_count": len(by_symbol), "issues": issues}


def _normalize_daily_state(row: Mapping[str, Any], trade_date: str) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").strip().split(".", 1)[0].zfill(6)
    risk_warning = _bool_or_none(row.get("risk_warning"))
    if not symbol or risk_warning is None:
        raise ValueError(f"invalid daily security state: symbol={symbol} trade_date={trade_date}")
    available_at = str(row.get("available_at") or trade_date)
    if available_at[:10] > trade_date:
        raise ValueError(f"daily security state is not point-in-time available: {symbol} {trade_date}")
    date.fromisoformat(trade_date)
    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "name": str(row.get("name") or ""),
        "listing_status": str(row.get("listing_status") or "listed").strip().lower(),
        "risk_warning": risk_warning,
        "available_at": available_at,
        "source": str(row.get("source") or "unknown"),
        "source_observed_at": str(row.get("source_observed_at") or available_at),
        "source_payload_hash": str(row.get("source_payload_hash") or ""),
    }


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None
