# 下一批真实开发执行记录（Batch 21）

时间：`2026-07-02`

## 本批目标

沿着已落地的 factor 股票池横截面摘要查询，补齐两个只读边界验证：

- 返回 symbol 顺序稳定性
- 未知股票池输入的空结果约束

## 本批实际落地

### 1. 收紧 demo / fake 股票池夹具

- `app/runtime/demo_registry.py`
- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`

当前 fake 行为调整为：

- `000300.XSHG` 返回固定顺序的两只股票
- 未知 `index_code` 返回空列表

### 2. 扩展横截面摘要边界验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- 横截面摘要返回顺序与股票池成员顺序一致
- 未知股票池成员查询返回空列表
- 未知股票池横截面摘要返回空结果

## 本批为何这样切

这一步继续遵循保守策略：

- 不扩新接口
- 不改正式 service 结构
- 不改持久化层
- 先把横截面只读能力的顺序稳定性与空结果边界补成显式回归验证

## 下一步建议

1. 若验证继续稳定，可补未知 `trade_date` 的空结果约束验证
2. 或继续保守，补 cross-section-summary 在不同 `date` 参数下的股票池切换验证
3. 暂不进入前端与 AI 侧扩展
