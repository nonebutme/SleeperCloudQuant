# 下一批真实开发执行记录（Batch 38）

时间：`2026-07-03`

## 本批目标

在 batch-34 ~ batch-37 已补齐 factor / market 相关 HTTP 400 显式 smoke 的基础上，把同一条参数错误语义平滑扩到 backtest 入口：

- POST JSON object 缺少必填字段时，backtest handler 返回 400
- 不改生产逻辑，只补显式回归验证

## 本批实际落地

### 1. 补充 backtest run-once 缺参的 HTTP handler smoke

- `scripts/smoke_test_formal_http_adapter.py`

新增最小验证：

- 通过 handler 路径发送 `POST /api/backtest/run-once`
- request body 缺少必填 `end_date`
- 断言返回 `400`
- 断言响应消息为 `invalid request parameters`

### 2. 阶段切换方式保持最小化

本批没有直接切入 backtest-kernel 的生产能力扩展，而是先在 backtest HTTP 入口补一条和前序 batch 一致的错误语义 smoke。

这样做的目的是：

- 让阶段切换更平滑
- 先确认 backtest API 壳层和既有参数错误策略一致
- 避免一上来同时进入新模块能力开发和错误语义变更

## 本批为何这样切

这一步仍然保持保守型、小步快跑：

- 不新增生产代码改动
- 只补最小 handler-level 验证
- 以回归验证的方式把工作重心从 factor / market 平滑过渡到 backtest 入口

## 验证结果

已通过：

- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：开始挑一条最小的 backtest-kernel 主线任务推进，例如补显式 batch/run-once 参数边界验证，或开始梳理下一条最小可实现的回测能力增量。
2. `阶段 3：因子分析（收尾）`：如果想先彻底收口只读入口验证，也可以再检查是否还有同类但未显式覆盖的 HTTP 400 分支，不过收益已经在下降。