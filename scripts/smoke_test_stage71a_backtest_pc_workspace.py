"""Stage 71A smoke checks for the PC backtest workspace and soft deletion."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from _project_bootstrap import ensure_project_root_on_sys_path


class FakeMarketService:
    def list_a_share_symbols(self, *, market: str, limit: int, offset: int):
        rows = [
            {
                "symbol": "000001",
                "rqalpha_symbol": "000001.XSHE",
                "name": "Ping An Bank",
                "market": "SZSE",
                "listing_status": "current",
            }
        ]
        return {"total": len(rows), "items": rows[offset : offset + limit]}


class FakeStrategyService:
    def resolve_version(self, strategy_id: str, strategy_version: str | None):
        return {
            "strategy_id": strategy_id,
            "latest_version": strategy_version or "v1",
            "source_sha256": "a" * 64,
            "execution_contract": "generate_target_weights",
            "source_code": "def generate_target_weights(bars, parameters): return [0.0 for _ in bars]",
            "parameters": {},
        }


def require(text: str, marker: str, message: str) -> None:
    if marker not in text:
        raise SystemExit(message)


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
    from app.services.independent_screening_service import IndependentScreeningService
    from app.services.shared_portfolio_service import SharedPortfolioService

    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
    css = (root / "web" / "styles.css").read_text(encoding="utf-8")
    api = (root / "app" / "api" / "backtest.py").read_text(encoding="utf-8")

    for marker in (
        'document.querySelector(".backtest-workflow")?.remove()',
        'data-backtest-view-target="overview"]\')?.remove()',
        'researchTab.textContent = "研究实验"',
        '["strategy", "single", "independent", "portfolio", "research"]',
        'data-screening-delete',
        'data-portfolio-delete',
        'data-research-delete',
        'data-experiment-delete',
        'window.confirm',
        'method: "DELETE"',
        'function returnFromBacktestResults()',
    ):
        require(app_js, marker, f"Stage 71A UI contract missing: {marker}")
    require(css, "position: sticky", "Stage 71A smoke failed: desktop sidebar is not sticky")
    require(css, "grid-template-columns: repeat(4", "Stage 71A smoke failed: PC form grid missing")
    require(css, ".task-row-actions", "Stage 71A smoke failed: task row actions missing")
    for path in (
        "/api/backtest/independent-screening-tasks/{task_id}",
        "/api/backtest/shared-portfolio-tasks/{task_id}",
        "/api/backtest/experiments/index/{experiment_id}",
        "/api/backtest/parameter-matrix-tasks/{task_id}",
        "/api/backtest/research-tasks/{task_id}",
        "/api/backtest/results/{run_id}",
    ):
        require(api, path, f"Stage 71A delete route missing: {path}")

    (root / "tmp").mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="stage71a-", dir=root / "tmp", ignore_cleanup_errors=True) as temp_dir:
        temp = Path(temp_dir)
        strategy = FakeStrategyService()
        market = FakeMarketService()
        runtime = SqliteRuntimeStore(temp / "runtime.sqlite3")
        now = "2026-07-22T00:00:00+00:00"
        runtime.upsert_backtest_run(
            run_id="stage71a-run",
            strategy_name="Stage 71A",
            strategy_id="stage71a",
            status="completed",
            benchmark="000300.XSHG",
            universe="000001.XSHE",
            start_date="2020-01-01",
            end_date="2020-01-10",
            created_at=now,
            completed_at=now,
            parameters={},
            extra_config={},
            raw_result={},
        )
        deleted_run = runtime.soft_delete_backtest_run(
            "stage71a-run",
            deleted_at=now,
            reason="stage71a smoke",
        )
        if not deleted_run or runtime.fetch_backtest_run("stage71a-run") is not None:
            raise SystemExit("Stage 71A smoke failed: backtest run soft deletion is not hidden")

        independent = IndependentScreeningService(
            object(), market, strategy, runtime, temp / "independent.sqlite3"
        )
        independent.create_task(
            task_id="stage71a-independent",
            name="Stage 71A independent",
            strategy_id="stage71a",
            strategy_version="v1",
            symbols=["000001"],
            market="",
            start_date="2020-01-01",
            end_date="2020-01-10",
            adjustment="raw",
            benchmark="000300.XSHG",
            initial_cash=100000,
            parameters={},
            max_workers=1,
            retry_count=0,
            symbol_limit=1,
        )
        independent.delete_task("stage71a-independent")
        if independent.list_tasks(limit=10):
            raise SystemExit("Stage 71A smoke failed: deleted independent task remains listed")

        shared = SharedPortfolioService(
            market, strategy, runtime, temp / "portfolio.sqlite3"
        )
        shared.create_task(
            task_id="stage71a-portfolio",
            name="Stage 71A portfolio",
            strategy_id="stage71a",
            strategy_version="v1",
            symbols=["000001"],
            market="",
            start_date="2020-01-01",
            end_date="2020-01-10",
            adjustment="raw",
            benchmark="000300.XSHG",
            initial_cash=100000,
            parameters={},
            max_workers=1,
            symbol_limit=1,
            max_positions=1,
            portfolio_exposure=0.9,
            commission_rate=0.0003,
            min_commission=5,
            tax_rate=0.001,
            slippage_rate=0.0005,
        )
        shared.delete_task("stage71a-portfolio")
        if shared.list_tasks(limit=10):
            raise SystemExit("Stage 71A smoke failed: deleted portfolio task remains listed")

    print("Stage 71A PC workspace and soft deletion smoke passed")


if __name__ == "__main__":
    main()
