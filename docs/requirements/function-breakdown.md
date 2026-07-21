# 功能拆解

## 目标

- `已确认` 将最初需求拆成可实现、可展示、可验证的功能模块。
- `已确认` 每个功能点必须能追踪到后端服务/API、Web 展示区域和验证方式。
- `已确认` 五仓库重构成果必须体现在模块边界和溯源页面中。

## 功能点

| 功能域 | MVP 功能 | 后端落点 | Web 展示 | 验证方式 |
| --- | --- | --- | --- | --- |
| 数据中心 | 行情、日历、同步状态、数据源状态 | `data_platform`, `MarketDataService`, `app/api/market.py` | 数据中心、Dashboard | API smoke + Web 探针 |
| 因子分析 | 因子定义、股票池、快照、截面、Top N | `factor_lab`, `FactorResearchService`, `app/api/factor.py` | 因子分析页 | factor smoke + API smoke |
| 策略回测 | 单次回测、批量回测、指标摘要 | `backtest_kernel`, `BacktestService`, `BatchResearchService`, `app/api/backtest.py` | 策略回测页 | service/API/http smoke |
| 报告中心 | Run Detail、Batch Summary、历史结果 | `reporting`, `ReportingService`, `app/api/reporting.py` | 报告中心 | reporting verification |
| AI 分析 | 单股分析任务、结构化报告、风险提示 | `AIAnalysisService`, `app/api/ai.py` | AI 分析页 | AI API smoke |
| 配置中心 | 数据源、模型、回测默认参数、模板状态 | `config_center`, `ConfigCenterService`, `app/api/config.py` | 配置中心 | config API smoke |
| 重构溯源 | 五仓库来源矩阵、采纳边界、模块映射 | 文档与静态元数据 | 溯源页 | 文档检查 + Web 展示 |

## 优先级

1. P0：需求基线、五仓库映射、Dashboard、数据中心、因子分析、策略回测、报告中心。
2. P1：AI 分析、配置中心、重构溯源页。
3. P2：更丰富图表、真实数据接入、真实 LLM 接入、真实 rqalpha 运行时。

## 依赖关系

- 数据中心是因子分析、回测和 AI 分析的数据基础。
- 因子分析依赖本地行情和股票池读取。
- 策略回测依赖行情、配置和回测网关。
- 报告中心依赖回测与 AI 分析产物。
- Web MVP 依赖稳定 API 契约。
- 重构溯源依赖五仓库比较与复用整合方案。

## 待确认事项

- `待确认` 数据获取与更新方式从 demo/mock 切换到真实 provider 的时机。
- `待确认` 回测、研究、展示三类能力是否在 MVP 审批后进入真实运行时增强。
- `待确认` AI 分析报告是否需要引入人工审核状态。

## 阶段 60 后确认的回测模式

1. `已确认` 独立选股回测：一个策略对所选范围内股票逐只并发运行，每只股票使用独立虚拟资金；仅发生有效买入成交的标的进入绩效汇总，同时披露完整筛选漏斗和失败原因。
2. `已确认` 共享资金池组合回测：一个账户共享现金并持有多只股票，按统一交易日推进信号、权重、成交、持仓和净值，最终以组合整体评价策略。
3. `已确认` 两种模式共用版本化策略契约，并绑定策略版本、源码 hash、参数、股票池快照和数据版本。
4. `已确认` 实施顺序为版本化策略真实执行、独立选股并发、共享资金池组合撮合、双模式报告分析。