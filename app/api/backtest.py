from __future__ import annotations

from app.api.contracts import RouteDefinition
from app.schemas.backtest import BacktestRunRequestPayload, BacktestRunResponsePayload
from app.services.backtest_service import BacktestService
from domain.backtest import BacktestRunRequest



def run_once(service: BacktestService, payload: BacktestRunRequestPayload) -> BacktestRunResponsePayload:
    result = service.run_once(
        BacktestRunRequest(
            run_id=payload.run_id,
            strategy_name=payload.strategy_name,
            symbol=payload.symbol,
            benchmark=payload.benchmark,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_cash=payload.initial_cash,
            frequency=payload.frequency,
            parameters=payload.parameters,
            extra_config=payload.extra_config,
        )
    )
    return BacktestRunResponsePayload(result=result)



def build_backtest_routes(service: BacktestService) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="POST",
            path="/api/backtest/run-once",
            name="backtest_run_once",
            handler=lambda payload: run_once(service, payload),
            request_model=BacktestRunRequestPayload,
        )
    ]
