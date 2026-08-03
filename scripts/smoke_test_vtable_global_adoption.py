from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    adapter = (ROOT / "web" / "vtable-adapter.js").read_text(encoding="utf-8")
    policy = (ROOT / "docs" / "architecture" / "vtable-global-adoption.md").read_text(encoding="utf-8")
    vendor = ROOT / "web" / "vendor" / "vtable" / "vtable.min.js"
    metadata = (ROOT / "web" / "vendor" / "vtable" / "package.json").read_text(encoding="utf-8")

    require(vendor.stat().st_size > 1_000_000, "VTable 本地分发文件缺失或不完整")
    require('"version": "1.23.1"' in metadata, "VTable 包元数据版本未固定为 1.23.1")
    require(index.index("/vendor/vtable/vtable.min.js") < index.index("/vtable-adapter.js"), "VTable 必须先于适配层加载")
    require(index.index("/vtable-adapter.js") < index.index("/app.js"), "全局适配层必须先于业务脚本加载")
    require("window.VTable?.ListTable" in adapter, "适配层缺少 VTable ListTable 检查")
    require("MutationObserver" in adapter, "适配层缺少动态表格观察")
    require("button, a[href]" in adapter, "适配层缺少行级操作转发")
    require('data-vtable-disabled="true"' in policy, "技术基线缺少例外登记规则")

    web_sources = [ROOT / "web" / name for name in ("index.html", "app.js", "data_center.js", "report-ui.js")]
    disabled = sum(path.read_text(encoding="utf-8").count('data-vtable-disabled="true"') for path in web_sources)
    require(disabled == 0, f"发现 {disabled} 个未登记的 VTable 禁用点")
    print("VTable 全局采用专项静态验证通过")


if __name__ == "__main__":
    main()
