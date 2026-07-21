# 下一批真实开发执行记录（Batch 72）
时间：`2026-07-05`

## 本批目标

执行上一轮建议中的：

- `[阶段 7：最小本地量化服务闭环]` 开始逐项复核 `app/services` 的职责边界
- `[阶段 7：最小本地量化服务闭环]` 再针对 `app/api` 与 `http_adapter` 做一轮契约级收束

## 本批实际落地

### 1. 新增“阶段 7 服务职责与 API 契约边界”文档

- `docs/architecture/stage-7-service-and-api-boundaries.md`

本批把阶段 7 当前需要稳定保留的服务层与访问层，正式收束为：

- `market`
- `factors`
- `backtest`
- `reporting`
- `http_adapter`
- `run_formal_verifications.py`

### 2. 明确哪些服务属于阶段 7 必要闭环

本批正式写清：

- `MarketDataService`、`FactorResearchService`、`BacktestService`、`PersistentBacktestService`、`BatchResearchService`、`ReportingService` 都属于阶段 7 必要闭环
- 但它们各自仍应保持“最小编排 / 最小映射 / 最小持久化边界”，不继续外扩为更重的任务系统或产品能力层

### 3. 明确哪些 API 面当前不建议继续扩

本批正式写清：

- `market`、`factors`、`backtest`、`reporting` 当前已有入口已经足够覆盖阶段 7
- 当前不建议继续新增 reporting 列表、导出接口、AI 接口、异步任务接口或前端专用契约结构

## 本批为何这样切

阶段 7 目前已经有：

- 明确主线
- 更新后的开发计划
- 统一验证入口

在这个基础上，如果不先把“哪些职责必须保留、哪些访问面先止步”写清，后续很容易一边收束一边继续偷偷扩接口。

因此，本批优先补边界文档，而不是马上改代码实现。

## 验证结果

已完成验证：

- 读取并复核 `app/services/market_data_service.py`
- 读取并复核 `app/services/factor_research_service.py`
- 读取并复核 `app/services/backtest_service.py`
- 读取并复核 `app/services/persistent_backtest_service.py`
- 读取并复核 `app/services/batch_research_service.py`
- 读取并复核 `app/services/reporting_service.py`
- 读取并复核 `app/api/market.py`
- 读取并复核 `app/api/factor.py`
- 读取并复核 `app/api/backtest.py`
- 读取并复核 `app/api/reporting.py`
- 读取并复核 `app/runtime/http_adapter.py`
- `git diff --check -- docs/architecture/stage-7-service-and-api-boundaries.md docs/architecture/next-real-development-execution-batch-72.md`

说明：本批仅新增边界文档与批次记录，不涉及生产代码和 smoke 逻辑改动。

## 下一步建议

1. `[阶段 7：最小本地量化服务闭环]` 开始针对 `app/services` 做一轮小范围代码收束，优先识别哪些重复转换、重复默认值处理可以合并。
2. `[阶段 7：最小本地量化服务闭环]` 再决定是否需要为 `RouteDefinition` 和 `http_adapter` 增加更清晰的最小契约约束，但不扩大接口数量。
