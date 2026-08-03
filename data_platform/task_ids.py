"""Unified, readable identifiers for persistent data-center tasks."""

from __future__ import annotations

import uuid
from datetime import datetime


TASK_ID_PREFIXES = frozenset({"a-share-sync", "panorama-sync", "quality-scan"})


def new_task_id(prefix: str, *, created_at: datetime | None = None) -> str:
    """Return ``<type>-YYYYMMDD-HHMMSS-XXXXXX`` using local creation time."""

    normalized = str(prefix).strip()
    if normalized not in TASK_ID_PREFIXES:
        raise ValueError(f"unsupported task id prefix: {normalized}")
    timestamp = created_at or datetime.now().astimezone()
    return f"{normalized}-{timestamp.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"