# 下一批真实开发执行记录（Batch 31）

时间：`2026-07-02`

## 本批目标

继续沿着 factor 只读查询补两类边界验证：

- `top-n` 在异常 `limit` 输入下的边界验证
- `summary / cross-section-summary / factor values` 在更多未知输入组合下的联动一致性验证

## 本批实际落地

### 1. 扩展 top-n limit 边界验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- `limit` 远大于结果行数时，返回全部可用结果
- `limit` 为负数时，当前实现按最小 1 条结果钳制
- 上述行为在 services / API / HTTP 三层一致

### 2. 扩展更多未知输入组合联动验证

新增验证：

- `summary` 在未知 `symbol` + 未知 `factor_id` 组合下返回空列表
- `cross-section-summary` 在未知 `factor_id` + 不同日期股票池组合下保留 `symbol` 集合但所有 `rows` 为空
- `factor values` 在未知 `symbol` + 未知 `factor_id` 组合下返回空列表
- 上述行为在 services / API / HTTP 三层一致

## 本批为何这样切

这一步继续保持最小变更原则：

- 不扩新接口
- 不改 service / API 逻辑
- 仅把异常 limit 处理和未知输入组合语义补成显式回归验证

## 下一步建议

1. 若继续保守推进，可补 `top-n` 在非数字 `limit` 输入下的失败语义或适配策略验证
2. 或补 `summary / factor values / top-n` 在更多 scope 错配组合下的联动一致性验证
3. 暂不进入前端与 AI 侧扩展
