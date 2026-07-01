"""Ricequant configuration loading for phase-1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import environ
from pathlib import Path


class RicequantConfigError(ValueError):
    """Raised when Ricequant credentials are incomplete."""


@dataclass(frozen=True, slots=True)
class RicequantConfig:
    """Credentials and optional connection settings for Ricequant."""

    username: str
    password: str
    host: str | None = None
    port: int | None = None


DEFAULT_ENV_FILE = Path(".env")


def _first_non_empty(mapping: Mapping[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return None


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def load_ricequant_config(
    env: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> RicequantConfig:
    """Load Ricequant credentials from env file and environment variables."""

    resolved_env = dict(_load_env_file(env_file or DEFAULT_ENV_FILE))
    resolved_env.update(environ if env is None else env)

    username = _first_non_empty(
        resolved_env,
        ("RICEQUANT_USERNAME", "RICEQUANT_ACCOUNT", "RQDATAC_USERNAME"),
    )
    password = _first_non_empty(
        resolved_env,
        ("RICEQUANT_PASSWORD", "RQDATAC_PASSWORD"),
    )
    host = _first_non_empty(resolved_env, ("RICEQUANT_HOST", "RQDATAC_HOST"))
    port_value = _first_non_empty(resolved_env, ("RICEQUANT_PORT", "RQDATAC_PORT"))

    missing_keys: list[str] = []
    if username is None:
        missing_keys.append("RICEQUANT_USERNAME")
    if password is None:
        missing_keys.append("RICEQUANT_PASSWORD")
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise RicequantConfigError(
            f"Missing Ricequant credentials. Set environment variables: {missing}."
        )

    port = int(port_value) if port_value is not None else None
    return RicequantConfig(
        username=username,
        password=password,
        host=host,
        port=port,
    )
