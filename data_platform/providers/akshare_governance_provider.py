"""AKShare adapter for the stage-78.1 governance sample datasets."""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode

from .a_share_sqlite_repository import _normalize_symbol
from .akshare_a_share_provider import AkshareAShareProvider


US_INDEX_SINA_SYMBOLS = {
    "SPX": ".INX",
    "IXIC": ".IXIC",
    "DJI": ".DJI",
    "NDX": ".NDX",
}

GLOBAL_INDEX_SINA_SYMBOLS = {
    "FTSE": "英国富时100指数",
    "GDAXI": "德国DAX 30种股价指数",
    "N225": "日经225指数",
}


class AkshareGovernanceProvider(AkshareAShareProvider):
    """Fetch calendar, index and point-in-time context evidence through AKShare."""

    def probe_symbol_catalog(self) -> list[dict[str, Any]]:
        """Read one bounded exchange catalog as a lightweight connectivity probe."""

        frame = self._retry(lambda ak: ak.stock_info_sh_name_code(symbol="主板A股"))
        rows = frame.head(1).to_dict("records")
        return [
            {str(key): _clean_value(value) for key, value in row.items()}
            for row in rows
        ]

    def fetch_trade_calendar(
        self,
        *,
        start_date: str,
        end_date: str,
        market: str = "CN",
    ) -> list[dict[str, Any]]:
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
        if start > end:
            raise ValueError("start_date must not be after end_date")
        frame = self._retry(lambda ak: ak.tool_trade_date_hist_sina())
        open_dates = {
            _date_text(row.get("trade_date"))
            for row in frame.to_dict("records")
        }
        observed_at = _utc_now()
        rows = []
        cursor = start
        while cursor <= end:
            trade_date = cursor.isoformat()
            is_open = trade_date in open_dates
            evidence = {
                "market": market,
                "trade_date": trade_date,
                "is_open": is_open,
                "upstream": "sina",
            }
            rows.append(
                {
                    **evidence,
                    "session_status": "open" if is_open else "closed",
                    "source": "akshare:tool_trade_date_hist_sina",
                    "source_observed_at": observed_at,
                    "source_payload_hash": _record_hash(evidence),
                }
            )
            cursor += timedelta(days=1)
        return rows

    def fetch_index_daily_prices(
        self,
        *,
        index_symbol: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        code = _normalize_symbol(index_symbol)
        try:
            frame = self._retry(
                lambda ak: ak.stock_zh_index_daily(
                    symbol=_index_sina_symbol(code)
                )
            )
            rows = _index_frame_rows(
                frame,
                index_symbol=code,
                start_date=start_date,
                end_date=end_date,
            )
            if rows:
                return rows
        except RuntimeError:
            pass
        return _fetch_index_with_curl(
            index_symbol=code,
            request_gate=self._acquire_request_slot,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_global_index_daily_prices(
        self,
        *,
        index_symbol: str,
        endpoint: str,
        start_date: str,
        end_date: str,
        retry_count: int | None = None,
        retry_delay_seconds: float | None = None,
        request_gate: Any = None,
    ) -> list[dict[str, Any]]:
        """Fetch one explicitly mapped global index through a governed Sina endpoint."""

        code = str(index_symbol or "").strip().upper()
        if endpoint == "index_us_stock_sina":
            upstream_symbol = US_INDEX_SINA_SYMBOLS.get(code)
            if upstream_symbol is None:
                raise ValueError(f"unsupported US Sina index symbol: {code}")
            frame = self._retry_with_policy(
                lambda ak: ak.index_us_stock_sina(symbol=upstream_symbol),
                retry_count=retry_count,
                retry_delay_seconds=retry_delay_seconds,
                request_gate=request_gate,
            )
        elif endpoint == "index_global_hist_sina":
            upstream_symbol = GLOBAL_INDEX_SINA_SYMBOLS.get(code)
            if upstream_symbol is None:
                raise ValueError(f"unsupported global Sina index symbol: {code}")
            frame = self._retry_with_policy(
                lambda ak: ak.index_global_hist_sina(symbol=upstream_symbol),
                retry_count=retry_count,
                retry_delay_seconds=retry_delay_seconds,
                request_gate=request_gate,
            )
        else:
            raise ValueError(f"unsupported global-index endpoint: {endpoint}")
        return _index_frame_rows(
            frame,
            index_symbol=code,
            start_date=start_date,
            end_date=end_date,
            source=f"akshare:{endpoint}:sina",
        )

    def fetch_index_component_snapshot(
        self,
        *,
        index_code: str,
    ) -> dict[str, Any]:
        """Fetch one authoritative latest constituent snapshot from CSI."""

        code = _normalize_symbol(index_code)
        frame = self._retry(lambda ak: ak.index_stock_cons_csindex(symbol=code))
        observed_at = _utc_now()
        records = []
        for values in frame.itertuples(index=False, name=None):
            if len(values) < 9:
                continue
            as_of_date = _date_text(values[0])
            member = _normalize_symbol(str(values[4] or ""))
            if not as_of_date or not member:
                continue
            records.append(
                {
                    "index_code": code,
                    "symbol": member,
                    "as_of_date": as_of_date,
                    "index_name": _clean_value(values[2]),
                    "member_name": _clean_value(values[5]),
                    "exchange": _clean_value(values[7]),
                }
            )
        dates = sorted({str(row["as_of_date"]) for row in records})
        if not records or len(dates) != 1:
            raise RuntimeError(
                f"CSI index snapshot is empty or has mixed dates: {code} {dates}"
            )
        content_hash = _record_hash(
            {"index_code": code, "as_of_date": dates[0], "symbols": sorted(row["symbol"] for row in records)}
        )
        return {
            "index_code": code,
            "as_of_date": dates[0],
            "observed_at": observed_at,
            "source": "akshare:index_stock_cons_csindex:csindex",
            "source_version": content_hash,
            "rows": records,
        }
    def fetch_security_lifecycle_events(
        self,
        *,
        symbol: str,
    ) -> list[dict[str, Any]]:
        code = _normalize_symbol(symbol)
        try:
            company_survey_rows = _fetch_security_lifecycle_from_company_survey(
                code, request_gate=self._acquire_request_slot
            )
            if company_survey_rows:
                return company_survey_rows
        except RuntimeError:
            pass
        try:
            frame = self._retry(lambda ak: ak.stock_individual_info_em(symbol=code))
        except RuntimeError:
            return _fetch_security_lifecycle_with_fallbacks(code, request_gate=self._acquire_request_slot)
        items = {
            str(row.get("item") or ""): _clean_value(row.get("value"))
            for row in frame.to_dict("records")
        }
        listing_date = _date_text(items.get("\u4e0a\u5e02\u65f6\u95f4"))
        if not listing_date:
            return _fetch_security_lifecycle_with_fallbacks(code, request_gate=self._acquire_request_slot)
        observed_at = _utc_now()
        evidence = {
            "symbol": code,
            "event_type": "listed",
            "effective_from": listing_date,
            "name": items.get("\u80a1\u7968\u7b80\u79f0"),
            "upstream_items": items,
        }
        return [
            {
                **evidence,
                "source": "akshare:stock_individual_info_em:eastmoney",
                "source_observed_at": observed_at,
                "source_payload_hash": _record_hash(evidence),
                "evidence": evidence,
            }
        ]

    def fetch_corporate_actions(
        self,
        *,
        symbol: str,
    ) -> list[dict[str, Any]]:
        code = _normalize_symbol(symbol)
        try:
            frame = self._retry(lambda ak: ak.stock_fhps_detail_em(symbol=code))
        except RuntimeError:
            return _fetch_corporate_actions_with_curl(
                code,
                request_gate=self._acquire_request_slot,
            )
        observed_at = _utc_now()
        rows = []
        for source_row in frame.to_dict("records"):
            evidence = {
                str(key): _clean_value(value)
                for key, value in source_row.items()
            }
            rows.append(
                {
                    "symbol": code,
                    "action_type": "distribution",
                    "report_period": _date_text(evidence.get("\u62a5\u544a\u671f")),
                    "announcement_date": _date_text(
                        evidence.get("\u6700\u65b0\u516c\u544a\u65e5\u671f")
                        or evidence.get("\u9884\u6848\u516c\u544a\u65e5")
                    ),
                    "record_date": _date_text(evidence.get("\u80a1\u6743\u767b\u8bb0\u65e5")),
                    "ex_date": _date_text(evidence.get("\u9664\u6743\u9664\u606f\u65e5")),
                    "pay_date": _date_text(evidence.get("\u73b0\u91d1\u5206\u7ea2-\u53d1\u653e\u65e5")),
                    "cash_ratio": _optional_float(
                        evidence.get("\u73b0\u91d1\u5206\u7ea2-\u73b0\u91d1\u5206\u7ea2\u6bd4\u4f8b")
                    ),
                    "bonus_ratio": _optional_float(
                        evidence.get("\u9001\u8f6c\u80a1\u4efd-\u9001\u80a1\u6bd4\u4f8b")
                    ),
                    "transfer_ratio": _optional_float(
                        evidence.get("\u9001\u8f6c\u80a1\u4efd-\u8f6c\u80a1\u6bd4\u4f8b")
                    ),
                    "status": str(evidence.get("\u65b9\u6848\u8fdb\u5ea6") or "unknown"),
                    "source": "akshare:stock_fhps_detail_em:eastmoney",
                    "source_observed_at": observed_at,
                    "source_payload_hash": _record_hash(evidence),
                    "evidence": evidence,
                }
            )
        return rows

    def fetch_suspensions(
        self,
        *,
        trade_date: str,
    ) -> list[dict[str, Any]]:
        frame = self._retry(
            lambda ak: ak.stock_tfp_em(date=str(trade_date).replace("-", ""))
        )
        observed_at = _utc_now()
        target_date = _date_text(trade_date)
        rows = []
        for source_row in frame.to_dict("records"):
            evidence = {
                str(key): _clean_value(value)
                for key, value in source_row.items()
            }
            symbol = _normalize_symbol(str(evidence.get("\u4ee3\u7801") or ""))
            suspension_start = _date_text(evidence.get("\u505c\u724c\u65f6\u95f4"))
            suspension_end = _date_text(evidence.get("\u505c\u724c\u622a\u6b62\u65f6\u95f4"))
            expected_resume = _date_text(evidence.get("\u9884\u8ba1\u590d\u724c\u65f6\u95f4"))
            if not target_date or not suspension_start:
                continue
            if target_date < suspension_start:
                continue
            if suspension_end and target_date > suspension_end:
                continue
            if expected_resume and target_date >= expected_resume:
                continue
            evidence["source_suspension_start_date"] = suspension_start
            evidence["source_suspension_end_date"] = suspension_end
            evidence["normalized_status_trade_date"] = target_date
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": target_date,
                    "status": "suspended",
                    "is_tradable": False,
                    "suspension_reason": evidence.get("\u505c\u724c\u539f\u56e0"),
                    "expected_resume_date": expected_resume,
                    "source": "akshare:stock_tfp_em:eastmoney",
                    "source_observed_at": observed_at,
                    "source_payload_hash": _record_hash(evidence),
                    "evidence": evidence,
                }
            )
        return [row for row in rows if row["symbol"] and row["trade_date"]]


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text in {"", "NaT", "nan", "None", "--"}:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _date_text(value: Any) -> str | None:
    cleaned = _clean_value(value)
    if cleaned is None:
        return None
    text = str(cleaned).strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _optional_float(value: Any) -> float | None:
    cleaned = _clean_value(value)
    if cleaned is None:
        return None
    return float(cleaned)


