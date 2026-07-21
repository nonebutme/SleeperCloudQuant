# 下一批真实开发执行记录（Batch 19）

时间：`2026-07-02`

## 本批目标

沿着已落地的 factor 只读摘要查询，补齐未知 `factor_id` 的空结果约束验证：

- 单标的多因子摘要未知因子过滤
- 股票池横截面多因子摘要未知因子过滤
- 对应 services / API / HTTP smoke 验证

## 本批实际落地

### 1. 扩展未知因子空结果验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- `factor_ids=unknown_factor` 时单标的摘要返回空列表
- `factor_ids=unknown_factor` 时横截面摘要仍保留股票池成员，但每只股票的 `rows` 为空列表

## 本批为何这样切

这一步继续遵循保守策略：

- 不扩新接口
- 不改 service 结构
- 不改持久化层
- 先把已有只读能力的边界行为补成显式回归验证

## 下一步建议

1. 若验证继续稳定，可补 `factor_ids` 为空字符串与多逗号输入的解析约束验证
2. 或继续保守，补横截面摘要按 symbol 稳定顺序的显式验证
3. 暂不进入前端与 AI 侧扩展
