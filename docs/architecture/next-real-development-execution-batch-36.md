# 下一批真实开发执行记录（Batch 36）

时间：`2026-07-03`

## 本批目标

在 batch-35 已补齐 POST 非法 JSON body 的 HTTP 400 显式 smoke 基础上，再收紧一格 POST body 边界验证：

- JSON 合法但不是 object 时，HTTP handler 返回 400
- 不改生产逻辑，只补显式回归验证

## 本批实际落地

### 1. 补充 non-object JSON body 的 HTTP handler smoke

- `scripts/smoke_test_formal_http_adapter.py`

新增最小验证：

- 通过 handler 路径发送 `POST /api/market/sync-price-history`
- request body 使用合法 JSON 数组：`["not-an-object"]`
- 断言返回 `400`
- 断言响应消息为 `request body must be a JSON object`

## 本批为何这样切

这一步继续保持保守型、小步快跑：

- 不新增生产代码改动
- 不扩到更多 POST 接口
- 只把 `_build_route_payload` 已经存在的一条 400 分支补成显式 HTTP smoke

## 验证结果

已通过：

- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. 如果继续沿着 factor / HTTP 错误语义收口，可评估是否需要为更多 POST 接口抽一个共享的 handler-level 错误 smoke 帮助函数，但当前还不必抽象。
2. 如果准备切阶段，下一主线更适合从 factor 查询边界收尾转向 backtest-kernel 能力推进，而不是继续堆同类只读 smoke。