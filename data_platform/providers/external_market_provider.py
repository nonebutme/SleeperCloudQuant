"""Open external market-data provider gateway with safe fallback semantics."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from data_platform.providers.ricequant_repository import normalize_price_history_rows, normalize_trading_calendar
from data_platform.repository.contracts import MarketDataRepository

DEFAULT_FIELD_MAPPING = {
    "date": ["date", "trade_date", "datetime", "time"],
    "open": ["open", "open_price", "openPrice"],
    "high": ["high", "high_price", "highPrice"],
    "low": ["low", "low_price", "lowPrice"],
    "close": ["close", "close_price", "closePrice"],
    "volume": ["volume", "vol", "turnover_volume"],
}
DEFAULT_ENDPOINT_SPEC = {
    "price_history_path": "/price-history",
    "price_history_rows_path": "rows",
    "trading_calendar_path": "/trading-calendar",
    "trading_calendar_days_path": "days",
    "index_components_path": "/index-components",
    "index_components_path_in_payload": "components",
    "financial_indicators_path": "/financial-indicators",
    "financial_indicators_rows_path": "rows",
    "field_mapping": DEFAULT_FIELD_MAPPING,
    "pagination": {
        "enabled": False,
        "page_param": "page",
        "page_size_param": "page_size",
        "page_size": 200,
        "next_cursor_path": "next_cursor",
        "next_cursor_param": "cursor",
        "max_pages": 1,
    },
    "retry": {"max_attempts": 1},
}


class ExternalMarketProviderRepository(MarketDataRepository):
    """Read OHLCV rows from a configurable HTTP market provider when configured."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        provider_name: str | None = None,
        timeout_seconds: float | int | str | None = None,
        enabled: bool | None = None,
        api_key: str | None = None,
        endpoint_spec: Mapping[str, Any] | None = None,
    ) -> None:
        configured_base_url = base_url if base_url is not None else os.environ.get("SCQ_MARKET_PROVIDER_BASE_URL")
        configured_provider = provider_name if provider_name is not None else os.environ.get("SCQ_MARKET_PROVIDER_NAME")
        configured_timeout = timeout_seconds if timeout_seconds is not None else os.environ.get("SCQ_MARKET_PROVIDER_TIMEOUT_SECONDS")
        self._base_url = (configured_base_url or "").rstrip("/")
        self._api_key = api_key if api_key is not None else os.environ.get("SCQ_MARKET_PROVIDER_API_KEY") or ""
        self._provider = configured_provider or "open-http-market-provider"
        self._enabled_intent = True if enabled is None else bool(enabled)
        self._endpoint_spec = _normalize_endpoint_spec(endpoint_spec)
        self._last_call: dict[str, Any] | None = None
        try:
            self._timeout = float(configured_timeout or 8.0)
        except (TypeError, ValueError):
            self._timeout = 8.0

    def provider_status(self) -> dict[str, Any]:
        missing = []
        if not self._base_url:
            missing.append("SCQ_MARKET_PROVIDER_BASE_URL")
        if not self._api_key:
            missing.append("SCQ_MARKET_PROVIDER_API_KEY")
        enabled = self._enabled_intent and not missing
        status = "configured" if enabled else ("disabled_by_config" if not self._enabled_intent else "fallback_to_local_sqlite")
        return {
            "provider": self._provider,
            "enabled": enabled,
            "enabled_intent": self._enabled_intent,
            "status": status,
            "missing": missing,
            "base_url_configured": bool(self._base_url),
            "api_key_configured": bool(self._api_key),
            "timeout_seconds": self._timeout,
            "endpoint_spec": _public_endpoint_spec(self._endpoint_spec),
            "last_call": dict(self._last_call or {}),
            "secret_policy": "API keys are read from environment variables and are never persisted in payloads.",
        }

    def fetch_price_history(self, symbol: str, start_date: str | None = None, end_date: str | None = None) -> Sequence[Mapping[str, Any]]:
        path = str(self._endpoint_spec["price_history_path"])
        if not self._is_enabled(path):
            return []
        rows = self._fetch_rows(
            path=path,
            query={"symbol": symbol, "start_date": start_date or "", "end_date": end_date or ""},
            rows_path=str(self._endpoint_spec["price_history_rows_path"]),
        )
        normalized_rows = normalize_price_history_rows([self._map_price_row(row) for row in rows])
        self._mark_row_count(len(normalized_rows))
        return normalized_rows

    def fetch_index_components(self, index_code: str, date: str | None = None) -> Sequence[str]:
        path = str(self._endpoint_spec["index_components_path"])
        if not self._is_enabled(path):
            return []
        rows = self._fetch_rows(
            path=path,
            query={"index_code": index_code, "date": date or ""},
            rows_path=str(self._endpoint_spec["index_components_path_in_payload"]),
        )
        components = [str(item) for item in rows or []]
        self._mark_row_count(len(components))
        return components

    def fetch_financial_indicators(self, symbol: str, report_date: str | None = None) -> Sequence[Mapping[str, Any]]:
        path = str(self._endpoint_spec["financial_indicators_path"])
        if not self._is_enabled(path):
            return []
        rows = self._fetch_rows(
            path=path,
            query={"symbol": symbol, "report_date": report_date or ""},
            rows_path=str(self._endpoint_spec["financial_indicators_rows_path"]),
        )
        indicators = [dict(item) for item in rows if isinstance(item, Mapping)]
        self._mark_row_count(len(indicators))
        return indicators

    def fetch_trading_calendar(self, start_date: str, end_date: str) -> Sequence[str]:
        path = str(self._endpoint_spec["trading_calendar_path"])
        if not self._is_enabled(path):
            return []
        rows = self._fetch_rows(
            path=path,
            query={"start_date": start_date, "end_date": end_date},
            rows_path=str(self._endpoint_spec["trading_calendar_days_path"]),
        )
        days = normalize_trading_calendar(list(rows or []))
        self._mark_row_count(len(days))
        return days

    def _is_enabled(self, path: str) -> bool:
        status = self.provider_status()
        if status["enabled"]:
            return True
        self._record_call(path=path, status="skipped", reason=status["status"], missing=status["missing"])
        return False

    def _fetch_rows(self, *, path: str, query: Mapping[str, str], rows_path: str) -> list[Any]:
        pagination = self._endpoint_spec["pagination"]
        max_pages = int(pagination.get("max_pages") or 1)
        max_pages = max(1, min(max_pages, 50))
        rows: list[Any] = []
        cursor = ""
        page_count = 0
        for page_number in range(1, max_pages + 1):
            page_query = dict(query)
            if pagination.get("enabled"):
                page_query[str(pagination["page_param"])] = str(page_number)
                page_query[str(pagination["page_size_param"])] = str(pagination["page_size"])
                if cursor:
                    page_query[str(pagination["next_cursor_param"])] = cursor
            payload = self._get_json(path, page_query)
            if not payload:
                break
            page_count += 1
            page_rows = _extract_path(payload, rows_path)
            if page_rows is None and isinstance(payload, list):
                page_rows = payload
            if isinstance(page_rows, list):
                rows.extend(page_rows)
            elif page_rows is not None:
                rows.append(page_rows)
            next_cursor = _extract_path(payload, str(pagination["next_cursor_path"]))
            cursor = str(next_cursor or "")
            if not pagination.get("enabled") or not cursor:
                break
        if self._last_call is not None:
            self._last_call["page_count"] = page_count
            self._last_call["pagination_enabled"] = bool(pagination.get("enabled"))
        return rows

    def _get_json(self, path: str, query: Mapping[str, str]) -> Any:
        retry = self._endpoint_spec["retry"]
        max_attempts = max(1, min(int(retry.get("max_attempts") or 1), 5))
        safe_query = {key: value for key, value in query.items() if value}
        for attempt in range(1, max_attempts + 1):
            payload = self._request_json_once(path=path, query=safe_query, attempt=attempt)
            if payload is not None:
                return payload
            if self._last_call and self._last_call.get("status") in {"http_error", "decode_error"}:
                break
        return {}

    def _request_json_once(self, *, path: str, query: Mapping[str, str], attempt: int) -> Any | None:
        encoded_query = urllib.parse.urlencode({key: value for key, value in query.items() if value})
        url = f"{self._base_url}{path}?{encoded_query}" if encoded_query else f"{self._base_url}{path}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
                "User-Agent": "SleeperCloudQuant/Stage28",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # nosec - user-configured endpoint
                payload = json.loads(response.read().decode("utf-8"))
                self._record_call(
                    path=path,
                    status="success",
                    reason="provider_response",
                    status_code=getattr(response, "status", None),
                    query=query,
                    attempt=attempt,
                )
                return payload
        except urllib.error.HTTPError as error:
            self._record_call(path=path, status="http_error", reason=str(error.reason or error), status_code=error.code, query=query, attempt=attempt)
        except urllib.error.URLError as error:
            self._record_call(path=path, status="network_error", reason=str(error.reason or error), query=query, attempt=attempt)
        except TimeoutError as error:
            self._record_call(path=path, status="timeout", reason=str(error), query=query, attempt=attempt)
        except json.JSONDecodeError as error:
            self._record_call(path=path, status="decode_error", reason=str(error), query=query, attempt=attempt)
        except Exception as error:  # pragma: no cover - keeps fallback path observable for unexpected provider failures.
            self._record_call(path=path, status="request_failed", reason=type(error).__name__, query=query, attempt=attempt)
        return None

    def _map_price_row(self, row: Any) -> dict[str, Any]:
        if not isinstance(row, Mapping):
            return {}
        mapping = self._endpoint_spec["field_mapping"]
        return {target: _first_present(row, aliases) for target, aliases in mapping.items()}

    def _mark_row_count(self, row_count: int) -> None:
        if self._last_call is not None:
            self._last_call["row_count"] = row_count
            if self._last_call.get("status") == "success" and row_count == 0:
                self._last_call["reason"] = "empty_provider_response"

    def _record_call(self, *, path: str, status: str, reason: str, **extra: Any) -> None:
        self._last_call = {
            "provider": self._provider,
            "path": path,
            "status": status,
            "reason": reason,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **{key: value for key, value in extra.items() if value not in (None, "")},
        }


