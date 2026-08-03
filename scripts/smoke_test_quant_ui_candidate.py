from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "quant-ui-candidate.css").read_text(encoding="utf-8")
    script = (ROOT / "web" / "quant-ui-candidate.js").read_text(encoding="utf-8")
    vtable = (ROOT / "web" / "vtable-adapter.js").read_text(encoding="utf-8")

    require(index.count("/quant-ui-candidate.css?v=2") == 1, "全局主题样式未唯一加载")
    require(index.count("/quant-ui-candidate.js?v=2") == 1, "全局主题脚本未唯一加载")
    require(index.index("/quant-ui-candidate.css") > index.index("/data_center.css"), "全局主题必须最后覆盖业务样式")
    require(index.index("/quant-ui-candidate.js") > index.index("/app.js"), "全局主题脚本必须在业务脚本后加载")

    required_tokens = (
        "--q-primary: #1677ff",
        "--q-profit: #f53f3f",
        "--q-loss: #00b42a",
        "--q-warning: #ff7d00",
        "--q-bg-page: #f2f3f5",
        "--q-bg-card: #ffffff",
        "--q-border: #e5e6eb",
        "--q-sidebar-width: 256px",
    )
    for token in required_tokens:
        require(token in styles.lower(), f"缺少设计 Token：{token}")
    require('html[data-theme="dark"]' in styles, "缺少暗色盯盘主题")
    require("prefers-reduced-motion" in styles, "缺少减少动画无障碍适配")
    require("量化 UI 规范 · 全局生效" in script, "缺少全局规范状态标识")
    require("releaseAll" in script and "enhanceAll" in script, "主题切换未刷新 VTable")
    require("financialDirection" in vtable and "formatFinancialValue" in vtable, "VTable 缺少金融箭头格式化")
    require("frozenColCount" in vtable and "modeRowHeight" in vtable, "VTable 缺少业务模式与冻结列配置")
    require('document.documentElement.dataset.theme || "light"' in vtable, "VTable 签名未绑定主题")

    print("quant UI global standard static smoke passed")


if __name__ == "__main__":
    main()
