"""Minimal market-domain models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Stock:
    """Minimal stock identifier model."""

    symbol: str
    name: str | None = None
    exchange: str | None = None


@dataclass(frozen=True, slots=True)
class Bar:
    """Minimal OHLCV row used by services and schemas."""

    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
