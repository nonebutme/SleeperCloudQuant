"""Shared enums for the minimal formal domain layer."""

from __future__ import annotations

from enum import StrEnum


class BacktestRunStatus(StrEnum):
    """Normalized run statuses used by the minimal service layer."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
