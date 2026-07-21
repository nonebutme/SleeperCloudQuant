# 下一批真实开发执行记录（Batch 33）

时间：`2026-07-02`

## 本批目标

继续沿着 factor 查询边界补两类验证：

- HTTP handler 对非 `DispatchError` 异常的当前真实行为
- factor 查询接口在参数校验层的显式错误语义验证

## 本批实际落地

### 1. 扩展 HTTP handler 异常策略验证

- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- `DispatchError` 会被 handler 转换为 HTTP 响应
- 非 `DispatchError` 异常（如 `ValueError`）会继续向外冒泡
- 对于继续冒泡的异常，handler 当前不会写出 HTTP 响应体

### 2. 扩展参数校验层错误语义验证

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- `top-n` 的非数字 `limit` 维持 `ValueError` 语义
- 缺少必填查询参数的 HTTP factor summary 请求维持 `TypeError` 语义
- 当前这批验证只记录现状，不改统一错误处理策略

## 本批为何这样切

这一步继续保持最小变更原则：

- 不扩新接口
- 不改 handler 与参数校验逻辑
- 仅把当前真实异常语义补成显式回归验证，方便后续若要统一错误处理时有清晰基线

## 下一步建议

1. 若继续保守推进，可开始把 factor 查询接口的错误语义统一成显式 HTTP/DispatchError 约束
2. 或继续先补更多异常输入组合的现状验证，再决定是否收敛错误处理策略
3. 暂不进入前端与 AI 侧扩展
