"""Deterministic smoke test for stage-78.1 governance and pre-run binding."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from app.services.persistent_backtest_service import PersistentBacktestService
    from app.services.shared_portfolio_service import SharedPortfolioService
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.a_share_market_store import AShareMarketStore
    from domain.backtest.models import BacktestResultSummary, BacktestRunRequest
    from domain.common.enums import BacktestRunStatus

    with tempfile.TemporaryDirectory(
        prefix="scq-stage78-",
        ignore_cleanup_errors=True,
    ) as temporary:
        root = Path(temporary)
        market_path = root / "canonical.sqlite3"
        runtime_path = root / "runtime.sqlite3"
        market_store = AShareMarketStore(market_path)
        market_store.ensure_schema()
        market_store.upsert_symbols(
            [
                {
                    "symbol": "000001",
                    "name": "sample",
                    "listing_status": "current",
                    "source": "stage78-smoke",
                }
            ]
        )
        bars = [
            {
                "symbol": "000001",
                "date": trade_date,
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + 0.2,
                "volume": 1000,
                "amount": 10000,
            }
            for trade_date, price in (
                ("2026-07-20", 10.0),
                ("2026-07-21", 10.2),
                ("2026-07-22", 10.4),
                ("2026-07-23", 10.6),
                ("2026-07-24", 10.8),
            )
        ]
        for adjustment in ("raw", "qfq", "hfq"):
            market_store.upsert_daily_prices(
                bars,
                adjustment=adjustment,
                source="stage78-smoke",
            )

        governance = AShareGovernanceStore(market_path)
        governance.ensure_schema()
        governance.upsert_trade_calendar(
            [
                {
                    "market": "CN",
                    "trade_date": row["date"],
                    "is_open": True,
                    "session_status": "open",
                    "source": "stage78-smoke",
                }
                for row in bars
            ]
        )
        governance.upsert_index_prices(
            [
                {
                    "index_symbol": "000300",
                    "trade_date": row["date"],
                    "open": 4000,
                    "high": 4010,
                    "low": 3990,
                    "close": 4005,
                    "volume": 100,
                    "amount": 1000,
                    "source": "stage78-smoke",
                }
                for row in bars
            ]
        )
        governance.upsert_lifecycle_events(
            [
                {
                    "symbol": "000001",
                    "event_type": "listed",
                    "effective_from": "1991-04-03",
                    "source": "stage78-smoke",
                    "evidence": {"fixture": True},
                }
            ]
        )
        governance.upsert_trading_statuses(
            [
                {
                    "symbol": "000001",
                    "trade_date": row["date"],
                    "status": "normal",
                    "is_tradable": True,
                    "source": "stage78-smoke",
                    "evidence": {"fixture": True},
                }
                for row in bars
            ]
        )
        governance.upsert_corporate_actions(
            [
                {
                    "symbol": "000001",
                    "action_type": "distribution",
                    "report_period": "2025-12-31",
                    "announcement_date": "2026-03-01",
                    "record_date": "2026-06-01",
                    "ex_date": "2026-06-02",
                    "cash_ratio": 1.0,
                    "status": "implemented",
                    "source": "stage78-smoke",
                    "evidence": {"fixture": True},
                }
            ]
        )
        governance.upsert_adjustment_factors(
            [
                {
                    "symbol": "000001",
                    "trade_date": row["date"],
                    "factor_method": "observed_qfq_close_ratio",
                    "factor": 1.0,
                    "base_date": "2026-07-24",
                    "source": "stage78-smoke",
                    "quality_status": "passed",
                    "evidence": {"fixture": True},
                }
                for row in bars
            ]
        )
        report = governance.save_quality_report(
            quality_report_id="stage78-smoke-quality",
            rule_version="stage78.1-quality-v1",
            status="passed",
            payload={"checks": [{"name": "fixture", "status": "passed"}]},
        )
        if report.get("status") != "passed":
            raise SystemExit("stage78 smoke failed: quality report not persisted")
        members = [
            {
                "dataset": "market_daily_prices",
                "adjustment": adjustment,
                "symbol_scope": "fixture",
                "row_count": 5,
                "symbol_count": 1,
                "min_date": "2026-07-20",
                "max_date": "2026-07-24",
                "source": "stage78-smoke",
                "quality_status": "passed",
            }
            for adjustment in ("raw", "qfq", "hfq")
        ]
        members.extend(
            [
                {
                    "dataset": dataset,
                    "symbol_scope": "fixture",
                    "row_count": 1,
                    "symbol_count": 1,
                    "min_date": "2026-07-20",
                    "max_date": "2026-07-24",
                    "source": "stage78-smoke",
                    "quality_status": "passed",
                }
                for dataset in (
                    "market_trade_calendar",
                    "market_index_daily_prices",
                    "security_lifecycle_events",
                    "security_trading_status_daily",
                    "corporate_action_events",
                    "price_adjustment_factors",
                )
            ]
        )
        version = governance.publish_data_version(
            as_of_trade_date="2026-07-24",
            quality_report_id="stage78-smoke-quality",
            members=members,
            notes="stage78 deterministic smoke",
        )
        version_id = str(version.get("data_version_id") or "")
        if not version_id or version.get("status") != "published":
            raise SystemExit("stage78 smoke failed: data version not published")

        resolved = governance.resolve_published_data_version(
            symbol="000001.XSHE",
            adjustment="raw",
            start_date="2026-07-20",
            end_date="2026-07-24",
            benchmark="000300.XSHG",
        )
        if resolved.get("status") != "bound" or resolved.get("data_version") != version_id:
            raise SystemExit("stage78 smoke failed: published version resolution failed")

        runtime_store = SqliteRuntimeStore(runtime_path)
        runtime_store.ensure_schema()
        fake_runtime = _FakeBacktestRuntime(BacktestResultSummary, BacktestRunStatus)
        market_service = _PublishedVersionService(governance)
        persistent = PersistentBacktestService(fake_runtime, runtime_store, market_service)
        request = BacktestRunRequest(
            run_id="stage78-smoke-run",
            strategy_name="fixture",
            strategy_id="fixture",
            symbol="000001.XSHE",
            benchmark="000300.XSHG",
            start_date="2026-07-20",
            end_date="2026-07-24",
            extra_config={"adjustment": "raw"},
        )
        persistent.run_once(request)
        snapshot = runtime_store.fetch_backtest_input_snapshot("stage78-smoke-run")
        if snapshot.get("data_version") != version_id:
            raise SystemExit("stage78 smoke failed: input snapshot version mismatch")
        if fake_runtime.call_count != 1:
            raise SystemExit("stage78 smoke failed: fake runtime call count mismatch")

        empty_governance = AShareGovernanceStore(root / "empty-governance.sqlite3")
        empty_governance.ensure_schema()
        blocked_runtime = _FakeBacktestRuntime(BacktestResultSummary, BacktestRunStatus)
        blocked_service = PersistentBacktestService(
            blocked_runtime,
            SqliteRuntimeStore(root / "blocked-runtime.sqlite3"),
            _PublishedVersionService(empty_governance),
        )
        try:
            blocked_service.run_once(
                BacktestRunRequest(
                    run_id="stage78-blocked-run",
                    strategy_name="fixture",
                    symbol="000001.XSHE",
                    benchmark="000300.XSHG",
                    start_date="2026-07-20",
                    end_date="2026-07-24",
                )
            )
        except RuntimeError as error:
            if "data_not_ready" not in str(error):
                raise
        else:
            raise SystemExit("stage78 smoke failed: missing version did not block")
        if blocked_runtime.call_count != 0:
            raise SystemExit("stage78 smoke failed: runtime executed without version")

        portfolio = SharedPortfolioService(
            _PortfolioMarketService(governance),
            _PortfolioStrategyService(),
            runtime_store,
            database_path=root / "portfolio.sqlite3",
        )
        task = portfolio.create_task(
            task_id="stage78-portfolio",
            name="stage78 portfolio",
            strategy_id="fixture",
            strategy_version="v1",
            symbols=["000001"],
            market="",
            start_date="2026-07-20",
            end_date="2026-07-24",
            adjustment="raw",
            benchmark="000300",
            initial_cash=100000,
            parameters={},
            max_workers=1,
            symbol_limit=1,
            max_positions=1,
            portfolio_exposure=1.0,
            commission_rate=0.0003,
            min_commission=5.0,
            tax_rate=0.001,
            slippage_rate=0.0,
        )
        frozen = dict(task.get("config") or {}).get("data_version_binding") or {}
        if frozen.get("data_version") != version_id:
            raise SystemExit("stage78 smoke failed: portfolio version not frozen")

        overview = governance.get_overview()
        if overview.get("schema_version") != "78.1.0":
            raise SystemExit("stage78 smoke failed: governance schema version mismatch")
        print(
            "stage78 data governance smoke test passed "
            f"version={version_id} snapshot={snapshot.get('snapshot_id')}"
        )


class _FakeBacktestRuntime:
    def __init__(self, summary_type: Any, status_type: Any) -> None:
        self._summary_type = summary_type
        self._status_type = status_type
        self.call_count = 0

    def run_once_with_raw_result(self, request: Any) -> tuple[Any, dict[str, Any]]:
        self.call_count += 1
        return (
            self._summary_type(
                run_id=request.run_id,
                strategy_name=request.strategy_name,
                status=self._status_type.COMPLETED,
                start_date=request.start_date,
                end_date=request.end_date,
                benchmark=request.benchmark,
                metrics={"total_returns": 0.01},
            ),
            {
                "logs": [],
                "trades": [],
                "positions": [],
                "accounts": [],
                "yearly_returns": [],
            },
        )


class _PublishedVersionService:
    def __init__(self, governance: Any) -> None:
        self._governance = governance

    def get_published_data_version(self, **kwargs: Any) -> dict[str, Any]:
        return self._governance.resolve_published_data_version(**kwargs)


class _PortfolioMarketService(_PublishedVersionService):
    def list_a_share_symbols(
        self,
        *,
        market: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        items = [] if offset else [
            {
                "symbol": "000001",
                "rqalpha_symbol": "000001.XSHE",
                "name": "sample",
                "market": "SZSE",
                "listing_status": "current",
            }
        ]
        return {"total": 1, "items": items}


class _PortfolioStrategyService:
    def resolve_version(self, strategy_id: str, version: str | None) -> dict[str, Any]:
        return {
            "strategy_id": strategy_id,
            "latest_version": version or "v1",
            "source_sha256": "fixture",
            "execution_contract": "target-weights-v1",
            "source_code": "def generate_target_weights(context): return {}",
        }


if __name__ == "__main__":
    main()
