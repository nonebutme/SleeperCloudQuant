# 下一批真实开发执行记录（Batch 29）

时间：`2026-07-02`

## 本批目标

继续沿着 factor 只读查询补两类默认参数边界验证：

- `top-n` 查询在默认 / 空参数解析下的边界一致性验证
- `factor values` 在默认日期参数下的显式空结果验证

## 本批实际落地

### 1. 扩展 top-n 默认 / 空参数解析验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- service 层 `get_factor_top_n(...)` 使用默认 `limit=10`、`descending=True` 时返回当前默认降序结果
- API 层 `FactorTopNQuery` 省略 `limit/descending` 时返回默认降序结果
- API / HTTP 层传入空字符串 `limit=""`、`descending=""` 时仍回落到默认解析语义

### 2. 扩展 factor values 默认日期参数验证

新增验证：

- `factor values` 在省略 `start_date/end_date` 时，由于当前存储按精确作用域匹配，返回空列表
- 未知 `symbol` 在省略 `start_date/end_date` 时同样返回空列表
- 上述行为在 services / API / HTTP 三层一致

## 本批为何这样切

这一步仍然保持最小变更原则：

- 不扩新接口
- 不改查询与解析逻辑
- 仅把默认参数与空参数解析语义补成显式回归验证，避免后续适配时发生隐式行为漂移

## 下一步建议

1. 若继续保守推进，可补 `top-n` 在更多 `descending` 字符串输入（如 `0/no/false`）下的解析一致性验证
2. 或补 `factor values / summary / top-n` 在更多默认 scope 组合下的联动一致性验证
3. 暂不进入前端与 AI 侧扩展
