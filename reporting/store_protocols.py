"""Store protocols for reporting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol


class ReportingStore(Protocol):
    """Minimal store protocol required by the reporting layer."""

    def fetch_backtest_run(self, run_id: str) -> Mapping[str, Any] | None:
        """Return one archived backtest run."""

    def fetch_backtest_metrics(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        """Return metric rows for one archived backtest run."""

    def fetch_backtest_logs(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        """Return log rows for one archived backtest run."""

    def fetch_backtest_trades(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        """Return trade rows for one archived backtest run."""

    def fetch_backtest_positions(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        """Return position rows for one archived backtest run."""

    def fetch_backtest_accounts(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        """Return account rows for one archived backtest run."""

    def fetch_backtest_yearly_returns(
        self,
        run_id: str,
    ) -> Sequence[Mapping[str, Any]]:
        """Return yearly return rows for one archived backtest run."""

    def fetch_research_run(self, run_id: str) -> Mapping[str, Any] | None:
        """Return one archived research run."""
