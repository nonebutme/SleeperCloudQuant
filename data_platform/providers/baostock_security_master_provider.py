"""Baostock adapter for historical point-in-time ST and tradability facts."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

from .a_share_sqlite_repository import _normalize_symbol


class BaostockSecurityMasterProvider:
    """Read complete daily security states from Baostock.

    Baostock keeps a process-global session, so calls are serialized.  The
    adapter deliberately rejects BSE symbols because the upstream API only
    accepts ``sh`` and ``sz`` markets; an empty BSE response must never be
    interpreted as a non-ST history.
    """

    def __init__(self, *, request_gate: Callable[[], None] | None = None) -> None:
        self.request_gate = request_gate
        self._lock = threading.Lock()
        self._logged_in = False

    def fetch_daily_security_states(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        code = _normalize_symbol(symbol)
        market_code = self.assert_symbol_supported(code)
        if self.request_gate is not None:
            self.request_gate()
        with self._lock:
            bs = self._ensure_login()
            result = bs.query_history_k_data_plus(
                market_code,
                "date,code,tradestatus,isST",
                start_date=str(start_date)[:10],
                end_date=str(end_date)[:10],
                frequency="d",
                adjustflag="3",
            )
            if str(result.error_code) != "0":
                self._logged_in = False
                raise RuntimeError(
                    "baostock_history_failed: "
                    f"symbol={market_code}; code={result.error_code}; "
                    f"message={result.error_msg}"
                )
            fields = list(result.fields)
            records: list[dict[str, Any]] = []
            while result.next():
                values = result.get_row_data()
                if len(values) != len(fields):
                    raise RuntimeError(
                        "baostock_history_row_shape_invalid: "
                        f"symbol={market_code}; fields={len(fields)}; values={len(values)}"
                    )
                records.append(dict(zip(fields, values)))
        observed_at = _utc_now()
        rows: list[dict[str, Any]] = []
        for record in records:
            trade_date = str(record.get("date") or "")[:10]
            risk_warning = _binary(record.get("isST"), field="isST", symbol=code, trade_date=trade_date)
            is_tradable = _binary(
                record.get("tradestatus"),
                field="tradestatus",
                symbol=code,
                trade_date=trade_date,
            )
            evidence = {
                "provider": "baostock",
                "provider_version": "0.9.3",
                "upstream_code": str(record.get("code") or market_code),
                "trade_date": trade_date,
                "isST": int(risk_warning),
                "tradestatus": int(is_tradable),
                "availability_semantics": "contemporaneous_daily_field",
            }
            rows.append(
                {
                    "symbol": code,
                    "trade_date": trade_date,
                    "name": "",
                    "listing_status": "listed",
                    "risk_warning": risk_warning,
                    "is_tradable": is_tradable,
                    "available_at": trade_date,
                    "source": "baostock:query_history_k_data_plus",
                    "source_observed_at": observed_at,
                    "source_payload_hash": _hash(evidence),
                    "evidence": evidence,
                }
            )
        return rows

    def assert_symbol_supported(self, symbol: str) -> str:
        """Return the upstream code or raise an explicit market-boundary error."""

        return _baostock_symbol(_normalize_symbol(symbol))

    def close(self) -> None:
        with self._lock:
            if not self._logged_in:
                return
            import baostock as bs

            bs.logout()
            self._logged_in = False

    def _ensure_login(self) -> Any:
        import baostock as bs

        if not self._logged_in:
            result = bs.login()
            if str(result.error_code) != "0":
                raise RuntimeError(
                    "baostock_login_failed: "
                    f"code={result.error_code}; message={result.error_msg}"
                )
            self._logged_in = True
        return bs


def _baostock_symbol(symbol: str) -> str:
    if symbol.startswith("6"):
        return f"sh.{symbol}"
    if symbol.startswith(("0", "3")):
        return f"sz.{symbol}"
    if symbol.startswith(("4", "8", "9")):
        raise RuntimeError(
            f"baostock_market_unsupported: BSE symbol={symbol}; "
            "point-in-time all-A coverage remains unavailable"
        )
    raise ValueError(f"unsupported A-share symbol: {symbol}")


def _binary(value: Any, *, field: str, symbol: str, trade_date: str) -> bool:
    normalized = str(value).strip()
    if normalized not in {"0", "1"}:
        raise ValueError(
            f"baostock_{field}_invalid: symbol={symbol}; "
            f"trade_date={trade_date}; value={value!r}"
        )
    return normalized == "1"


def _hash(value: dict[str, Any]) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
