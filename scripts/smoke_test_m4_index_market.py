"""Contracts for governed index browsing and the M4 index workspace."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.api.market import build_market_routes
from app.schemas.market import IndexDailyPricesQuery, IndexSymbolsQuery
from app.services.market_data_service import MarketDataService
from data_platform.storage.a_share_governance_store import AShareGovernanceStore


class _MarketRepository:
    def fetch_index_components(self, index_code: str, date: str | None = None):
        return []


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "market.sqlite3"
        store = AShareGovernanceStore(database)
        store.ensure_schema()
        store.upsert_index_prices(
            [
                {
                    "index_symbol": "000300",
                    "trade_date": "2026-07-29",
                    "open": 4000,
                    "high": 4050,
                    "low": 3980,
                    "close": 4030,
                    "volume": 123,
                    "amount": 456,
                    "source": "smoke",
                },
                {
                    "index_symbol": "000300",
                    "trade_date": "2026-07-30",
                    "open": 4030,
                    "high": 4060,
                    "low": 4010,
                    "close": 4050,
                    "volume": 234,
                    "amount": 567,
                    "source": "smoke",
                },
            ]
        )
        service = MarketDataService(_MarketRepository(), governance_repository=store)
        catalog = service.list_index_symbols()
        hs300 = next(item for item in catalog["items"] if item["index_symbol"] == "000300")
        assert hs300["row_count"] == 2
        assert hs300["status"] == "ready"
        daily = service.get_index_daily_prices(index_symbol="000300", limit=1)
        assert daily["total"] == 2
        assert daily["rows"][0]["date"] == "2026-07-30"
        assert daily["rows"][0]["change_pct"] is not None
        routes = {route.name: route for route in build_market_routes(service)}
        assert routes["market_index_symbols"].handler(IndexSymbolsQuery()).catalog["items"]
        response = routes["market_index_daily"].handler(
            IndexDailyPricesQuery(index_symbol="000300", limit=10)
        )
        assert response.daily["rows"][0]["index_symbol"] == "000300"

    root = Path(__file__).resolve().parent.parent
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    script = (root / "web" / "m4_asset_browser.js").read_text(encoding="utf-8")
    assert "股票行情" in html
    assert "北交所周线" not in html
    assert "data-m4-frequency" in html
    assert "/api/market/index-symbols" in script
    assert "/api/market/index-daily" in script
    print("M4 governed index market smoke passed")


if __name__ == "__main__":
    main()
