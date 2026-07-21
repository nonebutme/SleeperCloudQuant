# 下一批真实开发执行记录（Batch 35）

时间：`2026-07-03`

## 本批目标

在 batch-34 已完成参数错误统一收敛的基础上，补齐一个更贴近真实 HTTP 入口的最小回归验证：

- POST request body 非合法 JSON 时，HTTP handler 返回 400
- 不扩生产逻辑，不改服务层，不改 registry

## 本批实际落地

### 1. 补充非法 JSON body 的 HTTP handler smoke

- `scripts/smoke_test_formal_http_adapter.py`

新增最小验证：

- 通过 handler 路径发送 `POST /api/market/sync-price-history`
- request body 使用非法 JSON：`b"{"`
- 断言返回 `400`
- 断言响应消息为 `request body must be valid JSON`

### 2. 修正测试入口语义

本批先尝试直接对 `dispatch_request(...)` 断言 400，实际验证发现这一路径会抛出 `DispatchError`，不会直接产出 HTTP 响应。

因此测试改为走 handler 路径，和 batch-34 目标中的“HTTP 400 响应语义”保持一致。

## 本批为何这样切

这一步继续保持保守型、小步快跑：

- 不新增生产代码改动
- 不放大验证范围到更多 POST 接口
- 只把 batch-34 已落地但尚未单独显式覆盖的一条错误分支补成稳定 smoke

## 验证结果

已通过：

- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. 若继续沿着最小闭环推进，可补 POST body 为非 JSON object 时的 400 smoke。
2. 当前 `dispatch_request` 与 `create_http_handler` 的错误语义边界已经更清晰，后续若扩展验证，应继续区分“dispatch 层异常”与“HTTP handler 响应”。
3. 暂不进入更深服务层错误语义收敛。