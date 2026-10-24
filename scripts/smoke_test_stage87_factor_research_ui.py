"""Static UI contract smoke test for the stage 87 factor workspace."""

from __future__ import annotations

from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    root = Path(__file__).resolve().parent.parent
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    script = (root / "web" / "factor_research.js").read_text(encoding="utf-8")
    app_script = (root / "web" / "app.js").read_text(encoding="utf-8")
    style = (root / "web" / "factor_research.css").read_text(encoding="utf-8")

    required_ids = {
        "page-factor",
        "factor-dashboard-body",
        "factor-research-form",
        "factor-definition-form",
        "factor-definition-validate",
        "factor-definition-output",
        "factor-profile-dialog",
        "factor-profile-overview",
        "factor-profile-evidence",
        "factor-profile-versions",
        "factor-profile-version-body",
        "factor-profile-create-version",
        "factor-profile-start-research",
        "factor-definition-new",
        "factor-report-back",
        "factor-report-context",
        "factor-acceptance-body",
        "factor-sample-body",
        "factor-annual-body",
        "factor-cost-stress-body",
        "factor-oos-reveal-toolbar",
        "multi-factor-form",
        "multi-factor-correlation-body",
        "factor-governance-output",
        "factor-monitoring-output",
        "factor-preflight",
        "factor-task-body",
        "factor-report-summary",
        "factor-ic-chart",
        "factor-nav-chart",
        "factor-decay-body",
        "factor-industry-body",
        "factor-stock-body",
        "factor-compare-report-ids",
        "factor-compare-run",
        "factor-compare-body",
        "factor-artifact-body",
        "factor-optimization-form",
        "factor-optimization-task-body",
        "factor-strategy-declaration-output",
        "factor-optimization-report-output",
    }
    missing = sorted(item for item in required_ids if f'id="{item}"' not in html)
    if missing:
        raise SystemExit(f"stage87 UI smoke failed: missing DOM ids {missing}")
    if html.count('id="page-factor"') != 1 or 'id="page-factor-legacy"' not in html:
        raise SystemExit("stage87 UI smoke failed: formal/legacy factor page boundary mismatch")
    if "/factor_research.css?v=924" not in html:
        raise SystemExit("stage87 UI smoke failed: stylesheet is not wired")
    if html.index("/factor_research.js?v=924") > html.index("/app.js?v=923"):
        raise SystemExit("stage87 UI smoke failed: formal factor loader must precede app bootstrap")
    if html.count('data-vtable-mode="factor"') < 6:
        raise SystemExit("stage87 UI smoke failed: factor tables are not routed through VTable")
    for label in ("因子库", "因子开发", "因子研究", "研究任务", "研究报告", "多因子研究", "因子发布与应用"):
        if label not in html:
            raise SystemExit(f"stage87 UI smoke failed: missing factor workflow label {label}")
    if 'data-factor-view-target="report">研究报告</button>' not in html:
        raise SystemExit("stage87 UI smoke failed: factor report is not represented in navigation")
    if "因子分析工作台" in html or 'class="factor-hero' in html:
        raise SystemExit("stage87 UI smoke failed: duplicate factor hero was not removed")
    if 'class="factor-status-strip"' in html or "受控研究 · 结果不构成投资建议" in html:
        raise SystemExit("stage87 UI smoke failed: redundant factor status strip still exists")
    if "R3 标准因子研究证据</h3>" in html:
        raise SystemExit("stage87 UI smoke failed: R3 evidence must be scoped to factor detail")
    for label in ("基本信息", "研究证据", "版本记录"):
        if f">{label}</button>" not in html:
            raise SystemExit(f"stage87 UI smoke failed: missing factor detail tab {label}")
    for label in ("详情</button></td><td>", "开始研究</button></td><td>", "查看报告</button>"):
        if label not in script:
            raise SystemExit(f"stage87 UI smoke failed: missing direct factor action {label}")

    required_script_fragments = {
        "window.loadFactors",
        "/api/factor-research/definitions",
        "/api/factor-research/definitions/validate",
        "publishDefinition",
        "/api/factor-research/preflight",
        "/api/factor-research/tasks",
        "/api/factor-research/reports/",
        "/compare?",
        "index_component_facts_unavailable",
        "/api/factor-research/artifacts",
        "/strategy-declaration",
        "/api/factor-research/optimization/preflight",
        "/api/factor-research/optimization/tasks",
        "aligned_value",
        "scheduleOptimizationPoll",
        "/api/factor-research/multi-factor/research",
        "/review",
        "/register",
        "/monitor",
        "/reveal-out-of-sample",
        "activateFactorProfileTab",
        "renderFactorProfileEvidence",
        "createVersionFromProfile",
        "syncFactorPageTitle",
        "renderReportNavigation",
    }
    missing_script = sorted(item for item in required_script_fragments if item not in script)
    if missing_script:
        raise SystemExit(f"stage87 UI smoke failed: missing script contracts {missing_script}")
    if "function loadLegacyFactors" not in app_script:
        raise SystemExit("stage87 UI smoke failed: legacy loader isolation missing")
    if 'window.syncFactorPageTitle?.()' not in app_script:
        raise SystemExit("stage87 UI smoke failed: global title does not follow factor subview")
    if chr(0) in html or chr(0) in script or "pppp" in html or "pppp" in script:
        raise SystemExit("stage87 UI smoke failed: encoding damage marker found")
    for token in ("--q-", ".factor-workspace", ".factor-report-grid", "@media"):
        if token not in style:
            raise SystemExit(f"stage87 UI smoke failed: style contract missing {token}")

    print("stage87 factor research UI smoke test passed")


if __name__ == "__main__":
    main()
