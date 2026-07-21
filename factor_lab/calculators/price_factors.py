"""Minimal price-based factor calculators."""

from __future__ import annotations

from collections.abc import Sequence

from domain.market.models import Bar
from factor_lab.models import FactorDefinition, FactorValue


class CloseToCloseReturnCalculator:
    """Compute one-day close-to-close return values from price bars."""

    factor_id = "close_to_close_return_1d"
    factor_name = "Close To Close Return 1D"

    def definition(self) -> FactorDefinition:
        return FactorDefinition(
            factor_id=self.factor_id,
            name=self.factor_name,
        )

    def calculate(self, *, symbol: str, bars: Sequence[Bar]) -> list[FactorValue]:
        rows: list[FactorValue] = []
        previous_close: float | None = None
        for bar in bars:
            if previous_close is None:
                previous_close = bar.close
                continue
            if previous_close == 0:
                previous_close = bar.close
                continue
            rows.append(
                FactorValue(
                    factor_id=self.factor_id,
                    symbol=symbol,
                    trade_date=bar.date,
                    value=(bar.close / previous_close) - 1.0,
                )
            )
            previous_close = bar.close
        return rows


class CloseToMa2BiasCalculator:
    """Compute close-to-2day-moving-average bias values from price bars."""

    factor_id = "close_to_ma2_bias"
    factor_name = "Close To MA2 Bias"

    def definition(self) -> FactorDefinition:
        return FactorDefinition(
            factor_id=self.factor_id,
            name=self.factor_name,
            parameters={"window": 2},
        )

    def calculate(self, *, symbol: str, bars: Sequence[Bar]) -> list[FactorValue]:
        rows: list[FactorValue] = []
        closes: list[float] = []
        for bar in bars:
            closes.append(bar.close)
            if len(closes) < 2:
                continue
            moving_average = (closes[-1] + closes[-2]) / 2.0
            if moving_average == 0:
                continue
            rows.append(
                FactorValue(
                    factor_id=self.factor_id,
                    symbol=symbol,
                    trade_date=bar.date,
                    value=(bar.close / moving_average) - 1.0,
                )
            )
        return rows
