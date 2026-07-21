# 下一批真实开发执行记录（Batch 17）

时间：`2026-07-01`

## 本批目标

沿着已落地的 factor 只读 API，补最小股票池横截面多因子摘要查询：

- 给定 `index_code + date + trade_date`
- 返回池内多只股票在指定交易日的多因子摘要
- 对应 services / API / HTTP smoke 验证

## 本批实际落地

### 1. 扩展 factor 服务层只读能力

- `app/services/factor_research_service.py`

新增：

- `get_pool_factor_summary(...)`

当前实现保持最小化：

- 先读取股票池成员
- 逐只股票复用既有 `get_factor_summary(...)`
- 不新增 SQLite 表结构
- 不引入新的批量计算入口

### 2. 扩展 factor schema 与路由

- `app/schemas/factor.py`
- `app/api/factor.py`

新增：

- `FactorCrossSectionSummaryQuery`
- `FactorCrossSectionSummaryItem`
- `FactorCrossSectionSummaryResponse`
- `GET /api/factors/cross-section-summary`

### 3. 扩展验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- 服务层股票池横截面多因子摘要读取
- API 股票池横截面多因子摘要查询
- HTTP adapter 股票池横截面多因子摘要调度

## 本批为何这样切

这一步继续遵循保守策略：

- 只补读取
- 不补执行入口
- 不改持久化结构
- 先把“股票池内多标的在同一交易日如何并排查看”补齐

## 下一步建议

1. 若验证继续稳定，可补横截面摘要的 `factor_ids` 过滤用例
2. 或继续保守，补更明确的研究报表只读聚合
3. 暂不进入前端与 AI 侧扩展
