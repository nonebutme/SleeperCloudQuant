from __future__ import annotations

import re
from datetime import datetime

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.task_ids import TASK_ID_PREFIXES, new_task_id


def main() -> None:
    created_at = datetime(2026, 8, 1, 12, 34, 56)
    values = [new_task_id(prefix, created_at=created_at) for prefix in sorted(TASK_ID_PREFIXES)]
    for prefix, value in zip(sorted(TASK_ID_PREFIXES), values, strict=True):
        assert re.fullmatch(rf"{re.escape(prefix)}-20260801-123456-[A-F0-9]{{6}}", value), value
    assert len(set(values)) == len(values)
    try:
        new_task_id("unknown", created_at=created_at)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported task prefix must be rejected")
    print("unified readable task id smoke passed")


if __name__ == "__main__":
    main()
