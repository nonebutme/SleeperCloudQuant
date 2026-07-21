"""Smoke test for stage 68 strategy-library CRUD behavior."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.services import StrategyService

    database_path = Path("tmp") / f"stage68-strategy-library-{uuid4().hex}.sqlite3"
    service = StrategyService(
        database_path,
        legacy_drafts_path=Path("tmp") / "missing-strategy-drafts.json",
    )

    try:
        builtins = {item["strategy_id"] for item in service.list_strategies()}
        if "dual_ma_atr_dynamic_stop" not in builtins:
            raise SystemExit("stage68 smoke failed: dual MA ATR strategy is missing")

        source_v1 = "def generate_target_weights(bars, parameters):\n    return [0.25 for bar in bars]\n"
        saved_v1 = service.save_version(
            strategy_id="stage68_crud_probe",
            name="Stage 68 CRUD Probe",
            category="趋势跟随",
            description="用于验证策略库增删改查。",
            source_code=source_v1,
            parameters={"target_weight": 0.25},
        )
        if saved_v1["latest_version"] != "v1":
            raise SystemExit("stage68 smoke failed: first version was not v1")
        if saved_v1["category"] != "趋势跟随" or saved_v1["description"] != "用于验证策略库增删改查。":
            raise SystemExit("stage68 smoke failed: strategy metadata was not persisted")

        archived = service.archive_strategy("stage68_crud_probe")
        if archived["status"] != "archived":
            raise SystemExit("stage68 smoke failed: archive status mismatch")
        visible_ids = {item["strategy_id"] for item in service.list_strategies()}
        if "stage68_crud_probe" in visible_ids:
            raise SystemExit("stage68 smoke failed: archived strategy is still visible")
        if service.resolve_version("stage68_crud_probe", "v1")["source_sha256"] != saved_v1["source_sha256"]:
            raise SystemExit("stage68 smoke failed: archived strategy history is unavailable")

        source_v2 = "def generate_target_weights(bars, parameters):\n    return [0.5 for bar in bars]\n"
        saved_v2 = service.save_version(
            strategy_id="stage68_crud_probe",
            name="Stage 68 CRUD Probe Updated",
            category="自定义策略",
            description="归档后恢复并生成新版本。",
            source_code=source_v2,
            parameters={"target_weight": 0.5},
        )
        if saved_v2["latest_version"] != "v2":
            raise SystemExit("stage68 smoke failed: restored strategy was not versioned")
        restored = {item["strategy_id"]: item for item in service.list_strategies()}
        if "stage68_crud_probe" not in restored:
            raise SystemExit("stage68 smoke failed: saving did not restore archived strategy")
        if restored["stage68_crud_probe"]["name"] != "Stage 68 CRUD Probe Updated":
            raise SystemExit("stage68 smoke failed: restored metadata is stale")

        html = Path("web/index.html").read_text(encoding="utf-8")
        javascript = Path("web/app.js").read_text(encoding="utf-8")
        web_demo = Path("scripts/run_formal_web_demo.py").read_text(encoding="utf-8")
        http_adapter = Path("app/runtime/http_adapter.py").read_text(encoding="utf-8")
        required_html_markers = [
            'id="strategy-library-search"',
            'id="strategy-library-category"',
            'id="strategy-library-refresh"',
            'id="strategy-new"',
            'id="strategy-delete"',
            'id="strategy-draft-description"',
        ]
        if any(marker not in html for marker in required_html_markers):
            raise SystemExit("stage68 smoke failed: strategy manager controls are incomplete")
        required_javascript_markers = [
            "async function archiveSelectedStrategy()",
            'method: "DELETE"',
            "strategyCatalog = payload.strategies || []",
            'typeof compareSelectedExperiments === "function"',
        ]
        if any(marker not in javascript for marker in required_javascript_markers):
            raise SystemExit("stage68 smoke failed: strategy manager behavior contract is incomplete")
        if "def do_DELETE(self)" not in web_demo or "def do_DELETE(self)" not in http_adapter:
            raise SystemExit("stage68 smoke failed: DELETE forwarding is incomplete")

        print("stage68 strategy library CRUD smoke test passed")
    finally:
        database_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
