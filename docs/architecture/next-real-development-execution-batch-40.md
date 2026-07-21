# 下一批真实开发执行记录（Batch 40）

时间：`2026-07-03`

## 本批目标

按既定顺序继续推进 `阶段 4：回测内核（backtest-kernel）`：

- 先补 `run-batch` 更细的输入边界验证
- 再把 batch payload 的标准化收口往前推进一小步

## 本批实际落地

### 1. 补充 backtest run-batch 的更细输入边界验证

- `scripts/smoke_test_formal_http_adapter.py`
- `scripts/smoke_test_formal_api.py`

新增与收紧的验证包括：

- HTTP handler 下，`POST /api/backtest/run-batch` 的嵌套 runs 项缺少必填字段时返回 `400`
- API smoke 下，`BatchBacktestRunRequestPayload` 会把 dict 形式的 runs 项规范为 `BatchBacktestRunItemPayload`
- API smoke 下，无效 runs 项会在 payload 构造阶段显式失败

### 2. 推进 batch payload 的显式标准化收口

- `app/schemas/backtest.py`
- `app/api/backtest.py`

本批把 `BatchBacktestRunRequestPayload` 的 `runs` 提前标准化：

- 若 runs 项已经是 `BatchBacktestRunItemPayload`，直接保留
- 若 runs 项是 dict，则在 `__post_init__` 中规范化为 `BatchBacktestRunItemPayload`
- 若 runs 项不是合法 dict / payload，则抛出 `ValueError("invalid batch run item")`

同时，`run_batch` 的 `_to_run_request` 现在直接消费标准化后的 `BatchBacktestRunItemPayload`，不再在更后面的路径里重复做 dict -> payload 构造。

### 3. 保持上一批 dispatch 修正有效

- `app/runtime/http_adapter.py`

上一批对 `dispatch_request` 的 TypeError 收紧继续生效，因此本批的 batch 嵌套输入错误不会再被误判成路由调用签名错误。

## 本批为何这样切

这一步符合“先验证后扩展、最小变更”的策略：

- 先补边界验证
- 再做最小生产收口
- 不进入服务层和回测执行内核深处

本批的价值在于：`run-batch` 的输入约束更早、更显式，阶段 4 的 backtest 入口开始从“能跑”走向“输入边界稳定”。

## 验证结果

已通过：

- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续把 `run-batch` 的输入约束补完整一格，例如约束 `runs` 不能为空或补显式错误语义验证。
2. `阶段 4：回测内核（backtest-kernel）`：如果想从入口验证切到能力推进，下一条更自然的是补 batch request 的最小业务约束，而不是继续堆 HTTP 壳层 smoke。
3. `阶段 5：报告层（reporting）`：当前还不建议切，除非你想提前增强回测结果的可读展示。