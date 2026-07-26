# 数据结构

## 总体分层

当前数据模型分为五层：市场主数据与行情事实、策略定义与不可变版本、回测任务与执行状态、Run 结果与事实证据、分析报告与研究工作流。各层通过稳定 ID 关联，不以页面状态替代持久化实体。

## 市场数据实体

规范库：`var/market/a_share_market.sqlite3`

- `market_symbols`：证券代码、名称、市场、上市状态和来源。
- `market_daily_prices`：证券、交易日、复权类型、OHLCV、成交额、换手率和来源。
- `market_sync_runs`：同步操作、范围、状态、写入量、错误和时间。
- `market_sync_state`：同步断点和全局状态。

分类库：`var/runtime/a_share_classification_history.sqlite3`

- `classification_intervals`：证券、分类维度、分类值、生效区间和证据。
- `classification_sync_state`：按证券记录同步状态、重试次数和错误。

核心约束：

- 行情事实按 `symbol + trade_date + adjustment` 唯一定位。
- 历史分类必须按回测时点 as-of 匹配，不用当前分类回填历史。
- 数据版本、新鲜度和质量状态必须进入回测输入快照与报告证据。

## 策略实体

策略库：`var/runtime/strategy_library.sqlite3`

- `strategy_definitions`：策略 ID、名称、分类、说明、当前版本和归档状态。
- `strategy_versions`：版本号、源码、SHA-256、参数、参数 Schema、校验状态和契约版本。
- `strategy_migrations`：策略库迁移审计。

核心约束：

- 已保存版本不可原地修改。
- 回测必须绑定明确版本、源码 hash 和参数快照。
- 自定义策略当前使用 `target-weights-v1` 契约。

## 回测任务实体

- `single_backtest_tasks`：单股任务、状态、配置、Run、结果、错误与软删除信息。
- `screening_tasks`：独立账户批量回测任务、冻结配置、股票数、摘要、生命周期与软删除信息。
- `screening_items`：每只股票的独立执行状态、是否建仓、Run、指标和错误。
- `portfolio_tasks`：投资组合回测任务、冻结股票池、组合 Run、进度、摘要和生命周期。

状态基线：

- 通用：`pending/ready -> running -> completed/failed`。
- 可控长任务可扩展：`pause_requested/paused/resume/cancel_requested/cancelled`。
- 删除使用 `deleted_at/deleted_reason`，任务编号不复用。

账户语义：

- 单品种测试：一个标的、一个独立账户。
- 独立账户批量回测：N 个互不共享资金的独立账户，只对实际建仓样本计算绩效，同时保留完整筛选漏斗。
- 投资组合回测：一个账户、共享现金、多股票持仓，组合结果不得由独立 Run 拼接。

## Run 事实与证据实体

Web Demo 运行结果库：`tmp/formal_http_demo.sqlite3`

- `backtest_runs`：Run 主记录、策略绑定、标的范围、期间、参数、状态和错误。
- `backtest_metrics`：指标名和值。
- `backtest_trades`：成交时间、证券、方向、价格、数量和金额。
- `backtest_positions`：持仓快照。
- `backtest_accounts`：账户资产、现金和单位净值快照。
- `backtest_yearly_returns`：年度组合、基准和超额收益。
- `backtest_logs`：阶段化运行日志。
- `backtest_input_snapshots`：数据集、证券、数据版本和资产键绑定。
- `local_data_assets`：本地资产版本、质量、覆盖和同步时间。

结果层只记录事实、指标和证据，不直接把分析结论写回交易事实表。

## 报告与研究实体

- `report_snapshots`：Run 报告类型、版本、标题和不可变快照。
- `report_packages`：报告包、Run/工作流/快照绑定、生命周期和导出信息。
- `ai_workflow_runs`：AI 分析任务、Provider 模式、报告 ID、状态与 payload。
- `research_runs`、实验索引 JSON：参数研究、对比和实验目录。

分析报告必须声明评价对象与回测模式、报告/公式版本、数据版本与样本范围、证据质量、缺失证据和解释边界。

## 阶段 77 数据契约要求

- “查看结果”优先读取任务/Run 事实、指标、净值、交易、持仓、账户、日志和数据版本。
- “查看分析”按需读取模式化报告，不应为打开分析而强制预加载全部结果明细。
- 独立账户批量回测结果默认先展示任务级漏斗和分布，任务内单股 Run 由用户主动选择。
- 两个入口可复用任务上下文与查看器容器，但必须拥有独立加载状态、失败状态和验收标准。
