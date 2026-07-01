"""Effective settings provider for phase-1."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from os import environ
from typing import Any


class EffectiveSettingsProvider:
    """Merge defaults, file settings and env overrides with a TTL cache."""

    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._cache: dict[str, Any] | None = None
        self._cache_time: datetime | None = None

    def invalidate(self) -> None:
        self._cache = None
        self._cache_time = None

    def _is_cache_valid(self) -> bool:
        return (
            self._cache is not None
            and self._cache_time is not None
            and datetime.now(timezone.utc) - self._cache_time < self._ttl
        )

    def get_effective_settings(
        self,
        *,
        defaults: dict[str, Any] | None = None,
        file_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._is_cache_valid():
            return deepcopy(self._cache or {})

        merged = deepcopy(defaults or {})
        merged.update(file_settings or {})

        for key in list(merged):
            env_candidates = [
                key,
                key.upper(),
                str(key).replace(".", "_").replace(" ", "_").upper(),
            ]
            for env_key in env_candidates:
                if env_key in environ:
                    merged[key] = environ[env_key]
                    break

        self._cache = deepcopy(merged)
        self._cache_time = datetime.now(timezone.utc)
        return merged
