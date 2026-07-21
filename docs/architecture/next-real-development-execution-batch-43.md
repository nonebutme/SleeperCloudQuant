# 下一批真实开发执行记录（Batch 43）

时间：`2026-07-03`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的 batch request 输入一致性规则：

- 为 `run-batch` 增加一条更明确的业务一致性约束
- 先挑最稳妥的一条：同一 batch 内 `benchmark` 必须一致

## 本批实际落地

### 1. 增加 batch benchmark 一致性约束

- `app/schemas/backtest.py`

在 `BatchBacktestRunRequestPayload.__post_init__` 中新增规则：

- `runs` 规范化后，所有 `benchmark` 必须一致
- 若存在不一致的 `benchmark`，抛出 `ValueError("batch benchmark values must be consistent")`

### 2. 同步补齐 API / HTTP 验证

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- API 层构造 benchmark 不一致的 batch payload 时显式失败
- HTTP handler 下 benchmark 不一致的 batch 请求返回 `400`
- 既有的空 `runs`、重复 `run_id`、缺少必填字段验证继续保留

## 本批为何这样切

这一步继续遵守 `阶段 4` 当前的推进节奏：

- 先补低风险、可解释的输入一致性约束
- 不直接进入更深服务层和回测执行逻辑
- 选择 benchmark 而不是 strategy_name 作为首条一致性规则，是因为它更符合批量回测“同一基准下比较”的最小语义

## 验证结果

已通过：

- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：按上一轮建议的第二条，下一步可以从输入规则转向 batch 摘要的业务可读性增强，优先考虑 failure 信息的更清楚归类。
2. `阶段 4：回测内核（backtest-kernel）`：如果还想继续入口一致性规则，也可以再评估 strategy_name 是否需要一致性约束，但这一步比 benchmark 更有产品语义判断。
3. `阶段 5：报告层（reporting）`：当前仍不建议切换过去。