"""Minimal factor research service backed by market data and SQLite storage."""

from __future__ import annotations

from typing import Protocol

from app.services.market_data_service import MarketDataService
from factor_lab import (
    FactorDefinition,
    FactorPoolRunResult,
    FactorRankingResult,
    FactorRegistry,
    FactorRunResult,
    FactorValue,
)


class FactorValueStore(Protocol):
    """Storage protocol for minimal factor result persistence."""

    def save_factor_values(self, *, definition: FactorDefinition, symbol: str, start_date: str | None, end_date: str | None, rows: list[FactorValue]) -> str: ...
    def fetch_factor_values(self, *, factor_id: str, symbol: str, start_date: str | None, end_date: str | None) -> list[FactorValue]: ...
    def fetch_factor_rankings(self, *, factor_id: str, trade_date: str, start_date: str | None, end_date: str | None, limit: int, descending: bool) -> list[FactorValue]: ...


class FactorResearchService:
    """Expose one conservative factor-computation workflow."""

    def __init__(self, market_data_service: MarketDataService, factor_store: FactorValueStore) -> None:
        self._market_data_service = market_data_service
        self._factor_store = factor_store
        self._registry = FactorRegistry()

    def list_factor_definitions(self) -> list[FactorDefinition]:
        return self._registry.definitions()

    def get_pool_members(self, *, index_code: str, date: str | None = None) -> list[str]:
        return self._market_data_service.get_index_components(index_code=index_code, date=date)

    def get_factor_summary(self, *, symbol: str, trade_date: str, start_date: str | None = None, end_date: str | None = None, factor_ids: list[str] | None = None) -> list[FactorValue]:
        rows: list[FactorValue] = []
        for factor_id in self._resolve_factor_ids(factor_ids):
            factor_rows = self.get_factor_values(
                factor_id=factor_id,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            for row in factor_rows:
                if row.trade_date == trade_date:
                    rows.append(row)
                    break
        return rows

    def get_pool_factor_summary(
        self,
        *,
        index_code: str,
        trade_date: str,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        factor_ids: list[str] | None = None,
    ) -> dict[str, list[FactorValue]]:
        symbols = self.get_pool_members(index_code=index_code, date=date)
        return {
            symbol: self.get_factor_summary(
                symbol=symbol,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
                factor_ids=factor_ids,
            )
            for symbol in symbols
        }

    def run_factor(self, *, factor_id: str, symbol: str, start_date: str | None = None, end_date: str | None = None) -> FactorRunResult:
        calculator = self._registry.get(factor_id)
        return self._run_single_calculator(calculator=calculator, symbol=symbol, start_date=start_date, end_date=end_date)

    def run_factor_for_symbols(self, *, factor_id: str, symbols: list[str], start_date: str | None = None, end_date: str | None = None) -> FactorPoolRunResult:
        calculator = self._registry.get(factor_id)
        return self._run_pool_calculator(calculator=calculator, symbols=symbols, start_date=start_date, end_date=end_date)

    def run_factor_for_index(self, *, factor_id: str, index_code: str, date: str | None = None, start_date: str | None = None, end_date: str | None = None) -> FactorPoolRunResult:
        symbols = self.get_pool_members(index_code=index_code, date=date)
        return self.run_factor_for_symbols(factor_id=factor_id, symbols=symbols, start_date=start_date, end_date=end_date)

    def run_close_to_close_return(self, *, symbol: str, start_date: str | None = None, end_date: str | None = None) -> FactorRunResult:
        return self._run_named_factor(
            factor_id="close_to_close_return_1d",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def run_close_to_ma2_bias(self, *, symbol: str, start_date: str | None = None, end_date: str | None = None) -> FactorRunResult:
        return self._run_named_factor(
            factor_id="close_to_ma2_bias",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def run_close_to_close_return_for_symbols(self, *, symbols: list[str], start_date: str | None = None, end_date: str | None = None) -> FactorPoolRunResult:
        return self._run_named_factor_for_symbols(
            factor_id="close_to_close_return_1d",
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )

    def run_close_to_ma2_bias_for_symbols(self, *, symbols: list[str], start_date: str | None = None, end_date: str | None = None) -> FactorPoolRunResult:
        return self._run_named_factor_for_symbols(
            factor_id="close_to_ma2_bias",
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )

    def run_close_to_close_return_for_index(self, *, index_code: str, date: str | None = None, start_date: str | None = None, end_date: str | None = None) -> FactorPoolRunResult:
        return self._run_named_factor_for_index(
            factor_id="close_to_close_return_1d",
            index_code=index_code,
            date=date,
            start_date=start_date,
            end_date=end_date,
        )

    def run_close_to_ma2_bias_for_index(self, *, index_code: str, date: str | None = None, start_date: str | None = None, end_date: str | None = None) -> FactorPoolRunResult:
        return self._run_named_factor_for_index(
            factor_id="close_to_ma2_bias",
            index_code=index_code,
            date=date,
            start_date=start_date,
            end_date=end_date,
        )

    def get_factor_values(self, *, factor_id: str, symbol: str, start_date: str | None = None, end_date: str | None = None) -> list[FactorValue]:
        return self._factor_store.fetch_factor_values(factor_id=factor_id, symbol=symbol, start_date=start_date, end_date=end_date)

    def get_factor_top_n(self, *, factor_id: str, trade_date: str, start_date: str | None = None, end_date: str | None = None, limit: int = 10, descending: bool = True) -> FactorRankingResult:
        rows = self._factor_store.fetch_factor_rankings(
            factor_id=factor_id,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            limit=max(1, int(limit)),
            descending=descending,
        )
        return FactorRankingResult(
            factor_id=factor_id,
            trade_date=trade_date,
            row_count=len(rows),
            rows=rows,
        )

    def _run_named_factor(
        self,
        *,
        factor_id: str,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> FactorRunResult:
        return self.run_factor(
            factor_id=factor_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def _run_named_factor_for_symbols(
        self,
        *,
        factor_id: str,
        symbols: list[str],
        start_date: str | None,
        end_date: str | None,
    ) -> FactorPoolRunResult:
        return self.run_factor_for_symbols(
            factor_id=factor_id,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )

    def _run_named_factor_for_index(
        self,
        *,
        factor_id: str,
        index_code: str,
        date: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> FactorPoolRunResult:
        return self.run_factor_for_index(
            factor_id=factor_id,
            index_code=index_code,
            date=date,
            start_date=start_date,
            end_date=end_date,
        )

    def _run_single_calculator(self, *, calculator, symbol: str, start_date: str | None, end_date: str | None) -> FactorRunResult:
        bars = self._market_data_service.get_price_history(symbol=symbol, start_date=start_date, end_date=end_date)
        rows = calculator.calculate(symbol=symbol, bars=bars)
        stored_at = self._factor_store.save_factor_values(definition=calculator.definition(), symbol=symbol, start_date=start_date, end_date=end_date, rows=rows)
        return FactorRunResult(factor_id=calculator.factor_id, symbol=symbol, start_date=start_date, end_date=end_date, row_count=len(rows), rows=rows, stored_at=stored_at)

    def _run_pool_calculator(self, *, calculator, symbols: list[str], start_date: str | None, end_date: str | None) -> FactorPoolRunResult:
        normalized_symbols = self._normalize_symbols(symbols)
        results = [self._run_single_calculator(calculator=calculator, symbol=symbol, start_date=start_date, end_date=end_date) for symbol in normalized_symbols]
        return FactorPoolRunResult(factor_id=calculator.factor_id, symbols=normalized_symbols, run_count=len(results), row_count=sum(result.row_count for result in results), results=results)

    def _resolve_factor_ids(self, factor_ids: list[str] | None) -> list[str]:
        if factor_ids:
            return factor_ids
        return [definition.factor_id for definition in self.list_factor_definitions()]

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return [symbol.strip() for symbol in symbols if symbol and symbol.strip()]
