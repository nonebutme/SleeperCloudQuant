# 下一批真实开发执行记录（Batch 42）

时间：`2026-07-03`

## 本批目标

按顺序继续推进 `阶段 4：回测内核（backtest-kernel）` 的两步工作：

- 为 batch request 增加 `run_id` 唯一性约束
- 为 batch 回测结果摘要补一条最小可读性增强

## 本批实际落地

### 1. 增加 batch run_id 唯一性约束

- `app/schemas/backtest.py`

在 `BatchBacktestRunRequestPayload.__post_init__` 中新增约束：

- `runs` 规范化后，`run_id` 必须唯一
- 若存在重复 `run_id`，抛出 `ValueError("batch run_id values must be unique")`

同时补齐验证：

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增断言：

- API 层重复 `run_id` 会显式失败
- HTTP handler 下重复 `run_id` 返回 `400`

### 2. 增强 batch 结果摘要可读性

- `domain/backtest/models.py`
- `app/services/batch_research_service.py`

本批为 `BatchBacktestRunSummary` 新增：

- `successful_run_ids`

并在 batch 执行摘要生成时填充成功完成的 run_id 列表。

这样调用方不用只靠 `success_count` 推测哪些 run 成功，直接就能拿到成功 run 的明细标识。

同步补齐验证：

- API smoke 断言 `successful_run_ids`
- HTTP smoke 断言 `successful_run_ids`

## 本批为何这样切

这一步继续遵守“先收入口规则，再做最小可读性增强”的节奏：

- 不改回测执行引擎
- 不改 reporting 层结构
- 只在 batch request payload 和 batch summary 这两个最靠近阶段 4 入口/出口的位置做最小增强

## 验证结果

已通过：

- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续补 batch request 的输入一致性规则，例如 runs 中 symbol / benchmark / strategy_name 的组合约束是否需要显式策略。
2. `阶段 4：回测内核（backtest-kernel）`：如果不想继续在入口规则上打磨，下一条可以转向 batch 摘要的业务可读性增强，比如补更清楚的 failure 归类信息。
3. `阶段 5：报告层（reporting）`：当前仍不建议切换过去。