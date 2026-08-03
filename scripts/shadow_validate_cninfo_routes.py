"""Run a read-only CNInfo shadow sync without writing governed facts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform import ClassificationHistoryStore  # noqa: E402
from data_platform.providers.cninfo_controlled_provider import (  # noqa: E402
    CninfoControlledProvider,
)


DEFAULT_SYMBOLS = (
    "000001",
    "000002",
    "000333",
    "002594",
    "300750",
    "600000",
    "600519",
    "601318",
    "688981",
    "601398",
)
STANDARD_PRIORITIES = {
    "中国上市公司协会上市公司行业分类标准": 0,
    "中证行业分类标准": 1,
    "申银万国行业分类标准": 2,
    "巨潮行业分类标准": 3,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--as-of", default="2026-07-31")
    parser.add_argument("--history-start", default="1990-01-01")
    parser.add_argument("--announcement-start", default="2026-07-01")
    parser.add_argument(
        "--classification-database",
        default="var/runtime/a_share_classification_history.sqlite3",
    )
    parser.add_argument("--requests-per-minute", type=int, default=10)
    args = parser.parse_args()

    symbols = tuple(
        dict.fromkeys(
            item.strip().split(".")[0].zfill(6)
            for item in args.symbols.split(",")
            if item.strip()
        )
    )
    provider = CninfoControlledProvider(
        retry_count=0,
        requests_per_minute=args.requests_per_minute,
    )
    local_store = ClassificationHistoryStore(Path(args.classification_database))
    started = time.time()
    print("shadow: industry category catalog", file=sys.stderr, flush=True)
    categories, category_error = _capture(
        "industry category catalog", provider.fetch_industry_categories
    )
    category_contract = (
        len(categories) >= 250
        and all(row["category_code"] and row["category_name"] for row in categories)
    )

    items: list[dict[str, Any]] = []
    for index, symbol in enumerate(symbols, start=1):
        print(
            f"shadow: {index}/{len(symbols)} {symbol} industry",
            file=sys.stderr,
            flush=True,
        )
        industry, industry_error = _capture(
            f"{symbol} industry",
            lambda: provider.fetch_industry_intervals(
                symbol, args.history_start, args.as_of
            ),
        )
        industry_contract = industry_error is None and _industry_contract(industry)
        shadow_current = _select_current(industry, args.as_of)
        local_current = _select_current(
            local_store.resolve(symbol, "industry", args.as_of), args.as_of
        )

        print(
            f"shadow: {index}/{len(symbols)} {symbol} share changes",
            file=sys.stderr,
            flush=True,
        )
        shares, share_error = _capture(
            f"{symbol} share changes",
            lambda: provider.fetch_share_changes(
                symbol, "2020-01-01", args.as_of
            ),
        )
        share_contract = share_error is None and all(
            row["symbol"] == symbol
            and row["source_unit"] == "万股"
            and (
                row["total_shares"] is None
                or (
                    row["total_shares"] >= 0
                    and row["total_shares_wan"] is not None
                    and abs(
                        row["total_shares"]
                        - row["total_shares_wan"] * 10_000
                    )
                    < 0.01
                )
            )
            for row in shares
        )

        print(
            f"shadow: {index}/{len(symbols)} {symbol} announcements",
            file=sys.stderr,
            flush=True,
        )
        announcements, announcement_error = _capture(
            f"{symbol} announcements",
            lambda: provider.fetch_announcements(
                symbol, args.announcement_start, args.as_of
            ),
        )
        announcement_contract = announcement_error is None and all(
            row["symbol"] == symbol
            and row["event_type"] == "announcement"
            and row["title"]
            and str(row["url"]).startswith("https://www.cninfo.com.cn/")
            for row in announcements
        )
        items.append(
            {
                "symbol": symbol,
                "industry_rows": len(industry),
                "industry_contract": industry_contract,
                "shadow_category": (
                    shadow_current.get("category") if shadow_current else None
                ),
                "local_category": (
                    local_current.get("category") if local_current else None
                ),
                "classification_match": bool(
                    shadow_current
                    and local_current
                    and shadow_current.get("category") == local_current.get("category")
                ),
                "share_change_rows": len(shares),
                "share_contract": share_contract,
                "announcement_rows": len(announcements),
                "announcement_contract": announcement_contract,
                "errors": {
                    "industry": industry_error,
                    "share_changes": share_error,
                    "announcements": announcement_error,
                },
            }
        )

    if category_error is not None:
        print(
            "shadow: retry industry category catalog after endpoint cycle",
            file=sys.stderr,
            flush=True,
        )
        categories, category_error = _capture(
            "industry category catalog retry", provider.fetch_industry_categories
        )
        category_contract = (
            category_error is None
            and len(categories) >= 250
            and all(
                row["category_code"] and row["category_name"]
                for row in categories
            )
        )

    passed = bool(symbols) and category_contract and all(
        item["industry_contract"]
        and item["share_contract"]
        and item["announcement_contract"]
        for item in items
    )
    result = {
        "status": "passed" if passed else "failed",
        "mode": "read_only_shadow",
        "writes": 0,
        "published": False,
        "symbols": len(symbols),
        "requests_per_minute": args.requests_per_minute,
        "category_rows": len(categories),
        "category_contract": category_contract,
        "category_error": category_error,
        "industry_rows": sum(item["industry_rows"] for item in items),
        "share_change_rows": sum(item["share_change_rows"] for item in items),
        "announcement_rows": sum(item["announcement_rows"] for item in items),
        "classification_matches": sum(
            item["classification_match"] for item in items
        ),
        "classification_comparable": sum(
            bool(item["shadow_category"] and item["local_category"]) for item in items
        ),
        "elapsed_seconds": round(time.time() - started, 3),
        "items": items,
    }
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if passed else 2)


def _capture(label: str, loader) -> tuple[list[dict[str, Any]], str | None]:
    try:
        return list(loader()), None
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        print(f"shadow error: {label}: {message}", file=sys.stderr, flush=True)
        return [], message

def _industry_contract(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    keys: set[tuple[str, str, str]] = set()
    for row in rows:
        standard = str(row.get("evidence", {}).get("classification_standard") or "")
        key = (standard, str(row.get("valid_from") or ""), str(row.get("category") or ""))
        if (
            not standard
            or not key[1]
            or not key[2]
            or key in keys
        ):
            return False
        keys.add(key)
        grouped[standard].append(row)
    for items in grouped.values():
        items.sort(key=lambda row: str(row["valid_from"]))
        for index, row in enumerate(items):
            if index + 1 == len(items):
                if row.get("valid_to") is not None:
                    return False
                continue
            next_from = str(items[index + 1]["valid_from"])
            expected = (
                date.fromisoformat(next_from) - timedelta(days=1)
            ).isoformat()
            if row.get("valid_to") != expected or row["valid_from"] >= next_from:
                return False
    return True


def _select_current(
    rows: list[dict[str, Any]], as_of: str
) -> dict[str, Any] | None:
    active = [
        row
        for row in rows
        if str(row.get("valid_from") or "") <= as_of
        and (
            not row.get("valid_to")
            or str(row.get("valid_to")) >= as_of
        )
    ]
    if not active:
        return None
    return max(
        active,
        key=lambda row: (
            str(row.get("valid_from") or ""),
            -STANDARD_PRIORITIES.get(
                str(
                    row.get("evidence", {}).get("classification_standard") or ""
                ),
                99,
            ),
        ),
    )


if __name__ == "__main__":
    main()
