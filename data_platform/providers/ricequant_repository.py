"""Ricequant-backed repository for phase-1 market data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from config_center.providers.ricequant_config import RicequantConfig
from data_platform.repository.contracts import MarketDataRepository


class RicequantClientProtocol(Protocol):
    """Minimal client protocol expected by the phase-1 repository."""

    def get_price_history(
        self,
        symbol: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        """Return raw historical rows from the provider."""

    def get_index_components(
        self,
        index_code: str,
        *,
        date: str | None = None,
    ) -> Sequence[str]:
        """Return raw index component symbols from the provider."""

    def get_financial_indicators(
        self,
        symbol: str,
        *,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        """Return raw financial-indicator rows from the provider."""

    def get_trading_calendar(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> Sequence[str]:
        """Return trading dates from the provider."""


class RicequantMarketDataRepository(MarketDataRepository):
    """Repository that is ready to work once a client implementation is injected."""

    def __init__(
        self,
        config: RicequantConfig,
        *,
        client: RicequantClientProtocol | None = None,
    ) -> None:
        self._config = config
        self._client = client

    @property
    def config(self) -> RicequantConfig:
        """Return the active provider configuration."""

        return self._config

    @property
    def client(self) -> RicequantClientProtocol | None:
        """Return the injected provider client, if any."""

        return self._client

    def fetch_price_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        client = self._require_client()
        rows = client.get_price_history(
            symbol,
            start_date=start_date,
            end_date=end_date,
        )
        return normalize_price_history_rows(rows)

    def fetch_index_components(
        self,
        index_code: str,
        date: str | None = None,
    ) -> Sequence[str]:
        client = self._require_client()
        return [str(symbol) for symbol in client.get_index_components(index_code, date=date)]

    def fetch_financial_indicators(
        self,
        symbol: str,
        report_date: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        client = self._require_client()
        rows = client.get_financial_indicators(symbol, report_date=report_date)
        return normalize_financial_indicator_rows(rows)

    def fetch_trading_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> Sequence[str]:
        client = self._require_client()
        days = client.get_trading_calendar(
            start_date=start_date,
            end_date=end_date,
        )
        return normalize_trading_calendar(days)

    def _require_client(self) -> RicequantClientProtocol:
        if self._client is None:
            raise NotImplementedError(
                "No Ricequant client is injected yet. "
                "Provide a RicequantClientProtocol implementation to enable runtime calls."
            )
        return self._client



def normalize_price_history_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Normalize provider rows into the phase-1 price-history shape."""

    normalized: list[Mapping[str, Any]] = []
    for row in rows:
        price_date = _pick_first_text(row, ("date", "datetime", "time"))
        if not price_date:
            continue
        close = _to_optional_float(row.get("close"))
        normalized.append(
            {
                "date": price_date[:10],
                "open": _coalesce_float(row.get("open"), close, 0.0),
                "high": _coalesce_float(row.get("high"), close, 0.0),
                "low": _coalesce_float(row.get("low"), close, 0.0),
                "close": _coalesce_float(close, 0.0),
                "volume": _coalesce_float(row.get("volume"), 0.0),
            }
        )
    return normalized



def normalize_financial_indicator_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Normalize financial-indicator rows into plain dict payloads."""

    normalized: list[Mapping[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "report_date": _pick_first_text(row, ("report_date", "date", "end_date")),
                "roe": _to_optional_float(row.get("roe")),
                "roa": _to_optional_float(row.get("roa")),
                "gross_margin": _to_optional_float(
                    row.get("gross_margin") or row.get("gross_profit_margin")
                ),
                "net_margin": _to_optional_float(
                    row.get("net_margin") or row.get("net_profit_margin")
                ),
                "payload": dict(row),
            }
        )
    return normalized



def normalize_trading_calendar(days: Sequence[str]) -> list[str]:
    """Normalize calendar rows into sorted date strings."""

    return sorted(str(day)[:10] for day in days if str(day).strip())



def _pick_first_text(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        return str(value)
    return ""



def _to_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)



def _coalesce_float(*values: Any) -> float:
    for value in values:
        if value in (None, ""):
            continue
        return float(value)
    return 0.0
