# 下一批真实开发执行记录（Batch 41）

时间：`2026-07-03`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的最小业务规则收口：

- 不只验证 `run-batch` 输入格式是否合法
- 还补一条最小业务约束：`runs` 不能为空

## 本批实际落地

### 1. 新增 batch request 的最小业务规则

- `app/schemas/backtest.py`

在 `BatchBacktestRunRequestPayload.__post_init__` 中新增约束：

- 若 `runs` 规范化后为空，抛出 `ValueError("batch runs must not be empty")`

这样 batch request 的空列表不再落到服务层的 `empty` 状态，而是在请求入口被显式拒绝。

### 2. 同步补齐 API / HTTP 验证

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- API 层直接构造 `BatchBacktestRunRequestPayload(..., runs=[])` 时抛出 `ValueError`
- HTTP handler 下，`POST /api/backtest/run-batch` 传入空 `runs` 时返回 `400`
- 已有的无效 runs 项缺参验证继续保留

## 本批为何这样切

这一步符合上一批建议中的“从入口验证切到最小业务规则”：

- 不改回测执行逻辑
- 不改服务层编排
- 只把一个低风险、高收益的业务约束前移到 payload 层

这使得 `run-batch` 的输入约束从“结构合法”进一步推进到“最小业务上可接受”。

## 验证结果

已通过：

- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续补 batch request 的最小业务约束，例如 runs 中 `run_id` 的唯一性或更明确的输入一致性约束。
2. `阶段 4：回测内核（backtest-kernel）`：如果不想继续堆入口规则，下一条可以切到 batch 回测结果摘要的业务约束或结果可读性增强。
3. `阶段 5：报告层（reporting）`：当前仍不建议切换过去。