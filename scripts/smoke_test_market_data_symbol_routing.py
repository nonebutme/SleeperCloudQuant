"""Regression guard for A-share/index codes that share the same six digits."""

from _project_bootstrap import ensure_project_root_on_sys_path


class StockRepository:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_price_history(self, symbol: str, *, start_date: str | None, end_date: str | None, adjustment: str):
        self.calls.append(symbol)
        return [{"date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]


class IndexRepository:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_index_price_history(self, symbol: str, *, start_date: str | None, end_date: str | None):
        self.calls.append(symbol)
        return [{"date": "2024-01-02", "open": 3000, "high": 3010, "low": 2990, "close": 3005, "volume": 1000}]


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.market_data_service import MarketDataService

    stocks = StockRepository()
    indices = IndexRepository()
    service = MarketDataService(object(), a_share_repository=stocks, governance_repository=indices)

    bare_stock = service.get_a_share_price_history(symbol="000001")
    qualified_stock = service.get_a_share_price_history(symbol="000001.XSHE")
    qualified_index = service.get_a_share_price_history(symbol="000001.XSHG")

    assert bare_stock[0]["close"] == 10.5
    assert qualified_stock[0]["close"] == 10.5
    assert qualified_index[0]["close"] == 3005
    assert stocks.calls == ["000001", "000001.XSHE"]
    assert indices.calls == ["000001.XSHG"]
    print("market data symbol routing smoke test passed")


if __name__ == "__main__":
    main()
