"""Bounded CNInfo client for noncommercial local research."""

from __future__ import annotations

import base64
import threading
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping


from data_platform.providers.bounded_curl_transport import (
    BoundedCurlJsonTransport,
    CurlTransportError,
)

_AES_KEY = b"1234567887654321"
_WEBAPI_ROOT = "https://webapi.cninfo.com.cn/api/stock"
_DISCLOSURE_ROOT = "https://www.cninfo.com.cn/new"
_INDUSTRY_TYPES = {
    "证监会行业分类标准": "008001",
    "巨潮行业分类标准": "008002",
    "申银万国行业分类标准": "008003",
    "新财富行业分类标准": "008004",
    "国资委行业分类标准": "008005",
    "巨潮产业细分标准": "008006",
    "天相行业分类标准": "008007",
    "全球行业分类标准": "008008",
}


class CninfoRequestError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"{category}: {message}")
        self.category = category


class CninfoControlledProvider:
    """Call documented CNInfo endpoints with bounded retries and normalized rows."""

    def __init__(
        self,
        *,
        session: Any = None,
        connect_timeout_seconds: float = 10,
        read_timeout_seconds: float = 20,
        retry_count: int = 2,
        backoff_seconds: float = 0.8,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        curl_transport: BoundedCurlJsonTransport | None = None,
        enable_curl_fallback: bool = True,
        requests_per_minute: int = 10,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if session is None:
            import requests

            session = requests.Session()
        self.session = session
        self.timeout = (
            max(1.0, float(connect_timeout_seconds)),
            max(1.0, float(read_timeout_seconds)),
        )
        self.retry_count = max(0, int(retry_count))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self.sleep = sleep
        self.clock = clock
        self.monotonic = monotonic
        self.request_interval_seconds = (
            60.0 / int(requests_per_minute) if int(requests_per_minute) > 0 else 0.0
        )
        self._request_lock = threading.Lock()
        self._last_request_started: float | None = None
        self.curl_transport = curl_transport
        if self.curl_transport is None and enable_curl_fallback:
            self.curl_transport = BoundedCurlJsonTransport.auto(
                connect_timeout_seconds=int(self.timeout[0]),
                max_time_seconds=25,
            )
        self._org_ids: dict[str, str] | None = None

    def fetch_industry_categories(self, standard: str = "巨潮行业分类标准") -> list[dict[str, Any]]:
        if standard not in _INDUSTRY_TYPES:
            raise ValueError(f"unsupported CNInfo industry standard: {standard}")
        payload = self._request_json(
            "GET",
            f"{_WEBAPI_ROOT}/p_public0002",
            params={"indcode": "", "indtype": _INDUSTRY_TYPES[standard], "format": "json"},
            headers=self._webapi_headers(),
        )
        rows = []
        for record in list(payload.get("records") or []):
            rows.append(
                {
                    "category_code": str(record.get("SORTCODE") or ""),
                    "category_name": str(record.get("SORTNAME") or ""),
                    "category_name_en": str(record.get("F001V") or ""),
                    "parent_code": str(record.get("PARENTCODE") or ""),
                    "standard_code": str(record.get("F003V") or ""),
                    "standard": str(record.get("F004V") or standard),
                    "end_date": _date_text(record.get("F002D")) or None,
                }
            )
        return [row for row in rows if row["category_code"] and row["category_name"]]

    def fetch_industry_intervals(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        observed_at: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self._webapi_records(
            "p_stock2110", symbol=symbol, start_date=start_date, end_date=end_date
        )
        observed = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        records_by_standard: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            standard = str(record.get("F002V") or "未标注行业标准").strip()
            valid_from = _date_text(record.get("VARYDATE"))
            category = str(record.get("F006V") or record.get("F004V") or "").strip()
            if valid_from and category:
                records_by_standard.setdefault(standard, []).append(record)
        rows: list[dict[str, Any]] = []
        for standard, standard_records in records_by_standard.items():
            standard_records.sort(key=lambda row: str(row.get("VARYDATE") or ""))
            for index, record in enumerate(standard_records):
                valid_from = _date_text(record.get("VARYDATE"))
                category = str(record.get("F006V") or record.get("F004V") or "").strip()
                next_from = (
                    _date_text(standard_records[index + 1].get("VARYDATE"))
                    if index + 1 < len(standard_records)
                    else ""
                )
                valid_to = (
                    (datetime.fromisoformat(next_from).date() - timedelta(days=1)).isoformat()
                    if next_from
                    else None
                )
                rows.append(
                    {
                        "symbol": _symbol(symbol),
                        "dimension": "industry",
                        "category": category,
                        "valid_from": valid_from,
                        "valid_to": valid_to,
                        "source": "cninfo.p_stock2110",
                        "source_version": "controlled-http-aes-curl-v5",
                        "observed_at": observed,
                        "evidence": {
                            "classification_standard": standard,
                            "classification_code": record.get("F003V"),
                            "organization": record.get("ORGNAME"),
                        },
                    }
                )
        return sorted(
            rows,
            key=lambda row: (
                str(row["valid_from"]),
                str(row["evidence"]["classification_standard"]),
                str(row["category"]),
            ),
        )

    def fetch_share_changes(
        self, symbol: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        records = self._webapi_records(
            "p_stock2215", symbol=symbol, start_date=start_date, end_date=end_date
        )
        return [
            {
                "symbol": _symbol(symbol),
                "security_name": str(record.get("SECNAME") or ""),
                "organization": str(record.get("ORGNAME") or ""),
                "announcement_date": _date_text(record.get("DECLAREDATE")) or None,
                "change_date": _date_text(record.get("VARYDATE")) or None,
                "reason_code": str(record.get("F001V") or ""),
                "reason": str(record.get("F002V") or ""),
                "total_shares": _shares_from_ten_thousands(record.get("F003N")),
                "circulating_shares": _shares_from_ten_thousands(record.get("F021N")),
                "a_shares": _shares_from_ten_thousands(record.get("F022N")),
                "total_shares_wan": _optional_number(record.get("F003N")),
                "circulating_shares_wan": _optional_number(record.get("F021N")),
                "a_shares_wan": _optional_number(record.get("F022N")),
                "source_unit": "万股",
                "source": "cninfo.p_stock2215",
            }
            for record in records
        ]

    def fetch_announcements(
        self, symbol: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        code = _symbol(symbol)
        org_id = self._org_id(code)
        params = {
            "pageNum": 1,
            "pageSize": 30,
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{code},{org_id}",
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{_date_text(start_date)}~{_date_text(end_date)}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        first = self._request_json(
            "POST",
            f"{_DISCLOSURE_ROOT}/hisAnnouncement/query",
            params=params,
            headers=self._disclosure_headers(),
        )
        total = int(first.get("totalAnnouncement") or 0)
        page_count = max(1, (total + 29) // 30)
        payloads = [first]
        for page in range(2, page_count + 1):
            payloads.append(
                self._request_json(
                    "POST",
                    f"{_DISCLOSURE_ROOT}/hisAnnouncement/query",
                    data={**params, "pageNum": page},
                    headers=self._disclosure_headers(),
                )
            )
        rows = []
        china_timezone = timezone(timedelta(hours=8))
        for payload in payloads:
            for record in list(payload.get("announcements") or []):
                milliseconds = _optional_number(record.get("announcementTime"))
                published = (
                    datetime.fromtimestamp(milliseconds / 1000, timezone.utc)
                    .astimezone(china_timezone)
                    .replace(tzinfo=None)
                    .isoformat(sep=" ", timespec="seconds")
                    if milliseconds is not None
                    else _date_text(start_date)
                )
                announcement_id = str(record.get("announcementId") or "")
                row_org_id = str(record.get("orgId") or org_id)
                rows.append(
                    {
                        "event_date": published[:10],
                        "published_at": published,
                        "symbol": code,
                        "event_type": "announcement",
                        "title": str(record.get("announcementTitle") or "公告"),
                        "url": (
                            f"{_DISCLOSURE_ROOT}/disclosure/detail?stockCode={code}"
                            f"&announcementId={announcement_id}&orgId={row_org_id}"
                            f"&announcementTime={published}"
                        ),
                        "source": "cninfo.disclosure_report_controlled",
                    }
                )
        return rows

    def _webapi_records(
        self, endpoint: str, *, symbol: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            "POST",
            f"{_WEBAPI_ROOT}/{endpoint}",
            params={
                "scode": _symbol(symbol),
                "sdate": _date_text(start_date),
                "edate": _date_text(end_date),
            },
            headers=self._webapi_headers(),
        )
        return [dict(record) for record in list(payload.get("records") or [])]

    def _org_id(self, symbol: str) -> str:
        if self._org_ids is None:
            payload = self._request_json(
                "GET",
                f"{_DISCLOSURE_ROOT}/data/szse_stock.json",
                headers=self._disclosure_headers(),
            )
            self._org_ids = {
                str(row.get("code")): str(row.get("orgId"))
                for row in list(payload.get("stockList") or [])
                if row.get("code") and row.get("orgId")
            }
        org_id = self._org_ids.get(symbol)
        if not org_id:
            raise CninfoRequestError("mapping_error", f"orgId not found for {symbol}")
        return org_id

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        self._wait_for_request_slot()
        last_error: CninfoRequestError | None = None
        for attempt in range(self.retry_count + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=dict(params or {}),
                    data=dict(data or {}) if data is not None else None,
                    headers=dict(headers or {}),
                    timeout=self.timeout,
                    verify=True,
                )
                status = int(response.status_code)
                if status == 429 or status >= 500:
                    raise CninfoRequestError("http_retryable", f"HTTP {status}")
                if status >= 400:
                    raise CninfoRequestError("http_error", f"HTTP {status}")
                try:
                    payload = response.json()
                except Exception as error:
                    raise CninfoRequestError(
                        "json_error", f"{type(error).__name__}: {str(error)[:160]}"
                    ) from error
                if not isinstance(payload, dict):
                    raise CninfoRequestError("schema_error", "response is not a JSON object")
                return payload
            except CninfoRequestError as error:
                last_error = error
                retryable = error.category in {"http_retryable", "json_error"}
            except Exception as error:
                category = _transport_category(error)
                last_error = CninfoRequestError(
                    category, f"{type(error).__name__}: {str(error)[:240]}"
                )
                retryable = category in {"tls_error", "timeout", "connection_error"}
            if attempt >= self.retry_count or not retryable:
                break
            self.sleep(self.backoff_seconds * (2**attempt))
        if (
            last_error is not None
            and self.curl_transport is not None
            and last_error.category
            in {"tls_error", "timeout", "connection_error", "transport_error"}
        ):
            try:
                return self.curl_transport.request_json(
                    method, url, params=params, data=data, headers=headers
                )
            except CurlTransportError as curl_error:
                raise CninfoRequestError(
                    curl_error.category,
                    f"primary={last_error}; curl={curl_error}",
                ) from curl_error
        raise last_error or CninfoRequestError("unknown_error", "request failed")

    def _wait_for_request_slot(self) -> None:
        if self.request_interval_seconds <= 0:
            return
        with self._request_lock:
            now = self.monotonic()
            if self._last_request_started is not None:
                remaining = (
                    self.request_interval_seconds
                    - (now - self._last_request_started)
                )
                if remaining > 0:
                    self.sleep(remaining)
                    now = self.monotonic()
            self._last_request_started = now

    def _webapi_headers(self) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Enckey": _encrypted_timestamp(self.clock()),
            "Cache-Control": "no-cache",
            "Content-Length": "0",
            "Connection": "close",
            "Host": "webapi.cninfo.com.cn",
            "Origin": "https://webapi.cninfo.com.cn",
            "Pragma": "no-cache",
            "Referer": "https://webapi.cninfo.com.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

    @staticmethod
    def _disclosure_headers() -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Connection": "close",
            "Referer": "https://www.cninfo.com.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }


def _encrypted_timestamp(value: float) -> str:
    timestamp = str(int(value)).encode("ascii")
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
    except ModuleNotFoundError:
        encrypted = _windows_aes_cbc_encrypt(timestamp, key=_AES_KEY, iv=_AES_KEY)
    else:
        cipher = AES.new(_AES_KEY, AES.MODE_CBC, _AES_KEY)
        encrypted = cipher.encrypt(pad(timestamp, AES.block_size))
    return base64.b64encode(encrypted).decode("ascii")


def _windows_aes_cbc_encrypt(payload: bytes, *, key: bytes, iv: bytes) -> bytes:
    """Encrypt with Windows CNG when the optional PyCryptodome package is absent."""
    if os.name != "nt":
        raise RuntimeError("CNInfo AES requires PyCryptodome or Windows CNG")
    if len(key) not in {16, 24, 32} or len(iv) != 16:
        raise ValueError("AES key or IV length is invalid")

    import ctypes

    bcrypt = ctypes.WinDLL("bcrypt")
    handle_type = ctypes.c_void_p
    ulong = ctypes.c_ulong
    pointer = ctypes.c_void_p
    status_type = ctypes.c_long

    bcrypt.BCryptOpenAlgorithmProvider.argtypes = [
        ctypes.POINTER(handle_type), ctypes.c_wchar_p, ctypes.c_wchar_p, ulong,
    ]
    bcrypt.BCryptOpenAlgorithmProvider.restype = status_type
    bcrypt.BCryptSetProperty.argtypes = [
        handle_type, ctypes.c_wchar_p, pointer, ulong, ulong,
    ]
    bcrypt.BCryptSetProperty.restype = status_type
    bcrypt.BCryptGetProperty.argtypes = [
        handle_type, ctypes.c_wchar_p, pointer, ulong, ctypes.POINTER(ulong), ulong,
    ]
    bcrypt.BCryptGetProperty.restype = status_type
    bcrypt.BCryptGenerateSymmetricKey.argtypes = [
        handle_type, ctypes.POINTER(handle_type), pointer, ulong, pointer, ulong, ulong,
    ]
    bcrypt.BCryptGenerateSymmetricKey.restype = status_type
    bcrypt.BCryptEncrypt.argtypes = [
        handle_type, pointer, ulong, pointer, pointer, ulong,
        pointer, ulong, ctypes.POINTER(ulong), ulong,
    ]
    bcrypt.BCryptEncrypt.restype = status_type
    bcrypt.BCryptDestroyKey.argtypes = [handle_type]
    bcrypt.BCryptDestroyKey.restype = status_type
    bcrypt.BCryptCloseAlgorithmProvider.argtypes = [handle_type, ulong]
    bcrypt.BCryptCloseAlgorithmProvider.restype = status_type

    def check(status: int, operation: str) -> None:
        if status != 0:
            code = ctypes.c_ulong(status).value
            raise OSError(f"{operation} failed with NTSTATUS 0x{code:08x}")

    algorithm = handle_type()
    key_handle = handle_type()
    try:
        check(
            bcrypt.BCryptOpenAlgorithmProvider(
                ctypes.byref(algorithm), "AES", None, 0,
            ),
            "BCryptOpenAlgorithmProvider",
        )
        chaining_mode = ctypes.create_unicode_buffer("ChainingModeCBC")
        check(
            bcrypt.BCryptSetProperty(
                algorithm, "ChainingMode", ctypes.cast(chaining_mode, pointer),
                ctypes.sizeof(chaining_mode), 0,
            ),
            "BCryptSetProperty",
        )
        object_length = ulong()
        copied = ulong()
        check(
            bcrypt.BCryptGetProperty(
                algorithm, "ObjectLength", ctypes.byref(object_length),
                ctypes.sizeof(object_length), ctypes.byref(copied), 0,
            ),
            "BCryptGetProperty",
        )
        key_object = ctypes.create_string_buffer(object_length.value)
        key_material = ctypes.create_string_buffer(key, len(key))
        check(
            bcrypt.BCryptGenerateSymmetricKey(
                algorithm, ctypes.byref(key_handle), key_object, object_length.value,
                key_material, len(key), 0,
            ),
            "BCryptGenerateSymmetricKey",
        )
        source = ctypes.create_string_buffer(payload, len(payload))
        output_length = ulong()
        sizing_iv = ctypes.create_string_buffer(iv, len(iv))
        check(
            bcrypt.BCryptEncrypt(
                key_handle, source, len(payload), None, sizing_iv, len(iv),
                None, 0, ctypes.byref(output_length), 1,
            ),
            "BCryptEncrypt(size)",
        )
        output = ctypes.create_string_buffer(output_length.value)
        written = ulong()
        encrypt_iv = ctypes.create_string_buffer(iv, len(iv))
        check(
            bcrypt.BCryptEncrypt(
                key_handle, source, len(payload), None, encrypt_iv, len(iv),
                output, output_length.value, ctypes.byref(written), 1,
            ),
            "BCryptEncrypt",
        )
        return output.raw[:written.value]
    finally:
        if key_handle.value:
            bcrypt.BCryptDestroyKey(key_handle)
        if algorithm.value:
            bcrypt.BCryptCloseAlgorithmProvider(algorithm, 0)


def _transport_category(error: Exception) -> str:
    name = type(error).__name__.lower()
    message = str(error).lower()
    if "ssl" in name or "ssl" in message or "tls" in message:
        return "tls_error"
    if "timeout" in name or "timed out" in message:
        return "timeout"
    if "connection" in name or "connection" in message:
        return "connection_error"
    return "transport_error"


def _symbol(value: str) -> str:
    return str(value or "").strip().split(".")[0].zfill(6)


def _date_text(value: Any) -> str:
    text = str(value or "").strip().replace("/", "-")
    if not text:
        return ""
    compact = text.replace("-", "")[:8]
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _shares_from_ten_thousands(value: Any) -> float | None:
    number = _optional_number(value)
    return number * 10_000 if number is not None else None
