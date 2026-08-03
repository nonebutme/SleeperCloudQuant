"""Smoke test controlled CNINFO industry fill-missing helpers."""

from __future__ import annotations

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from scripts.run_cninfo_industry_fill_missing import (  # noqa: E402
    _industry_contract,
    _select_current,
)


def main() -> None:
    rows = [
        {
            "symbol": "000001",
            "dimension": "industry",
            "category": "??",
            "valid_from": "2020-01-01",
            "valid_to": "2023-12-31",
            "evidence": {"classification_standard": "????????"},
        },
        {
            "symbol": "000001",
            "dimension": "industry",
            "category": "??????",
            "valid_from": "2024-01-01",
            "valid_to": None,
            "evidence": {"classification_standard": "????????"},
        },
        {
            "symbol": "000001",
            "dimension": "industry",
            "category": "?????",
            "valid_from": "2023-01-01",
            "valid_to": None,
            "evidence": {"classification_standard": "??????????"},
        },
    ]
    assert _industry_contract(rows)
    current = _select_current(rows, "2026-07-31")
    assert current is not None
    assert current["category"] == "??????"
    broken = [dict(row) for row in rows]
    broken[0] = {**broken[0], "valid_to": "2024-01-02"}
    assert not _industry_contract(broken)
    duplicate = rows + [dict(rows[0])]
    assert not _industry_contract(duplicate)
    print("CNInfo industry fill-missing smoke passed")


if __name__ == "__main__":
    main()
