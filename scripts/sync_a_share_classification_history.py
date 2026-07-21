"""Sync/import effective-dated A-share industry and concept classifications."""

from __future__ import annotations

import argparse
import base64
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


_CNINFO_URL = "https://webapi.cninfo.com.cn/api/stock/p_stock2110"
_CNINFO_AES_KEY = b"1234567887654321"


def main() -> None:
    ensure_project_root_on_sys_path()
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="var/runtime/a_share_classification_history.sqlite3")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols for CNInfo industry history")
    parser.add_argument("--start-date", default="19900101")
    parser.add_argument("--end-date", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--input-jsonl", help="Effective-dated industry/concept records")
    args = parser.parse_args()

    from data_platform import ClassificationHistoryStore

    store = ClassificationHistoryStore(args.database)
    rows: list[dict[str, Any]] = []
    if args.input_jsonl:
        rows.extend(_read_jsonl(Path(args.input_jsonl)))
    symbols = [item.strip().split(".")[0].zfill(6) for item in args.symbols.split(",") if item.strip()]
    if symbols:
        rows.extend(_fetch_cninfo_industries(symbols, args.start_date, args.end_date))
    written = store.upsert_intervals(rows)
    print(json.dumps({"status": "completed", "written": written, "coverage": store.coverage()}, ensure_ascii=False))


def _fetch_cninfo_industries(symbols: list[str], start_date: str, end_date: str) -> list[dict[str, Any]]:
    try:
        import requests
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
    except ImportError as exc:
        raise SystemExit("requests and pycryptodome are required for CNInfo industry sync") from exc
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result: list[dict[str, Any]] = []
    for symbol in symbols:
        timestamp = str(int(time.time())).encode("ascii")
        cipher = AES.new(_CNINFO_AES_KEY, AES.MODE_CBC, _CNINFO_AES_KEY)
        enckey = base64.b64encode(cipher.encrypt(pad(timestamp, AES.block_size))).decode("ascii")
        response = requests.post(

            _CNINFO_URL,
            params={
                "scode": symbol,
                "sdate": _compact_date(start_date),
                "edate": _compact_date(end_date),
            },
            headers={
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Content-Length": "0",
                "Host": "webapi.cninfo.com.cn",
                "Accept-Enckey": enckey,
                "Origin": "https://webapi.cninfo.com.cn",
                "Pragma": "no-cache",
                "Connection": "close",
                "Referer": "https://webapi.cninfo.com.cn/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=(30, 60),
        )
        response.raise_for_status()
        payload = response.json()
        records = sorted(list(payload.get("records") or []), key=lambda row: str(row.get("VARYDATE") or ""))
        for index, record in enumerate(records):
            valid_from = _date_text(record.get("VARYDATE"))
            category = str(record.get("F006V") or record.get("F004V") or "").strip()
            if not valid_from or not category:
                continue
            next_from = _date_text(records[index + 1].get("VARYDATE")) if index + 1 < len(records) else ""
            valid_to = (datetime.fromisoformat(next_from).date() - timedelta(days=1)).isoformat() if next_from else None
            result.append({
                "symbol": symbol,
                "dimension": "industry",
                "category": category,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "source": "cninfo.p_stock2110",
                "source_version": "direct-http-aes-v3",
                "observed_at": observed_at,
                "evidence": {
                    "classification_standard": record.get("F002V"),
                    "classification_code": record.get("F003V"),
                    "organization": record.get("ORGNAME"),
                },
            })
    return result


def _compact_date(value: str) -> str:
    text = str(value or "").replace("-", "").replace("/", "")[:8]
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(dict(json.loads(line)))
    return rows


def _date_text(value: Any) -> str:
    text = str(value or "").strip()[:10]
    if not text:
        return ""
    return text.replace("/", "-") if "-" in text or "/" in text else f"{text[:4]}-{text[4:6]}-{text[6:8]}"


if __name__ == "__main__":
    main()
