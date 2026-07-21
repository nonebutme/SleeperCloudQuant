# 下一批真实开发执行记录（Batch 37）

时间：`2026-07-03`

## 本批目标

在 batch-34 ~ batch-36 已补齐多条 POST body 400 显式 smoke 的基础上，再补一条 request model 构造失败的 POST handler 回归验证：

- POST body 是 JSON object，但缺少必填字段时，HTTP handler 返回 400
- 不改生产逻辑，只补显式回归验证

## 本批实际落地

### 1. 补充 missing required POST field 的 HTTP handler smoke

- `scripts/smoke_test_formal_http_adapter.py`

新增最小验证：

- 通过 handler 路径发送 `POST /api/market/sync-trading-calendar`
- request body 只提供 `start_date`，缺少必填 `end_date`
- 断言返回 `400`
- 断言响应消息为 `invalid request parameters`

### 2. 修正测试目标路由选择

本批一开始先尝试把 smoke 放在 `sync-price-history` 上，实际验证后确认该路由只有 `symbol` 是必填，不适合作为“缺少必填 POST 字段”的稳定用例。

因此测试最终切到 `sync-trading-calendar`，和 schema 的真实必填约束保持一致。

## 本批为何这样切

这一步继续保持保守型、小步快跑：

- 不新增生产代码改动
- 不扩到更多 POST 接口
- 只把 POST request model 构造失败 -> `invalid request parameters` 的 HTTP 400 分支补成显式 smoke

## 验证结果

已通过：

- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. 如果继续沿着这条线补齐，可考虑结束 factor / HTTP 错误语义这组只读 smoke 收口，避免同类验证继续细碎扩张。
2. 下一主线更适合切到 `backtest-kernel` 的最小能力推进。