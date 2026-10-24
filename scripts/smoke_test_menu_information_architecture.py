"""Static contract smoke test for the unified business navigation."""

from __future__ import annotations

import re
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
    datasets_js = (root / "web" / "strategy-datasets.js").read_text(encoding="utf-8")

    sidebar = html.split('<nav class="nav-tabs"', 1)[1].split("</nav>", 1)[0]
    top_level = re.findall(
        r'<button class="nav-tab[^>]*data-page="([^"]+)"[^>]*data-nav-group="([^"]+)"[^>]*>([^<]+)</button>',
        sidebar,
    )
    assert top_level == [
        ("market", "market-data", "市场数据"),
        ("market", "market", "数据中心"),
        ("strategy-datasets", "datasets", "数据集"),
        ("factor", "factor", "因子分析"),
        ("backtest", "backtest", "策略回测"),
        ("dashboard", "dashboard", "工作台"),
        ("ai", "reporting", "报告与复盘"),
        ("config", "config", "系统设置"),
    ], top_level

    for group in ("market-data", "market", "datasets", "factor", "backtest", "reporting", "config"):
        assert f'data-nav-submenu="{group}"' in sidebar
    for category in ("个股行情", "行业板块", "概念板块", "新闻公告"):
        assert f'data-market-category="{category}"' in sidebar
    for view in ("catalog", "detail"):
        assert f'data-strategy-dataset-view="{view}"' in sidebar
    for view in ("dashboard", "detail", "tasks", "report", "artifacts"):
        assert f'data-factor-view-target="{view}"' in sidebar
    factor_subnav = sidebar.split('data-nav-submenu="factor"', 1)[1].split("</div>", 1)[0]
    factor_labels = re.findall(r'data-factor-view-target="[^"]+">([^<]+)</button>', factor_subnav)
    assert factor_labels == [
        "因子库", "因子开发", "因子研究", "研究任务", "研究报告", "多因子研究", "因子发布与应用",
    ], factor_labels
    for workspace in ("strategy", "create", "tasks", "research", "results"):
        assert f'data-stage76-workspace="{workspace}"' in sidebar
    for page in ("reporting", "ai", "report-management", "traceability"):
        assert f'data-route-page="{page}"' in sidebar
    assert 'data-route-page="reporting" data-nav-context="backtest">回测分析与复盘' in sidebar

    assert 'button.dataset.page = "strategy-datasets"' not in datasets_js
    assert 'button.dataset.page = "report-management"' not in app_js
    assert "pageNavigationGroups" in app_js
    assert '"strategy-datasets": "datasets"' in app_js
    assert 'reporting: "backtest"' in app_js
    assert "openMarketDataCategory" in app_js
    assert "popstate" in app_js
    assert "91.4" not in sidebar

    print("unified menu information architecture smoke passed")


if __name__ == "__main__":
    main()
