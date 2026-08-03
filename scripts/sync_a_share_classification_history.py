"""Sync/import effective-dated A-share industry and concept classifications."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path



def main() -> None:
    ensure_project_root_on_sys_path()
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="var/runtime/a_share_classification_history.sqlite3")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols for CNInfo industry history")
    parser.add_argument("--start-date", default="19900101")
    parser.add_argument("--end-date", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--input-jsonl", help="Effective-dated industry/concept records")
    args = parser.parse_args()

    from data_platform import ClassificationHistoryStore

    store = ClassificationHistoryStore(args.database)
    rows: list[dict[str, Any]] = []
    if args.input_jsonl:
        rows.extend(_read_jsonl(Path(args.input_jsonl)))
    symbols = [item.strip().split(".")[0].zfill(6) for item in args.symbols.split(",") if item.strip()]
    if symbols:
        rows.extend(_fetch_cninfo_industries(symbols, args.start_date, args.end_date))
    written = store.upsert_intervals(rows)
    print(json.dumps({"status": "completed", "written": written, "coverage": store.coverage()}, ensure_ascii=False))


def _fetch_cninfo_industries(symbols: list[str], start_date: str, end_date: str) -> list[dict[str, Any]]:
    from data_platform.providers.cninfo_controlled_provider import CninfoControlledProvider

    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    provider = CninfoControlledProvider()
    result: list[dict[str, Any]] = []
    for symbol in symbols:
        result.extend(
            provider.fetch_industry_intervals(
                symbol, start_date, end_date, observed_at=observed_at
            )
        )
    return result

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(dict(json.loads(line)))
    return rows



if __name__ == "__main__":
    main()
