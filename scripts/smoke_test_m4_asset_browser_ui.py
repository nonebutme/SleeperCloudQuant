"""Static contract checks for the redesigned M4 asset browser."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    script = (root / "web" / "m4_asset_browser.js").read_text(encoding="utf-8")
    styles = (root / "web" / "m4_asset_browser.css").read_text(encoding="utf-8")
    app = (root / "web" / "app.js").read_text(encoding="utf-8")

    assert "�" not in html
    assert html.count('id="dc-view-assets"') == 1
    assert html.count('id="a-share-symbol-form"') == 1
    assert html.count('id="a-share-daily-form"') == 1
    assert html.count('id="a-share-daily-chart"') == 1
    assert html.count('id="a-share-overview"') == 1
    assert html.index('id="a-share-overview"') < html.index('id="dc-view-assets"')
    assert "A 股数据基座与兼容工具" not in html
    assert 'id="market-query-form"' not in html
    assert 'id="backtest-asset-directory-form"' not in html
    assert "/m4_asset_browser.css?v=1" in html
    assert "/m4_asset_browser.js?v=1" in html
    assert 'class="dc-m4-layout"' in html
    assert html.count("data-m4-node") >= 25
    for label in ("沪深 A 股", "沪深300", "恒生指数", "MSCI全球", "资产负债表", "行业分类", "新闻公告"):
        assert label in html
    assert 'data-vtable-mode="market"' in html
    assert "选择 K 线交易日查看市场全景" in html
    assert html.count('class="dc-m4-panorama-card') == 5
    for panel_id in ("dc-m4-industry-heatmap", "dc-m4-concept-heatmap", "dc-m4-industry-flow", "dc-m4-concept-flow", "dc-m4-events"):
        assert f'id="{panel_id}"' in html
    assert "/api/market/panorama" in script
    assert 'data-vtable-mode="market"' in script
    assert "不展示模拟行情" in html
    assert "data-m4-jump-sync" in html
    assert "data-kline-date" in app
    for period in ("5:", "10:", "20:", "60:"):
        assert period in app
    assert "volumeBottom" in app
    assert "bindKlineDrilldown" in script
    assert "filterTree" in script
    assert "showUnavailable" in script
    assert "grid-template-columns: 268px minmax(0, 1fr)" in styles
    assert "@media (max-width: 980px)" in styles

    print("M4 asset browser UI smoke passed")


if __name__ == "__main__":
    main()
