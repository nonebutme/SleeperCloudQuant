# 下一批真实开发执行记录（Batch 48）
时间：`2026-07-03`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的最小收口，在既有 batch failures 摘要增强与 batch 输入一致性约束基础上，再完成两项小步增强：

- 为 `unexpected_status` 类型 failure 增加显式 `result_status`
- 为 `run-batch` 输入补齐 `start_date` 一致性约束

## 本批实际落地

### 1. 为 `unexpected_status` 增加 `result_status`

- `app/services/batch_research_service.py`

本批继续只在 batch failures 摘要层做最小增强：

- 当单次回测返回非 `completed` 状态时，除了既有 `failure_type` / `failure_stage` / `failure_code` / `failure_source` 外，再补充：
  - `result_status = result.status.value`

这样调用方在不解析 `error_message` 文本的情况下，也能直接读取真实返回状态值。

### 2. 为 run-batch 增加 `start_date` 一致性约束

- `app/schemas/backtest.py`

本批在已收口的 `benchmark`、`strategy_name`、`frequency`、`initial_cash` 之后，再补一项更保守的时间窗约束：

- 当同一批 `runs` 中存在不同 `start_date` 时，抛出 `ValueError("batch start_date values must be consistent")`

本轮只先收口 `start_date`，不同时扩到整组日期窗口，是为了继续保持小步快跑、逐项验证的节奏。

### 3. 补齐最小 smoke 验证闭环

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

本批补齐两类验证：

- services / reporting 链路中 `unexpected_status.result_status` 的透传验证
- API / HTTP 层对 `start_date` 不一致输入的拒绝验证

## 本批为何这样切

这一步仍然符合 `阶段 4：回测内核（backtest-kernel）` 的保守推进方式：

- 没有改动领域模型
- 没有扩展 reporting 对外协议
- 没有把输入规则下沉到更深服务层

选择 `result_status` 与 `start_date`，是因为两者都满足：

- 影响面小
- 语义直接且已存在于当前返回对象中
- 可以复用现有 smoke 与 formal verifications 验证闭环

## 验证结果

已通过：
- `python scripts/smoke_test_formal_services.py`
- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

另已通过：
- `git diff --check -- app/services/batch_research_service.py app/schemas/backtest.py scripts/smoke_test_formal_services.py scripts/smoke_test_formal_api.py scripts/smoke_test_formal_http_adapter.py`

说明：当前线程内 `apply_patch`、`rg` 与默认 sandbox helper 仍不稳定；本批编辑、检索与验证继续通过提权后的 PowerShell / 命令执行完成。该问题属于工具链环境问题，不是项目代码失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续评估 `unexpected_status` 是否还需要一项最小补充字段，但应优先复用现有返回数据，不新增额外业务层判断。
2. `阶段 4：回测内核（backtest-kernel）`：继续筛查 batch payload 中是否还存在一个语义很明确、适合继续在 payload 层收口的一致性字段，例如 `end_date`。
3. `阶段 5：报告层（reporting）`：暂不建议前移，等 `阶段 4` 的 failures 摘要语义与 batch 输入约束再稳定一轮后再评估。
