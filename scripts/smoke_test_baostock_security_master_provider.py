"""Deterministic contract checks for the Baostock security-state adapter."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from _project_bootstrap import ensure_project_root_on_sys_path


class _Result:
    error_code = "0"
    error_msg = "success"
    fields = ["date", "code", "tradestatus", "isST"]

    def __init__(self) -> None:
        self._rows = [
            ["2026-01-02", "sz.000001", "1", "0"],
            ["2026-01-05", "sz.000001", "0", "1"],
        ]
        self._index = -1

    def next(self) -> bool:
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


def main() -> None:
    ensure_project_root_on_sys_path()
    fake = SimpleNamespace(
        login=lambda: SimpleNamespace(error_code="0", error_msg="success"),
        logout=lambda: SimpleNamespace(error_code="0", error_msg="success"),
        query_history_k_data_plus=lambda *args, **kwargs: _Result(),
    )
    original = sys.modules.get("baostock")
    sys.modules["baostock"] = fake
    try:
        from data_platform.providers.baostock_security_master_provider import (
            BaostockSecurityMasterProvider,
        )

        provider = BaostockSecurityMasterProvider()
        rows = provider.fetch_daily_security_states(
            symbol="000001.XSHE",
            start_date="2026-01-02",
            end_date="2026-01-05",
        )
        assert [row["risk_warning"] for row in rows] == [False, True]
        assert [row["is_tradable"] for row in rows] == [True, False]
        assert all(row["available_at"] == row["trade_date"] for row in rows)
        try:
            provider.assert_symbol_supported("920176")
        except RuntimeError as error:
            assert "BSE" in str(error)
        else:
            raise AssertionError("BSE must fail closed")
        provider.close()
    finally:
        if original is None:
            sys.modules.pop("baostock", None)
        else:
            sys.modules["baostock"] = original
    print("[baostock-security-master-provider] passed")


if __name__ == "__main__":
    main()
