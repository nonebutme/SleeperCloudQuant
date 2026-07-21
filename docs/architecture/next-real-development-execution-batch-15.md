# 下一批真实开发执行记录（Batch 15）

时间：`2026-07-01`

## 本批目标

沿着已落地的 factor 只读 API，补最小股票池查询接口：

- 指数成分股成员查询
- 对应 API / HTTP smoke 验证

## 本批实际落地

### 1. 扩展 factor 服务层只读能力

- `app/services/factor_research_service.py`

新增：

- `get_pool_members(...)`

### 2. 扩展 factor schema 与路由

- `app/schemas/factor.py`
- `app/api/factor.py`

新增：

- `FactorPoolMembersQuery`
- `FactorPoolMembersResponse`
- `GET /api/factors/pool-members`

### 3. 扩展 API / HTTP smoke

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

## 本批为何这样切

这一步仍然遵循保守策略：

- 只开放股票池读取
- 不开放股票池维护
- 不开放 factor 运行 API
- 先把研究层最小可读对象补齐

## 下一步建议

1. 若验证通过，下一小步可评估是否开放 factor 运行 API
2. 或继续保守，只补多因子摘要/组合查询只读接口
3. 再之后考虑股票池持久化定义
