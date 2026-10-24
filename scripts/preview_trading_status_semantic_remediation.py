"""Read-only administrator preview for historical trading-status remediation."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from _project_bootstrap import ensure_project_root_on_sys_path
except ModuleNotFoundError:  # Imported as scripts.* by the Web application.
    from scripts._project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.storage.a_share_governance_store import AShareGovernanceStore


def build_preview_report(
    database: str | Path, *, current_symbols_only: bool = True,
    page_size: int = 5_000, sample_limit: int = 20,
) -> dict[str, Any]:
    """Scan candidates through read-only connections and return an audit summary."""

    path = Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"market database not found: {path}")
    store = AShareGovernanceStore(path)
    after_symbol = ""
    after_trade_date = ""
    total = 0
    repairability_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    sample_counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    while True:
        page = store.scan_trading_status_repair_candidates(
            after_symbol=after_symbol,
            after_trade_date=after_trade_date,
            limit=page_size,
            current_symbols_only=current_symbols_only,
        )
        if not page:
            break
        for candidate in page:
            total += 1
            repairability = str(candidate["repairability"])
            reason = str(candidate["reason"])
            source = str((candidate.get("before") or {}).get("source") or "unknown")
            repairability_counts[repairability] += 1
            reason_counts[reason] += 1
            source_counts[source] += 1
            digest.update(str(candidate["evidence_fingerprint"]).encode("ascii"))
            if sample_counts[reason] < sample_limit:
                samples.append({
                    "symbol": candidate["symbol"],
                    "trade_date": candidate["trade_date"],
                    "repairability": repairability,
                    "reason": reason,
                    "source": source,
                    "bars": candidate["bars"],
                    "evidence_fingerprint": candidate["evidence_fingerprint"],
                })
                sample_counts[reason] += 1
        last = page[-1]
        after_symbol = str(last["symbol"])
        after_trade_date = str(last["trade_date"])
        if len(page) < max(1, min(int(page_size), 10_000)):
            break
    return {
        "mode": "read_only_preview",
        "writes": 0,
        "apply_supported": False,
        "database": str(path),
        "scope": "current_symbols" if current_symbols_only else "all_symbols",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidate_count": total,
        "repairability_counts": dict(sorted(repairability_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "source_counts": dict(source_counts.most_common()),
        "candidate_set_hash": digest.hexdigest(),
        "samples": samples,
        "next_authorization_required": (
            "explicit per-run approval is required before invoking the separate batch writer"
        ),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Preview trading-status semantic remediation without database writes.",
    )
    parser.add_argument(
        "--database", type=Path,
        default=root / "var" / "market" / "a_share_market.sqlite3",
    )
    parser.add_argument("--all-symbols", action="store_true")
    parser.add_argument("--page-size", type=int, default=5_000)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument(
        "--output", type=Path,
        help="Optional JSON report path; the database remains read-only.",
    )
    arguments = parser.parse_args()
    report = build_preview_report(
        arguments.database,
        current_symbols_only=not arguments.all_symbols,
        page_size=arguments.page_size,
        sample_limit=max(0, arguments.sample_limit),
    )
    content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(content + "\n", encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
