# 下一批真实开发执行记录（Batch 14）

时间：`2026-07-01`

## 本批目标

沿着已落地的 `factor_lab` 注册表与统一运行入口，补最小只读 API：

- 因子定义列表查询
- 单标的因子值查询
- 因子 TopN 排序查询

## 本批实际落地

### 1. 新增 factor 只读 API 路由

- `app/api/factor.py`
- `app/api/__init__.py`
- `app/main.py`

新增路由：

- `GET /api/factors/definitions`
- `GET /api/factors/values`
- `GET /api/factors/top-n`

当前保持只读，不开放运行入口。

### 2. 新增 factor API schema

- `app/schemas/factor.py`

补齐最小查询/响应模型：

- `FactorValuesQuery`
- `FactorValuesResponse`
- `FactorTopNQuery`
- `FactorTopNResponse`
- `FactorDefinitionsResponse`

### 3. 扩展应用与 demo 装配

- `app/runtime/demo_registry.py`

在 demo 运行时先预计算并落盘两类因子结果：

- `close_to_close_return_1d`
- `close_to_ma2_bias`

这样 HTTP adapter smoke 可以走真实的只读查询链路，而不是伪造响应。

### 4. 扩展 API / HTTP smoke

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- 因子定义列表路由
- 因子值查询路由
- 因子 TopN 查询路由

## 本批为何这样切

这一步仍然遵循保守策略：

- 只开放只读 API
- 不开放因子运行 API
- 不开放批量运行入口
- 先把“已落盘的数据怎么稳定读出来”这一层补齐

这样可以先验证 Web/API 壳层对 `factor_lab` 的最小承接能力，再决定是否暴露执行能力。

## 已验证项

- `待执行` `python scripts/smoke_test_formal_api.py`
- `待执行` `python scripts/smoke_test_formal_http_adapter.py`
- `待执行` `python scripts/run_formal_verifications.py`
- `待执行` `python scripts/smoke_test_formal_services.py`

## 未验证项

- 尚未提供因子运行 API
- 尚未提供股票池 API
- 尚未支持多因子组合查询

## 阻塞原因

- 无代码级阻塞；仅待本轮 smoke 实跑确认

## 潜在风险

- 当前 factor TopN 的 `limit` 与 `descending` 仍通过字符串 query 参数转换，后续若引入正式 Web 框架模型绑定，可进一步收敛
- 当前 demo 预计算逻辑在运行时装配阶段执行，后续若数据量增大，需要考虑更明确的 demo seed 方式

## 下一步建议

1. 若验证通过，下一小步优先评估是否补 factor 运行 API
2. 或继续保守，只补股票池查询/枚举 API
3. 再之后考虑多因子组合查询或摘要接口
