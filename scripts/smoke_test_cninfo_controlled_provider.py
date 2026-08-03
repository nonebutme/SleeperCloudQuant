"""Deterministic smoke tests for the bounded CNInfo provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.providers.cninfo_controlled_provider import (  # noqa: E402
    CninfoControlledProvider,
    CninfoRequestError,
    _encrypted_timestamp,
)


@dataclass
class _Response:
    payload: dict[str, Any]
    status_code: int = 200

    def json(self) -> dict[str, Any]:
        return self.payload


class _Session:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _CurlFallback:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"method": method, "url": url, **kwargs})
        return {
            "records": [
                {
                    "VARYDATE": "2024-02-08",
                    "F006V": "货币金融服务",
                    "F002V": "中国上市公司协会上市公司行业分类标准",
                    "F003V": "J66",
                    "ORGNAME": "平安银行股份有限公司",
                }
            ]
        }

def main() -> None:
    assert _encrypted_timestamp(1_700_000_000) == "WltfJaS1dRCcbgz+YSPgFg=="
    sleeps: list[float] = []
    category_session = _Session(
        [
            _Response({}, status_code=500),
            _Response(
                {
                    "records": [
                        {
                            "SORTCODE": "A",
                            "SORTNAME": "农、林、牧、渔业",
                            "PARENTCODE": "0",
                            "F003V": "008002",
                            "F004V": "巨潮行业分类标准",
                        }
                    ]
                }
            ),
        ]
    )
    provider = CninfoControlledProvider(
        session=category_session,
        retry_count=1,
        backoff_seconds=0.25,
        sleep=sleeps.append,
        clock=lambda: 1_700_000_000,
    )
    categories = provider.fetch_industry_categories()
    assert categories[0]["category_code"] == "A"
    assert category_session.calls[0]["verify"] is True
    assert category_session.calls[0]["timeout"] == (10.0, 20.0)
    assert sleeps == [0.25]

    interval_session = _Session(
        [
            _Response(
                {
                    "records": [
                        {
                            "VARYDATE": "2020-01-02",
                            "F006V": "银行",
                            "F002V": "巨潮行业分类标准",
                            "F003V": "J66",
                            "ORGNAME": "平安银行",
                        },
                        {
                            "VARYDATE": "2021-03-05",
                            "F006V": "货币金融服务",
                            "F002V": "巨潮行业分类标准",
                            "F003V": "J66",
                            "ORGNAME": "平安银行",
                        },
                    ]
                }
            )
        ]
    )
    intervals = CninfoControlledProvider(session=interval_session).fetch_industry_intervals(
        "1", "20200101", "20261231", observed_at="2026-07-31T00:00:00+00:00"
    )
    assert intervals[0]["symbol"] == "000001"
    assert intervals[0]["valid_to"] == "2021-03-04"
    assert intervals[1]["valid_to"] is None
    assert intervals[0]["source_version"] == "controlled-http-aes-curl-v5"

    multi_standard_session = _Session(
        [
            _Response(
                {
                    "records": [
                        {
                            "VARYDATE": "2020-01-02",
                            "F006V": "银行",
                            "F002V": "巨潮行业分类标准",
                            "F003V": "Z07",
                        },
                        {
                            "VARYDATE": "2020-01-02",
                            "F006V": "货币金融服务",
                            "F002V": "证监会行业分类标准（2012）",
                            "F003V": "J66",
                        },
                    ]
                }
            )
        ]
    )
    multi_standard = CninfoControlledProvider(
        session=multi_standard_session
    ).fetch_industry_intervals("000001", "20200101", "20201231")
    assert len(multi_standard) == 2
    assert all(row["valid_to"] is None for row in multi_standard)
    assert len({row["evidence"]["classification_standard"] for row in multi_standard}) == 2

    share_session = _Session(
        [
            _Response(
                {
                    "records": [
                        {
                            "SECNAME": "平安银行",
                            "VARYDATE": "2024-06-30",
                            "F002V": "定期报告",
                            "F003N": "1940591.8198",
                            "F021N": "1940555.7128",
                        }
                    ]
                }
            )
        ]
    )
    shares = CninfoControlledProvider(session=share_session).fetch_share_changes(
        "000001", "20240101", "20241231"
    )
    assert shares[0]["total_shares"] == 19_405_918_198.0
    assert shares[0]["source_unit"] == "万股"
    assert shares[0]["change_date"] == "2024-06-30"

    announcement_session = _Session(
        [
            _Response({"stockList": [{"code": "000001", "orgId": "gssz0000001"}]}),
            _Response(
                {
                    "totalAnnouncement": 1,
                    "announcements": [
                        {
                            "announcementId": "121234",
                            "announcementTitle": "年度报告",
                            "announcementTime": 1_717_200_000_000,
                            "orgId": "gssz0000001",
                        }
                    ],
                }
            ),
        ]
    )
    announcements = CninfoControlledProvider(
        session=announcement_session, requests_per_minute=0
    ).fetch_announcements("000001", "20240601", "20240601")
    assert announcements[0]["event_type"] == "announcement"
    assert announcements[0]["source"] == "cninfo.disclosure_report_controlled"
    assert "announcementId=121234" in announcements[0]["url"]

    tls_session = _Session([RuntimeError("SSL EOF occurred")])
    try:
        CninfoControlledProvider(
            session=tls_session, retry_count=0, enable_curl_fallback=False
        ).fetch_share_changes(
            "000001", "20240101", "20241231"
        )
    except CninfoRequestError as error:
        assert error.category == "tls_error"
    else:
        raise AssertionError("TLS transport failure was not categorized")

    curl_fallback = _CurlFallback()
    fallback_rows = CninfoControlledProvider(
        session=_Session([RuntimeError("SSL EOF occurred")]),
        retry_count=0,
        curl_transport=curl_fallback,
    ).fetch_industry_intervals("000001", "20240101", "20241231")
    assert fallback_rows[0]["category"] == "货币金融服务"
    assert len(curl_fallback.calls) == 1
    assert curl_fallback.calls[0]["url"].endswith("/p_stock2110")

    ticks = iter([100.0, 101.0, 106.0])
    rate_sleeps: list[float] = []
    rate_provider = CninfoControlledProvider(
        session=_Session([]),
        requests_per_minute=10,
        monotonic=lambda: next(ticks),
        sleep=rate_sleeps.append,
        enable_curl_fallback=False,
    )
    rate_provider._wait_for_request_slot()
    rate_provider._wait_for_request_slot()
    assert rate_sleeps == [5.0]

    print(
        {
            "status": "passed",
            "categories": len(categories),
            "intervals": len(intervals),
            "share_changes": len(shares),
            "announcements": len(announcements),
        }
    )


if __name__ == "__main__":
    main()
