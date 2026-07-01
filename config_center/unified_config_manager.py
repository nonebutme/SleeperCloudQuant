"""Minimal unified configuration manager for phase-1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .effective_settings_provider import EffectiveSettingsProvider
from .providers.ricequant_config import RicequantConfig, load_ricequant_config


class UnifiedConfigManager:
    """Single entry point for phase-1 configuration loading."""

    def __init__(
        self,
        *,
        root_dir: Path | None = None,
        provider: EffectiveSettingsProvider | None = None,
    ) -> None:
        self._root_dir = root_dir or Path(__file__).resolve().parent
        self._profiles_path = self._root_dir / "profiles" / "backtest_profiles.json"
        self._provider = provider or EffectiveSettingsProvider()

    def get_backtest_profiles(self) -> dict[str, Any]:
        """Return all configured backtest profiles."""

        return self._load_json_file(self._profiles_path)

    def get_backtest_profile(self, profile_name: str) -> dict[str, Any]:
        """Return one backtest profile by name."""

        profiles = self.get_backtest_profiles()
        if profile_name not in profiles:
            raise KeyError(f"Unknown backtest profile: {profile_name}")
        profile = profiles[profile_name]
        if not isinstance(profile, dict):
            raise ValueError(f"Backtest profile must be an object: {profile_name}")
        return dict(profile)

    def get_ricequant_config(self) -> RicequantConfig:
        """Return Ricequant credentials from env file and environment."""

        env_file = self._root_dir.parent / ".env"
        return load_ricequant_config(env_file=env_file)

    def get_effective_runtime_settings(
        self,
        *,
        defaults: dict[str, Any] | None = None,
        file_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return merged runtime settings for phase-1."""

        return self._provider.get_effective_settings(
            defaults=defaults,
            file_settings=file_settings,
        )

    @staticmethod
    def _load_json_file(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object in {path}")
        return payload
