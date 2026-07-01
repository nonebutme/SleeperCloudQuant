"""Rqalpha/Ricequant gateway for phase-1 backtest execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from config_center.providers.ricequant_config import RicequantConfig
from backtest_kernel.gateway.contracts import (
    BacktestGateway,
    BacktestRequest,
    BacktestResult,
)


class RqalphaRuntimeProtocol(Protocol):
    """Minimal runtime protocol expected by the phase-1 gateway."""

    def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Execute one raw backtest payload."""


class RqalphaRicequantGateway(BacktestGateway):
    """Gateway that becomes executable once a runtime implementation is injected."""

    def __init__(
        self,
        config: RicequantConfig,
        *,
        runtime: RqalphaRuntimeProtocol | None = None,
    ) -> None:
        self._config = config
        self._runtime = runtime

    @property
    def config(self) -> RicequantConfig:
        """Return the active runtime configuration."""

        return self._config

    @property
    def runtime(self) -> RqalphaRuntimeProtocol | None:
        """Return the injected runtime, if any."""

        return self._runtime

    def run_backtest(self, request: BacktestRequest) -> BacktestResult:
        runtime = self._require_runtime()
        payload = build_runtime_payload(request)
        raw_result = runtime.run(payload)
        return normalize_runtime_result(request, raw_result)

    def _require_runtime(self) -> RqalphaRuntimeProtocol:
        if self._runtime is None:
            raise NotImplementedError(
                "No rqalpha runtime is injected yet. "
                "Provide a RqalphaRuntimeProtocol implementation to enable runtime calls."
            )
        return self._runtime



def build_runtime_payload(request: BacktestRequest) -> dict[str, Any]:
    """Convert a normalized request into a runtime-facing payload."""

    return {
        "run_id": request.run_id,
        "strategy_name": request.strategy_name,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "benchmark": request.benchmark,
        "initial_cash": request.initial_cash,
        "frequency": request.frequency,
        "parameters": dict(request.parameters),
        "extra_config": dict(request.extra_config),
    }



def normalize_runtime_result(
    request: BacktestRequest,
    payload: Mapping[str, Any],
) -> BacktestResult:
    """Normalize a runtime response into the phase-1 result shape."""

    metrics = payload.get("metrics")
    raw_result = payload.get("raw_result")
    return BacktestResult(
        run_id=str(payload.get("run_id") or request.run_id),
        strategy_name=str(payload.get("strategy_name") or request.strategy_name),
        status=str(payload.get("status") or "completed"),
        start_date=str(payload.get("start_date") or request.start_date),
        end_date=str(payload.get("end_date") or request.end_date),
        benchmark=str(payload.get("benchmark") or request.benchmark),
        metrics=dict(metrics) if isinstance(metrics, Mapping) else {},
        raw_result=dict(raw_result) if isinstance(raw_result, Mapping) else dict(payload),
    )
