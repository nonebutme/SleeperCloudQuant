"""Deterministic checks for CNInfo shadow validation semantics."""

from __future__ import annotations

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from shadow_validate_cninfo_routes import (  # noqa: E402
    _industry_contract,
    _select_current,
)


def main() -> None:
    rows = [
        {
            "category": "银行",
            "valid_from": "2020-01-01",
            "valid_to": None,
            "evidence": {"classification_standard": "巨潮行业分类标准"},
        },
        {
            "category": "商业银行",
            "valid_from": "2021-01-01",
            "valid_to": "2022-12-31",
            "evidence": {"classification_standard": "中证行业分类标准"},
        },
        {
            "category": "货币金融服务",
            "valid_from": "2023-01-01",
            "valid_to": None,
            "evidence": {"classification_standard": "中证行业分类标准"},
        },
    ]
    assert _industry_contract(rows)
    current = _select_current(rows, "2026-07-31")
    assert current is not None
    assert current["category"] == "货币金融服务"

    broken = [dict(row) for row in rows]
    broken[1] = {**broken[1], "valid_to": "2022-12-30"}
    assert not _industry_contract(broken)
    print("CNInfo shadow validation smoke passed")


if __name__ == "__main__":
    main()
