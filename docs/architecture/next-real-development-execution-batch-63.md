# 下一批真实开发执行记录（Batch 63）
时间：`2026-07-04`

## 本批目标

执行上一轮建议中的：

1. `[阶段 6：报告存储与模板边界]` 先定义“最小报告对象”字段范围
2. `[阶段 6：报告存储与模板边界]` 再判断这些字段里，哪些需要进入“快照存储”，哪些只属于展示模板

## 本批实际落地

### 1. 新增“报告对象与模板边界”文档

- `docs/architecture/report-object-and-template-boundaries.md`

本批基于当前 `domain/report/models.py` 与 reporting 冻结基线，明确区分了三层：

- 读取对象层
- 报告快照层
- 模板层

并给出了建议中的最小报告快照公共字段：

- `report_id`
- `report_type`
- `source_kind`
- `source_id`
- `title`
- `summary_text`
- `snapshot_payload`
- `created_at`

### 2. 明确哪些内容进入快照层，哪些留在模板层

本批正式写清：

- 报告身份、来源关联、生成时间与固定正文载荷，适合进入快照层
- 页面布局、区块标题、展示顺序、交互状态等内容，留在模板层或前端层
- route 包裹字段 `detail` / `summary` 不进入快照公共字段

### 3. 保持只文档化，不进入实现

本批不新增：

- dataclass
- repository
- storage schema
- template engine
- reporting service / api / schema 改动

## 本批为何这样切

当前最重要的不是急着实现快照存储，而是先把“报告对象”和“展示模板”分清，避免后续一上来就把页面结构、route contract 和报告事实揉在一起。

这一步更符合当前持续坚持的：

- 保守型
- 小步快跑
- 先验证后扩展
- 最小变更原则

## 验证结果

已完成验证：

- 读取并复核 `domain/report/models.py`
- 读取并复核 `docs/architecture/reporting-phase5-freeze-baseline.md`
- 读取并复核 `docs/architecture/reporting-readonly-route-contract.md`
- 读取并复核 `docs/verification/reporting-verification-baseline.md`
- `git diff --check -- docs/architecture/report-object-and-template-boundaries.md docs/architecture/next-real-development-execution-batch-63.md`

说明：本批仅新增文档与任务日志，不涉及生产代码与 smoke 逻辑改动。

## 下一步建议

1. `[阶段 6：报告存储与模板边界]` 继续补一份“报告快照最小字段草案”，把 `snapshot_payload` 的最小结构再收窄一层。
2. `[阶段 6：报告存储与模板边界]` 若还不进入实现，可补一份“快照存储触发条件”文档，明确什么情况下才值得引入 repository 或落库结构。