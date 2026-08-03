# VisActor VTable 全局采用基线

## 决策

- `已确认`：项目中所有能够表达为行列数据的数据表，统一使用 VisActor VTable。
- `已确认`：当前固定版本为 `@visactor/vtable@1.23.1`，采用本地 UMD 分发，
  不依赖浏览器运行时访问 CDN。
- `已确认`：现有原生表格由 `web/vtable-adapter.js` 自动增强为
  `VTable.ListTable`，保留原始表格作为可访问性语义和 CSV 导出数据源。
- `已确认`：表头排序、筛选、导出以及单个或多个行级操作继续复用原事件处理；
  Canvas 单元格点击会转发到对应的原始操作。
- `已确认`：VTable 继承 `quant-ui-global-standard.md` 的亮暗 Token，并按行情 32px、回测/因子 40px、编辑 48px 行高统一配置。

## 全局约束

1. 新增数据表不得直接形成第二套表格组件；应输出语义化 `<table>`，
   由 `window.AppVTable` 自动增强，或直接调用该适配层。
2. 禁止绕过固定版本改用公网 CDN、页面私有 VTable 副本或其他表格库。
3. K 线、净值曲线、热力图、定义列表、表单和卡片不是行列表格，不强制使用 VTable。
4. 只有 VTable 无法表达且涉及输入控件焦点、复杂编辑器或无障碍硬约束时，
   才可设置 `data-vtable-disabled="true"`；必须在本文登记原因、影响和替代方案。
5. 当前无已登记例外。

## 接入结构

```text
web/vendor/vtable/vtable.min.js
  -> window.VTable
  -> web/vtable-adapter.js
  -> window.AppVTable
  -> 静态表格 + 动态生成表格 + 报告表格 + 数据中心表格
```

## 当前覆盖

- 数据中心：行情口径、证券目录、日线、K 线原始数据、质量异常、版本快照。
- 市场数据：本地行情、数据浏览器。
- 回测与因子分析：筛选结果、交易/持仓/账户证据、绩效与因子比较。
- 报告：明细表、月度收益、批量摘要、实验比较。
- 治理：需求溯源表。

## 验证要求

- 静态检查固定版本、加载顺序、全局适配器和未登记例外。
- 浏览器检查 `window.VTable`、`window.AppVTable` 和 VTable Canvas 实例。
- 至少覆盖数据中心表格、动态报告表格以及带操作单元格的表格。
