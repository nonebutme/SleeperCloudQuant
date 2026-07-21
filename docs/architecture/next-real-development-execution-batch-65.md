# 下一批真实开发执行记录（Batch 65）
时间：`2026-07-04`

## 本批目标

执行上一轮建议中的：

- `[阶段 6：报告存储与模板边界]` 继续补一份“报告快照最小字段草案”，把 `snapshot_payload` 的最小结构再收窄一层

## 本批实际落地

### 1. 新增“报告快照最小字段草案”文档

- `docs/architecture/report-snapshot-payload-minimal-draft.md`

本批把 `snapshot_payload` 从“一个固定正文载荷”继续收窄为最小公共骨架：

- `headline`
- `key_stats`
- `body`
- `generated_from`

### 2. 补充当前两类报告的最小映射建议

本批基于当前已有两类读取对象，分别给出：

- `backtest_run_detail` 的最小快照正文建议
- `batch_experiment_summary` 的最小快照正文建议

这样后续如果真的进入实现，就不会直接从一个完全开放的 `snapshot_payload` 开始。

### 3. 保持只文档化，不进入 schema 设计

本批仍然不新增：

- dataclass
- repository
- route
- storage schema
- template engine

## 本批为何这样切

在阶段 6 里，先把“何时值得存”和“存什么最小结构”分两步做清楚，会比一次性把快照模型写死更稳。

当前这一步的价值在于：

- 继续压缩未来实现的自由度范围
- 但不把结构定细到过早架构化
- 保持实现前的判断成本低、回退成本低

## 验证结果

已完成验证：

- 读取并复核 `docs/architecture/report-object-and-template-boundaries.md`
- 读取并复核 `docs/architecture/report-snapshot-storage-trigger-conditions.md`
- `git diff --check -- docs/architecture/report-snapshot-payload-minimal-draft.md docs/architecture/next-real-development-execution-batch-65.md`

说明：本批仅新增文档与任务日志，不涉及生产代码和 smoke 逻辑改动。

## 下一步建议

1. `[阶段 6：报告存储与模板边界]` 如果继续停留在文档层，可补一份“首批支持的 report_type 范围”说明。
2. `[阶段 6：报告存储与模板边界]` 如果准备进入实现，先回看 batch-64 的触发条件，确认是否真的需要 repository / 落库结构。