# 下一批真实开发执行记录（Batch 56）
时间：`2026-07-04`

## 本批目标

继续推进 `阶段 5：报告层（reporting）`，沿用 Batch 53-55 的最小消费增强策略，把既有 `failures.failure_code` 也收敛为一个稳定聚合字段：

- 在 reporting batch summary 中增加 `failure_code_counts`
- 只消费既有 `failures` 明细
- 不新增 backtest-kernel 生产字段
- 不回到 batch payload 一致性约束

## 本批实际落地

### 1. 为 batch summary 增加 `failure_code_counts`

- `reporting/batch_comparison_service.py`

本批继续复用已抽出的失败字段聚合 helper：

- 保留 `failure_type_counts`
- 保留 `failure_stage_counts`
- 基于 `failure_code` 增加 `failure_code_counts`

当前仅统计已有且非空的 `failure_code`，并按 key 排序输出，保持结果稳定。

### 2. 将 `failure_code_counts` 透出到应用层 reporting 模型

- `domain/report/models.py`
- `app/services/reporting_service.py`

本批为 `BatchExperimentSummaryModel` 增加：

- `failure_code_counts: dict[str, int]`

并在 `ReportingService.get_batch_summary()` 中完成映射透出。

### 3. 补齐 services / API / HTTP smoke 闭环

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

本批新增或补强以下验证：

- runtime failure summary 应得到 `{"BACKTEST_RUN_ONCE_RUNTIME_ERROR": 1}`
- unexpected status summary 应得到 `{"BACKTEST_UNEXPECTED_RESULT_STATUS": 1}`
- API route 与 HTTP JSON 均可稳定读取 `failure_code_counts`

## 本批为何这样切

这一步仍然严格停留在 reporting 消费层：

- 不改变 failures 的生产逻辑
- 不新增回测执行阶段字段
- 只把既有明细进一步整理成稳定聚合读取面

到这一批为止，`failure_type` / `failure_stage` / `failure_code` 三个核心机器可读字段都已经在 reporting batch summary 侧具备对应计数聚合。

## 验证结果

已通过：

- `python scripts\smoke_test_formal_services.py`
- `python scripts\smoke_test_formal_api.py`
- `python scripts\smoke_test_formal_http_adapter.py`
- `python scripts\run_formal_verifications.py`
- `git diff --check -- reporting/batch_comparison_service.py domain/report/models.py app/services/reporting_service.py scripts/smoke_test_formal_services.py scripts/smoke_test_formal_api.py scripts/smoke_test_formal_http_adapter.py`

## 下一步建议

1. `阶段 5：报告层（reporting）`：更适合停止继续加同级聚合字段，转向 reporting batch summary 字段边界文档化。
2. 如仍需继续做代码，更适合补一个只读 schema/API 边界说明型增强，而不是继续扩 failures 聚合种类。
