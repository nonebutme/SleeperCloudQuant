# 下一批真实开发执行记录（Batch 34）

时间：`2026-07-03`

## 本批目标

将 factor 查询参数校验错误统一收敛到显式错误通道：

- API 层参数错误抛出 `DispatchError`
- HTTP handler 将 `DispatchError` 转换为 HTTP 400 响应
- 保持未知 factor 查询的既有空结果语义，不下探修改 registry 或服务层业务逻辑

## 本批实际落地

### 1. 收敛 request model 构造错误

- `app/runtime/http_adapter.py`

`_build_route_payload` 在 GET / POST 的 `request_model(**raw_query/raw_body)` 外层补充最小异常翻译：

- `TypeError` / `ValueError` -> `DispatchError(400, "invalid request parameters")`
- POST body 非合法 JSON -> `DispatchError(400, "request body must be valid JSON")`

HTTP handler 仍只捕获 `DispatchError`，非 `DispatchError` 异常继续保持向外冒泡的既有策略。

### 2. 收敛 top-n limit 参数错误

- `app/api/factor.py`

新增 `_parse_top_n_limit`：

- `None` / 空字符串继续回退到默认 `10`
- 非数字 limit 转换为 `DispatchError(400, "limit must be an integer")`

本批未修改 factor registry，避免影响 unknown factor -> 空结果的既有只读查询语义。

### 3. 更新最小验证闭环

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

验证从 batch-33 的“现状异常语义”切换为本批统一错误语义：

- API route 直接调用下，非数字 `limit` 抛出 `DispatchError(400, "limit must be an integer")`
- HTTP handler 下，缺少必填 query 字段返回 400 + `invalid request parameters`
- HTTP handler 下，非数字 `limit` 返回 400 + `limit must be an integer`
- 非 `DispatchError` 仍会继续冒泡，避免扩大 handler 捕获范围

## 本批为何这样切

本批只收敛参数校验层，不扩到服务层或 factor registry：

- 参数格式错误属于请求入口语义，适合在 API / HTTP 适配层统一转为 400
- unknown factor 在当前只读查询中已有大量空结果验证，贸然改为错误会扩大行为变更面
- handler 的异常策略保持保守，只处理显式 `DispatchError`，避免吞掉真实代码缺陷

## 验证结果

已通过：

- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮命令在默认 sandbox helper 下无法创建进程，实际验证使用沙箱外执行；失败点属于工具链 helper 创建层，不是项目代码运行失败。

## 下一步建议

1. 继续保持只读查询边界的小步验证，可补 POST body 非合法 JSON 的 HTTP handler smoke。
2. 若未来要改变 unknown factor 语义，应先单独列批评估 registry / service / API 三层影响，不与参数格式错误收敛混做。
3. 暂不进入前端、AI 大系统或远程数据服务扩展。