def _record_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _curl_json(url: str, *, max_time: int, request_gate: Any = None) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            if request_gate is not None:
                request_gate()
            completed = subprocess.run(
                [
                    "curl.exe", "-sS", "-L", "--noproxy", "*",
                    "--max-time", str(max_time), url,
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=max_time + 5,
            )
            payload = json.loads(completed.stdout)
            if isinstance(payload, dict):
                return payload
            raise RuntimeError("curl endpoint returned a non-object payload")
        except Exception as error:
            last_error = error
            if attempt < 3:
                time.sleep(float(attempt))
    assert last_error is not None
    raise RuntimeError(
        f"curl endpoint failed after 3 attempts: {type(last_error).__name__}: {last_error}"
    ) from last_error

def _fetch_security_lifecycle_with_curl(symbol: str, *, request_gate: Any = None) -> list[dict[str, Any]]:
    market_id = "1" if symbol.startswith("6") else "0"
    params = {
        "secid": f"{market_id}.{symbol}",
        "fields": "f57,f58,f84,f85,f116,f117,f127,f189",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    url = "https://push2.eastmoney.com/api/qt/stock/get?" + urlencode(params)
    payload = _curl_json(url, max_time=30, request_gate=request_gate)

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError(f"Eastmoney security-info fallback returned no data for {symbol}")
    listing_date = _date_text(data.get("f189"))
    if not listing_date:
        return []
    observed_at = _utc_now()
    evidence = {
        "symbol": symbol,
        "event_type": "listed",
        "effective_from": listing_date,
        "name": data.get("f58"),
        "industry": data.get("f127"),
        "upstream_fields": data,
    }
    return [
        {
            **evidence,
            "source": "curl:stock_individual_info:eastmoney",
            "source_observed_at": observed_at,
            "source_payload_hash": _record_hash(evidence),
            "evidence": evidence,
        }
    ]

def _fetch_corporate_actions_with_curl(
    symbol: str,
    *,
    request_gate: Any = None,
) -> list[dict[str, Any]]:
    params = {
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "pageSize": "500",
        "pageNumber": "1",
        "reportName": "RPT_SHAREBONUS_DET",
        "columns": "ALL",
        "quoteColumns": "",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(SECURITY_CODE="{symbol}")',
    }
    url = (
        "https://datacenter-web.eastmoney.com/api/data/v1/get?"
        + urlencode(params)
    )
    payload = _curl_json(url, max_time=30, request_gate=request_gate)
    result = payload.get("result") if isinstance(payload, dict) else None
    if result is None:
        if int(payload.get("code") or 0) == 9201:
            return []
        raise RuntimeError(
            f"Eastmoney corporate-action fallback failed: "
            f"code={payload.get('code')} message={payload.get('message')}"
        )
    source_rows = result.get("data") if isinstance(result, dict) else None
    if not isinstance(source_rows, list):
        raise RuntimeError("Eastmoney corporate-action fallback returned invalid data")
    observed_at = _utc_now()
    rows = []
    for source_row in source_rows:
        evidence = {
            str(key): _clean_value(value)
            for key, value in dict(source_row).items()
        }
        rows.append({
            "symbol": symbol,
            "action_type": "distribution",
            "report_period": _date_text(evidence.get("REPORT_DATE")),
            "announcement_date": _date_text(
                evidence.get("NOTICE_DATE") or evidence.get("PLAN_NOTICE_DATE")
            ),
            "record_date": _date_text(evidence.get("EQUITY_RECORD_DATE")),
            "ex_date": _date_text(evidence.get("EX_DIVIDEND_DATE")),
            "pay_date": _date_text(evidence.get("PAY_DATE")),
            "cash_ratio": _optional_float(evidence.get("PRETAX_BONUS_RMB")),
            "bonus_ratio": _optional_float(evidence.get("BONUS_RATIO")),
            "transfer_ratio": _optional_float(evidence.get("IT_RATIO")),
            "status": str(evidence.get("ASSIGN_PROGRESS") or "unknown"),
            "source": "curl:RPT_SHAREBONUS_DET:eastmoney",
            "source_observed_at": observed_at,
            "source_payload_hash": _record_hash(evidence),
            "evidence": evidence,
        })
    return rows
def _fetch_security_lifecycle_with_fallbacks(
    symbol: str,
    *,
    request_gate: Any = None,
) -> list[dict[str, Any]]:
    """Try the quote endpoint first, then the company-survey endpoint."""
    try:
        return _fetch_security_lifecycle_with_curl(symbol, request_gate=request_gate)
    except RuntimeError:
        return _fetch_security_lifecycle_from_company_survey(
            symbol, request_gate=request_gate
        )


def _fetch_security_lifecycle_from_company_survey(
    symbol: str,
    *,
    request_gate: Any = None,
) -> list[dict[str, Any]]:
    prefix = (
        "SH" if symbol.startswith("6") else
        "BJ" if symbol.startswith(("4", "8", "9")) else "SZ"
    )
    url = (
        "https://emweb.securities.eastmoney.com/"
        "PC_HSF10/CompanySurvey/PageAjax?"
        + urlencode({"code": f"{prefix}{symbol}"})
    )
    payload = _curl_json(url, max_time=30, request_gate=request_gate)
    issue_rows = payload.get("fxxg") if isinstance(payload, dict) else None
    listing = issue_rows[0] if isinstance(issue_rows, list) and issue_rows else {}
    listing_date = _date_text(listing.get("LISTING_DATE"))
    if not listing_date:
        return []
    profile_rows = payload.get("jbzl") if isinstance(payload, dict) else None
    profile = profile_rows[0] if isinstance(profile_rows, list) and profile_rows else {}
    observed_at = _utc_now()
    evidence = {
        "symbol": symbol,
        "event_type": "listed",
        "effective_from": listing_date,
        "name": profile.get("SECURITY_NAME_ABBR"),
        "market": profile.get("TRADE_MARKET"),
        "upstream_fields": {
            "SECUCODE": listing.get("SECUCODE"),
            "LISTING_DATE": listing.get("LISTING_DATE"),
            "ONLINE_ISSUE_DATE": listing.get("ONLINE_ISSUE_DATE"),
            "FOUND_DATE": listing.get("FOUND_DATE"),
        },
    }
    return [{
        **evidence,
        "source": "curl:company_survey:eastmoney",
        "source_observed_at": observed_at,
        "source_payload_hash": _record_hash(evidence),
        "evidence": evidence,
    }]
def _index_sina_symbol(index_symbol: str) -> str:
    code = str(index_symbol).split(".")[0].strip()
    prefix = "sz" if code.startswith("399") else "bj" if code.startswith("899") else "sh"
    return f"{prefix}{code}"


def _index_frame_rows(
    frame: Any,
    *,
    index_symbol: str,
    start_date: str,
    end_date: str,
    source: str = "akshare:stock_zh_index_daily:sina",
) -> list[dict[str, Any]]:
    observed_at = _utc_now()
    rows = []
    for source_row in frame.to_dict("records"):
        trade_date = _date_text(source_row.get("date"))
        if not trade_date or trade_date < str(start_date) or trade_date > str(end_date):
            continue
        evidence = {
            "index_symbol": index_symbol,
            "trade_date": trade_date,
            "open": _optional_float(source_row.get("open")),
            "high": _optional_float(source_row.get("high")),
            "low": _optional_float(source_row.get("low")),
            "close": _optional_float(source_row.get("close")),
            "volume": _optional_float(source_row.get("volume")),
            "amount": _optional_float(source_row.get("amount")),
        }
        rows.append({
            **evidence,
            "source": source,
            "source_observed_at": observed_at,
            "source_payload_hash": _record_hash(evidence),
        })
    return rows

def _fetch_index_with_curl(
    *,
    index_symbol: str,
    start_date: str,
    end_date: str,
    request_gate: Any = None,
) -> list[dict[str, Any]]:
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": "101",
        "fqt": "0",
        "secid": f"{_index_market_id(index_symbol)}.{index_symbol}",
        "beg": str(start_date).replace("-", ""),
        "end": str(end_date).replace("-", ""),
        "lmt": "1000000",
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(params)
    payload = _curl_json(url, max_time=60, request_gate=request_gate)

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("Eastmoney index curl fallback returned no data")
    observed_at = _utc_now()
    rows = []
    for line in data.get("klines") or []:
        values = str(line).split(",")
        if len(values) < 6:
            continue
        evidence = {
            "index_symbol": index_symbol,
            "trade_date": values[0],
            "open": float(values[1]),
            "close": float(values[2]),
            "high": float(values[3]),
            "low": float(values[4]),
            "volume": float(values[5]),
            "amount": float(values[6]) if len(values) > 6 else None,
        }
        rows.append(
            {
                **evidence,
                "source": "curl:index_zh_a_hist:eastmoney",
                "source_observed_at": observed_at,
                "source_payload_hash": _record_hash(evidence),
            }
        )
    return rows

def _index_market_id(index_symbol: str) -> str:
    """Map Eastmoney index codes to their quote-market identifier."""

    code = str(index_symbol).split(".")[0].strip()
    return "0" if code.startswith(("399", "899")) else "1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
