"""Unified direct-execution entry for local formal verification scripts."""

from __future__ import annotations

import runpy
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def _run_script(script_name: str) -> None:
    script_path = Path(__file__).resolve().parent / script_name
    runpy.run_path(str(script_path), run_name="__main__")


def main() -> None:
    ensure_project_root_on_sys_path()
    scripts = [
        "verify_formal_fake_runtime.py",
        "verify_formal_reporting.py",
        "verify_formal_sqlite_cache.py",
    ]
    for script_name in scripts:
        print(f"[formal] running {script_name}")
        _run_script(script_name)
    print("[formal] all verifications passed")


if __name__ == "__main__":
    main()
