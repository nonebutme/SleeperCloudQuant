# 下一批真实开发执行记录（Batch 55）
时间：`2026-07-04`

## 本批目标

继续推进 `阶段 5：报告层（reporting）`，在 `failure_type_counts` 已完成 service/API/HTTP 透出验证的基础上，再补一个同级、同策略的最小消费增强点：

- 基于既有 `failures.failure_stage`
- 在 reporting batch summary 中增加 `failure_stage_counts`
- 不新增 backtest-kernel 生产字段
- 不回到 batch payload 一致性约束

## 本批实际落地

### 1. 为 batch summary 增加 `failure_stage_counts`

- `reporting/batch_comparison_service.py`

本批复用已有的失败摘要聚合思路：

- 保留 `failure_type_counts`
- 抽出通用的失败字段计数 helper
- 基于 `failure_stage` 生成稳定的 `dict[str, int]`

当前只统计已有且非空的 `failure_stage`，并按 key 排序输出。

### 2. 将 `failure_stage_counts` 透出到应用层 reporting 模型

- `domain/report/models.py`
- `app/services/reporting_service.py`

本批为 `BatchExperimentSummaryModel` 增加：

- `failure_stage_counts: dict[str, int]`

并在 `ReportingService.get_batch_summary()` 中完成映射透出。

### 3. 补齐 services / API / HTTP smoke 闭环

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

本批新增或补强以下验证：

- runtime failure summary 应得到 `{"run_once": 1}`
- unexpected status summary 应得到 `{"result_status_check": 1}`
- API route 与 HTTP JSON 均可稳定读取 `failure_stage_counts`

## 本批为何这样切

这一步与 Batch 53 / 54 完全保持同一阶段策略：

- 只消费已稳定存在的 failures 明细字段
- 不改失败生产逻辑
- 不把 reporting 扩展成复杂报告系统

这样可以持续提高报告层读取面的一致性，同时把风险控制在最小范围内。

## 验证结果

已通过：

- `python scripts\smoke_test_formal_services.py`
- `python scripts\smoke_test_formal_api.py`
- `python scripts\smoke_test_formal_http_adapter.py`
- `python scripts\run_formal_verifications.py`
- `git diff --check -- reporting/batch_comparison_service.py domain/report/models.py app/services/reporting_service.py scripts/smoke_test_formal_services.py scripts/smoke_test_formal_api.py scripts/smoke_test_formal_http_adapter.py`

## 下一步建议

1. `阶段 5：报告层（reporting）`：如果继续保持同样节奏，可评估 `failure_code_counts` 是否值得做成最后一个同级聚合字段。
2. 如果不想继续加聚合字段，更适合转向 reporting batch summary 字段边界文档化，明确明细字段与聚合字段关系。
