"""AKShare adapter with retry and local proxy discovery for A-share data."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlencode

from data_platform.providers.a_share_sqlite_repository import (
    _normalize_adjustment,
    _normalize_symbol,
)
from data_platform.storage.a_share_market_store import AShareMarketStore

COLUMN_MAP = {
    "\u65e5\u671f": "date",
    "\u5f00\u76d8": "open",
    "\u6536\u76d8": "close",
    "\u6700\u9ad8": "high",
    "\u6700\u4f4e": "low",
    "\u6210\u4ea4\u91cf": "volume",
    "\u6210\u4ea4\u989d": "amount",
    "\u632f\u5e45": "amplitude",
    "\u6da8\u8dcc\u5e45": "change_pct",
    "\u6da8\u8dcc\u989d": "change_amount",
    "\u6362\u624b\u7387": "turnover_rate",
}


class AkshareAShareProvider:
    """Fetch current A-share metadata and daily bars through AKShare."""

    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        retry_count: int = 4,
        retry_delay_seconds: float = 2.0,
        request_gate: Callable[[], None] | None = None,
    ) -> None:
        self.proxy_url = proxy_url or discover_proxy_url()
        self.retry_count = max(1, int(retry_count))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))
        self.request_gate = request_gate

    def list_symbols(self) -> list[dict[str, Any]]:
        frame = self._retry(lambda ak: ak.stock_info_a_code_name())
        return [
            {
                "symbol": _normalize_symbol(str(row.get("code") or "")),
                "name": str(row.get("name") or ""),
                "listing_status": "current",
                "source": "akshare",
            }
            for row in frame.to_dict("records")
        ]

    def fetch_daily_prices(
        self,
        *,
        symbol: str,
        adjustment: str = "raw",
        start_date: str,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        code = _normalize_symbol(symbol)
        mode = _normalize_adjustment(adjustment)
        adjust = "" if mode == "raw" else mode
        finish = str(end_date or date.today().isoformat()).replace("-", "")
        begin = str(start_date).replace("-", "")
        if not _env_truthy(os.environ.get("SCQ_AKSHARE_INPROCESS_ENABLED", "")):
            self._acquire_request_slot()
            return _fetch_eastmoney_with_curl(
                symbol=code,
                adjustment=mode,
                start_date=begin,
                end_date=finish,
            )
        if code == "689009":
            return self._fetch_cdr_daily(
                adjustment=mode,
                start_date=begin,
                end_date=finish,
            )
        try:
            return self._fetch_sina_daily(
                symbol=code,
                adjustment=mode,
                start_date=begin,
                end_date=finish,
            )
        except RuntimeError:
            pass
        try:
            frame = self._retry(
                lambda ak: ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=begin,
                    end_date=finish,
                    adjust=adjust,
                )
            )
            return _normalize_frame_rows(frame, code)
        except RuntimeError as akshare_error:
            try:
                self._acquire_request_slot()
                return _fetch_eastmoney_with_curl(
                    symbol=code,
                    adjustment=mode,
                    start_date=begin,
                    end_date=finish,
                )
            except Exception as fallback_error:
                raise RuntimeError(
                    f"{akshare_error}; curl fallback failed: "
                    f"{type(fallback_error).__name__}: {fallback_error}"
                ) from fallback_error

    def _fetch_cdr_daily(
        self,
        *,
        adjustment: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        requested_start = datetime.strptime(start_date, "%Y%m%d").date()
        buffered_start = (requested_start - timedelta(days=10)).strftime("%Y%m%d")
        raw_frame = self._retry_direct(
            lambda ak: ak.stock_zh_a_cdr_daily(
                symbol="sh689009",
                start_date=buffered_start,
                end_date=end_date,
            )
        )
        raw_records = {
            str(row.get("date") or ""): row
            for row in raw_frame.to_dict("records")
        }
        if adjustment == "raw":
            records = list(raw_records.values())
        else:
            adjusted_frame = self._retry_direct(
                lambda ak: ak.stock_zh_a_hist_tx(
                    symbol="sh689009",
                    start_date=buffered_start,
                    end_date=end_date,
                    adjust=adjustment,
                )
            )
            records = []
            for adjusted in adjusted_frame.to_dict("records"):
                trade_date = str(adjusted.get("date") or "")
                raw = raw_records.get(trade_date, {})
                records.append({
                    **adjusted,
                    "volume": raw.get("volume"),
                    "amount": raw.get("amount"),
                })
        return _normalize_market_records(
            records,
            "689009",
            requested_start.isoformat(),
            volume_divisor=1.0,
        )
    def _fetch_sina_daily(
        self,
        *,
        symbol: str,
        adjustment: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        requested_start = datetime.strptime(start_date, "%Y%m%d").date()
        buffered_start = (requested_start - timedelta(days=10)).strftime("%Y%m%d")
        prefix = "bj" if symbol.startswith(("4", "8", "9")) else ("sh" if symbol.startswith("6") else "sz")
        market_symbol = prefix + symbol
        adjust = "" if adjustment == "raw" else adjustment
        frame = self._retry_direct(
            lambda ak: ak.stock_zh_a_daily(
                symbol=market_symbol,
                start_date=buffered_start,
                end_date=end_date,
                adjust=adjust,
            )
        )
        return _normalize_sina_rows(frame, symbol, requested_start.isoformat())

    def _retry_direct(self, operation: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                self._acquire_request_slot()
                with direct_network_environment():
                    import akshare as ak

                    return operation(ak)
            except Exception as error:
                last_error = error
                if attempt < self.retry_count:
                    time.sleep(self.retry_delay_seconds * attempt)
        assert last_error is not None
        raise RuntimeError(
            f"AKShare direct request failed after {self.retry_count} attempts: "
            f"{type(last_error).__name__}: {last_error}"
        ) from last_error
    def sync_symbol(
        self,
        store: AShareMarketStore,
        *,
        symbol: str,
        adjustment: str,
        start_date: str,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        mode = _normalize_adjustment(adjustment)
        rows = self.fetch_daily_prices(
            symbol=symbol, adjustment=mode,
            start_date=start_date, end_date=end_date,
        )
        fallback_rows: list[dict[str, Any]] = []
        fallback_error = ""
        requested_start = date.fromisoformat(str(start_date)).isoformat()
        returned_dates = {
            str(row.get("date") or row.get("trade_date") or "") for row in rows
        }
        if requested_start not in returned_dates:
            reference_modes = ("qfq", "hfq") if mode == "raw" else ("raw",)
            has_reference = any(
                int(store.fetch_daily_prices(
                    symbol=symbol, adjustment=reference_mode,
                    start_date=requested_start, end_date=requested_start, limit=1,
                ).get("total") or 0) > 0
                for reference_mode in reference_modes
            )
            if has_reference:
                begin = requested_start.replace("-", "")
                finish = str(end_date or date.today().isoformat()).replace("-", "")
                try:
                    frame = self._retry(
                        lambda ak: ak.stock_zh_a_hist(
                            symbol=_normalize_symbol(symbol), period="daily",
                            start_date=begin, end_date=finish, adjust=mode,
                        )
                    )
                    fallback = _normalize_frame_rows(frame, _normalize_symbol(symbol))
                except RuntimeError as akshare_error:
                    try:
                        self._acquire_request_slot()
                        fallback = _fetch_eastmoney_with_curl(
                            symbol=_normalize_symbol(symbol), adjustment=mode,
                            start_date=begin, end_date=finish,
                        )
                    except Exception as curl_error:
                        fallback = []
                        fallback_error = (
                            f"akshare={akshare_error}; "
                            f"curl={type(curl_error).__name__}: {curl_error}"
                        )
                fallback_rows = [
                    row for row in fallback
                    if str(row.get("date") or row.get("trade_date") or "") not in returned_dates
                ]
        written = store.upsert_daily_prices(
            rows, adjustment=mode, source="akshare",
        )
        if fallback_rows:
            written += store.upsert_daily_prices(
                fallback_rows, adjustment=mode,
                source="akshare_eastmoney_boundary_fallback",
            )
        return {
            "status": "completed",
            "provider": "akshare",
            "symbol": _normalize_symbol(symbol),
            "adjustment": mode,
            "start_date": start_date,
            "end_date": end_date or date.today().isoformat(),
            "rows_received": len(rows) + len(fallback_rows),
            "rows_written": written,
            "boundary_fallback_rows": len(fallback_rows),
            "boundary_fallback_error": fallback_error,
            "history_transport_policy": (
                "eastmoney_curl_default_akshare_inprocess_opt_in"
            ),
            "catalog_proxy": self.proxy_url or "",
        }

    def _acquire_request_slot(self) -> None:
        if self.request_gate is not None:
            self.request_gate()

    def _retry(self, operation: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                self._acquire_request_slot()
                with proxy_environment(self.proxy_url):
                    import akshare as ak

                    return operation(ak)
            except Exception as error:
                last_error = error
                if attempt < self.retry_count:
                    time.sleep(self.retry_delay_seconds * attempt)
        assert last_error is not None
        raise RuntimeError(
            f"AKShare request failed after {self.retry_count} attempts: "
            f"{type(last_error).__name__}: {last_error}"
        ) from last_error


def _normalize_frame_rows(frame: Any, symbol: str) -> list[dict[str, Any]]:
    rows = []
    for source_row in frame.to_dict("records"):
        row = {target: source_row.get(source) for source, target in COLUMN_MAP.items()}
        row["symbol"] = symbol
        if row.get("date") is not None:
            row["date"] = str(row["date"])
        rows.append(row)
    return rows


def _normalize_sina_rows(
    frame: Any,
    symbol: str,
    requested_start: str,
) -> list[dict[str, Any]]:
    return _normalize_market_records(
        frame.to_dict("records"),
        symbol,
        requested_start,
        volume_divisor=100.0,
    )


def _normalize_market_records(
    source_records: list[dict[str, Any]],
    symbol: str,
    requested_start: str,
    *,
    volume_divisor: float,
) -> list[dict[str, Any]]:
    records = sorted(source_records, key=lambda row: str(row.get("date") or ""))
    rows = []
    previous_close: float | None = None
    for source_row in records:
        trade_date = str(source_row.get("date") or "")
        close = _optional_float(source_row.get("close"))
        high = _optional_float(source_row.get("high"))
        low = _optional_float(source_row.get("low"))
        change_amount = close - previous_close if close is not None and previous_close else None
        change_pct = change_amount / previous_close * 100 if change_amount is not None else None
        amplitude = (
            (high - low) / previous_close * 100
            if high is not None and low is not None and previous_close
            else None
        )
        turnover = _optional_float(source_row.get("turnover"))
        row = {
            "symbol": symbol,
            "date": trade_date,
            "open": source_row.get("open"),
            "close": source_row.get("close"),
            "high": source_row.get("high"),
            "low": source_row.get("low"),
            "volume": (
                _optional_float(source_row.get("volume")) / volume_divisor
                if _optional_float(source_row.get("volume")) is not None
                else None
            ),
            "amount": source_row.get("amount"),
            "amplitude": amplitude,
            "change_pct": change_pct,
            "change_amount": change_amount,
            "turnover_rate": turnover * 100 if turnover is not None else None,
        }
        previous_close = close
        if trade_date >= requested_start:
            rows.append(row)
    return rows


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if number != number else number


def _env_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def _fetch_eastmoney_with_curl(
    *,
    symbol: str,
    adjustment: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    market_id = "1" if symbol.startswith("6") else "0"
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": "101",
        "fqt": {"raw": "0", "qfq": "1", "hfq": "2"}[adjustment],
        "secid": f"{market_id}.{symbol}",
        "beg": start_date,
        "end": end_date,
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(params)
    completed = subprocess.run(
        ["curl.exe", "-sS", "-L", "--noproxy", "*", "--max-time", "30", url],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=35,
    )
    payload = json.loads(completed.stdout)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError(f"Eastmoney returned no data: rc={payload.get('rc') if isinstance(payload, dict) else 'invalid'}")
    rows = []
    for line in data.get("klines") or []:
        values = str(line).split(",")
        if len(values) < 11:
            raise RuntimeError(f"Eastmoney returned malformed kline: {line}")
        rows.append({
            "symbol": symbol,
            "date": values[0],
            "open": values[1],
            "close": values[2],
            "high": values[3],
            "low": values[4],
            "volume": values[5],
            "amount": values[6],
            "amplitude": values[7],
            "change_pct": values[8],
            "change_amount": values[9],
            "turnover_rate": values[10],
        })
    return rows

def discover_proxy_url() -> str | None:
    configured = os.environ.get("SCQ_AKSHARE_PROXY")
    if configured:
        return configured
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(name):
            return os.environ[name]
    clash_config = (
        Path.home()
        / "AppData"
        / "Roaming"
        / "io.github.clash-verge-rev.clash-verge-rev"
        / "config.yaml"
    )
    if not clash_config.is_file():
        return None
    try:
        text = clash_config.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"(?m)^\s*mixed-port:\s*(\d+)\s*$", text)
    if not match:
        match = re.search(r"(?m)^\s*port:\s*(\d+)\s*$", text)
    return f"http://127.0.0.1:{match.group(1)}" if match else None


@contextmanager
def direct_network_environment() -> Iterator[None]:
    names = (
        "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
        "ALL_PROXY", "all_proxy",
    )
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ.pop(name, None)
        yield
    finally:
        for name, value in previous.items():
            if value is not None:
                os.environ[name] = value

@contextmanager
def proxy_environment(proxy_url: str | None) -> Iterator[None]:
    if not proxy_url:
        yield
        return
    names = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ[name] = proxy_url
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
