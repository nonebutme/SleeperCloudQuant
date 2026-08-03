"""Verify that market events use the bounded CNInfo provider."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.market_panorama_service import MarketPanoramaService  # noqa: E402
from data_platform.storage.market_panorama_store import MarketPanoramaStore  # noqa: E402


class _Frame:
    @staticmethod
    def to_dict(orient: str) -> list[dict[str, Any]]:
        assert orient == "records"
        return []


class _Akshare:
    @staticmethod
    def stock_news_em(*, symbol: str) -> _Frame:
        assert symbol == "000001"
        return _Frame()


class _Cninfo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def fetch_announcements(
        self, symbol: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        self.calls.append((symbol, start_date, end_date))
        return [
            {
                "event_date": "2026-07-31",
                "published_at": "2026-07-31 09:00:00",
                "symbol": symbol,
                "event_type": "announcement",
                "title": "受控公告",
                "url": "https://www.cninfo.com.cn/example",
                "source": "cninfo.disclosure_report_controlled",
            }
        ]


def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="scq-cninfo-market-", ignore_cleanup_errors=True
    ) as temporary:
        provider = _Cninfo()
        service = MarketPanoramaService(
            MarketPanoramaStore(Path(temporary) / "panorama.sqlite3"),
            cninfo_provider=provider,
        )
        service._akshare = lambda: _Akshare()  # type: ignore[method-assign]
        events = service._fetch_events("000001", "2026-07-31")

    assert provider.calls == [("000001", "20260731", "20260731")]
    assert len(events) == 1
    assert events[0]["title"] == "受控公告"
    assert events[0]["source"] == "cninfo.disclosure_report_controlled"
    print("CNInfo market integration smoke passed")


if __name__ == "__main__":
    main()
