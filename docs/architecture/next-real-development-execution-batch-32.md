# 下一批真实开发执行记录（Batch 32）

时间：`2026-07-02`

## 本批目标

继续沿着 factor 只读查询补两类边界验证：

- `top-n` 在非数字 `limit` 输入下的失败语义验证
- `summary / factor values / top-n` 在更多默认 scope 与未知输入组合下的联动一致性验证

## 本批实际落地

### 1. 扩展 top-n 非数字 limit 验证

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- API 路由处理 `limit="abc"` 时，当前实现抛出 `ValueError`
- HTTP adapter 直调 `dispatch_request(...)` 时，非数字 `limit` 也沿当前实现抛出 `ValueError`
- 这一步只记录当前真实行为，不修改错误处理策略

### 2. 扩展默认 scope 与未知输入组合验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- `summary` 在默认 scope + 未知 `factor_id` 下返回空列表
- `factor values` 在默认 scope + 未知 `factor_id` 下返回空列表
- `top-n` 在默认 scope + 未知 `factor_id` 下返回空排行
- 上述行为在 services / API / HTTP 三层保持一致

## 本批为何这样切

这一步继续保持最小变更原则：

- 不扩新接口
- 不改异常处理逻辑
- 仅把当前真实失败语义与更多默认 scope 组合语义补成显式回归验证

## 下一步建议

1. 若继续保守推进，可补 HTTP handler 真实捕获非 `DispatchError` 异常时的行为策略
2. 或补 factor 查询接口在参数校验层的显式错误语义统一
3. 暂不进入前端与 AI 侧扩展
