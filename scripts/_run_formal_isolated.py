"""Run one verification script and force process teardown afterward."""

from __future__ import annotations

import os
import runpy
import sys
import traceback
import builtins
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: _run_formal_isolated.py <script>")
    if os.environ.get("SCQ_FORMAL_STORAGE_GUARD_REQUIRED") == "1" and not getattr(
        builtins, "_SCQ_FORMAL_STORAGE_GUARD_READY", False
    ):
        print(
            "formal verification isolation failed: SQLite storage guard was not loaded",
            file=sys.stderr,
        )
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(97)
    script = Path(sys.argv[1]).resolve()
    exit_code = 0
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as error:
        if error.code is None:
            exit_code = 0
        elif isinstance(error.code, int):
            exit_code = error.code
        else:
            print(error.code, file=sys.stderr)
            exit_code = 1
    except BaseException:
        traceback.print_exc()
        exit_code = 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)


if __name__ == "__main__":
    main()
