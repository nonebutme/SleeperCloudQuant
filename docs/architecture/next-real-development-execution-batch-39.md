# 下一批真实开发执行记录（Batch 39）

时间：`2026-07-03`

## 本批目标

沿着 `阶段 4：回测内核（backtest-kernel）` 主线，继续把 backtest 入口的参数错误语义补齐到和 factor / market 一致：

- `POST /api/backtest/run-batch` 缺少必填字段时，HTTP handler 返回 400
- 若在 handler 内部发生嵌套 payload 构造失败，不再被 `dispatch_request` 误判为路由调用签名错误

## 本批实际落地

### 1. 补充 backtest run-batch 缺参的 HTTP handler smoke

- `scripts/smoke_test_formal_http_adapter.py`

新增最小验证：

- 通过 handler 路径发送 `POST /api/backtest/run-batch`
- request body 中 `runs` 项缺少必填字段
- 断言返回 `400`
- 断言响应消息为 `invalid request parameters`

### 2. 收紧 dispatch_request 的 TypeError 处理

- `app/runtime/http_adapter.py`

移除原先对 `TypeError` 的宽泛 fallback 调用，改为按当前 payload / path_params 状态直接选择 handler 调用方式。

这样可以避免：

- handler 内部真实抛出的 `TypeError` 被误判成“路由调用参数个数不匹配”
- 然后又错误地再次调用 `route.handler(*path_params.values())`

### 3. 收敛 backtest batch 嵌套 payload 构造失败

- `app/api/backtest.py`

在 `_to_run_request` 中把 `BatchBacktestRunItemPayload(**raw)` 的 `TypeError` / `ValueError` 翻译为：

- `DispatchError(400, "invalid request parameters")`

这样 `run-batch` 的嵌套 runs 项缺参，最终可以稳定落到 HTTP 400。

## 本批为何这样切

这一步虽然进入了生产修正，但仍然保持最小范围：

- 不改服务层
- 不改回测执行逻辑
- 只修正 HTTP 分派层和 backtest API 参数翻译层

本批的意义是把阶段 4 的入口错误语义先收紧，再继续往更深的回测能力推进。

## 验证结果

已通过：

- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/smoke_test_formal_api.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续补 `run-batch` / `run-once` 的更细参数边界验证，或开始挑一条最小生产能力增量推进，例如批量回测请求的显式输入约束收紧。
2. `阶段 5：报告层（reporting）`：暂时不建议切，除非你想提前做回测结果对外可读性增强。