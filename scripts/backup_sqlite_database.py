"""Create a transactionally consistent SQLite backup with progress output."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--pages", type=int, default=8192)
    args = parser.parse_args()
    source_path = Path(args.source)
    target_path = Path(args.target)
    if not source_path.is_file():
        raise SystemExit(f"source database does not exist: {source_path}")
    if target_path.exists():
        raise SystemExit(f"target already exists: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
        source.execute("PRAGMA wal_checkpoint(PASSIVE)")

        def progress(status: int, remaining: int, total: int) -> None:
            copied = total - remaining
            if remaining == 0 or copied % max(1, args.pages * 20) == 0:
                print(
                    f"[backup] copied_pages={copied} total_pages={total} "
                    f"remaining_pages={remaining} status={status}",
                    flush=True,
                )

        source.backup(target, pages=max(1, args.pages), progress=progress)
        result = target.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"backup quick_check failed: {result}")
    print(
        f"[backup] completed source={source_path} target={target_path} "
        f"bytes={target_path.stat().st_size}",
        flush=True,
    )


if __name__ == "__main__":
    main()
