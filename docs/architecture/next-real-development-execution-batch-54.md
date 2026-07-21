# 下一批真实开发执行记录（Batch 54）
时间：`2026-07-04`

## 本批目标

继续推进 `阶段 5：报告层（reporting）`，在 Batch 53 已完成 `failure_type_counts` service/model 透出的基础上，补齐 API 与 HTTP adapter 的最小验证闭环。

本批不新增生产字段，不改 backtest-kernel，不扩展 batch payload 约束。

## 本批实际落地

### 1. 补齐 reporting API 层 `failure_type_counts` 透出验证

- `scripts/smoke_test_formal_api.py`

本批在 formal API smoke 中直接 seed 一个失败 batch research run，并通过 `reporting_batch_summary` route 读取：

- `runtime_error: 1`
- `unexpected_status: 1`

验证 `BatchExperimentSummaryModel.failure_type_counts` 可以经 API route 正常读取。

### 2. 补齐 reporting HTTP 层 `failure_type_counts` JSON 透出验证

- `scripts/smoke_test_formal_http_adapter.py`

本批在 HTTP adapter smoke 中向 demo runtime store seed 一个失败 batch research run，并通过：

- `GET /api/reporting/batch-summary/http-batch-failure-001`

验证 HTTP JSON 响应中包含：

- `summary.failure_type_counts == {"runtime_error": 1, "unexpected_status": 1}`

## 本批为何这样切

Batch 53 已证明 reporting service/model 能稳定生成失败类型计数。本批只补上 API 与 HTTP adapter 层的读取验证，确保该字段能穿过当前后端边界。

这仍属于 reporting 消费层增强，不回到回测内核继续添加生产摘要字段。

## 验证结果

已通过：

- `python scripts\smoke_test_formal_api.py`
- `python scripts\smoke_test_formal_http_adapter.py`
- `python scripts\smoke_test_formal_services.py`
- `python scripts\run_formal_verifications.py`
- `git diff --check -- scripts/smoke_test_formal_api.py scripts/smoke_test_formal_http_adapter.py`

## 下一步建议

1. `阶段 5：报告层（reporting）`：可继续选择一个最小消费增强点，例如 `failure_stage_counts`，但必须只消费既有字段，不新增 backtest-kernel 生产字段。
2. 也可以先文档化 reporting batch summary 字段边界，明确明细字段与聚合字段的关系。