def _normalize_endpoint_spec(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    spec = dict(DEFAULT_ENDPOINT_SPEC)
    for key in (
        "price_history_path",
        "price_history_rows_path",
        "trading_calendar_path",
        "trading_calendar_days_path",
        "index_components_path",
        "index_components_path_in_payload",
        "financial_indicators_path",
        "financial_indicators_rows_path",
    ):
        if raw.get(key):
            spec[key] = str(raw[key])
    spec["field_mapping"] = _normalize_field_mapping(raw.get("field_mapping"))
    spec["pagination"] = _normalize_pagination(raw.get("pagination"))
    spec["retry"] = _normalize_retry(raw.get("retry"))
    return spec


def _normalize_field_mapping(value: Any) -> dict[str, list[str]]:
    raw = value if isinstance(value, Mapping) else {}
    mapping: dict[str, list[str]] = {}
    for target, default_aliases in DEFAULT_FIELD_MAPPING.items():
        aliases = raw.get(target)
        if isinstance(aliases, str):
            parsed = [item.strip() for item in aliases.split(",") if item.strip()]
        elif isinstance(aliases, list):
            parsed = [str(item).strip() for item in aliases if str(item).strip()]
        else:
            parsed = []
        mapping[target] = parsed or list(default_aliases)
    return mapping


def _normalize_pagination(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    try:
        page_size = int(raw.get("page_size", 200))
    except (TypeError, ValueError):
        page_size = 200
    try:
        max_pages = int(raw.get("max_pages", 1))
    except (TypeError, ValueError):
        max_pages = 1
    return {
        "enabled": bool(raw.get("enabled", False)),
        "page_param": str(raw.get("page_param") or "page"),
        "page_size_param": str(raw.get("page_size_param") or "page_size"),
        "page_size": max(1, min(page_size, 5000)),
        "next_cursor_path": str(raw.get("next_cursor_path") or "next_cursor"),
        "next_cursor_param": str(raw.get("next_cursor_param") or "cursor"),
        "max_pages": max(1, min(max_pages, 50)),
    }


def _normalize_retry(value: Any) -> dict[str, int]:
    raw = value if isinstance(value, Mapping) else {}
    try:
        max_attempts = int(raw.get("max_attempts", 1))
    except (TypeError, ValueError):
        max_attempts = 1
    return {"max_attempts": max(1, min(max_attempts, 5))}


def _public_endpoint_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "price_history_path": spec.get("price_history_path"),
        "price_history_rows_path": spec.get("price_history_rows_path"),
        "trading_calendar_path": spec.get("trading_calendar_path"),
        "trading_calendar_days_path": spec.get("trading_calendar_days_path"),
        "field_mapping": spec.get("field_mapping"),
        "pagination": spec.get("pagination"),
        "retry": spec.get("retry"),
    }


def _extract_path(payload: Any, path: str) -> Any:
    if path in {"", "."}:
        return payload
    current = payload
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
        else:
            return None
    return current


def _first_present(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return None
