# 数据结构

## R2 指标模型（2026-09-14）

指标旁库保存 `indicator_definitions`（公式来源）、`indicator_configs`（固定参数/复权/定义哈希）、`indicator_cache`（当前实际输入哈希及结果）、`indicator_factor_links`（指标—因子关系）、`indicator_factor_approvals`（精确制品哈希和选用依据）。策略数据目录增加 `indicator_values`；不复制规范行情，不新增人工版本发布。完整边界见 [R2 契约](r2-indicator-library.md)。

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

## 阶段 78.0 数据治理扩展（已审批并由 78.1 落地）

- 规范事实层拟新增交易日历、证券生命周期、日交易状态、公司行动、复权因子和指数日线六类数据集。
- 治理层拟新增不可变数据版本、版本成员和质量报告；只有 `published` 版本可供新回测绑定。
- 新回测必须在输入快照中固化统一数据版本；无法还原的历史 Run 保留 `legacy_unverifiable`，不伪造版本。
- 首轮迁移只增不改，不删除、重命名或改变现有 `market_daily_prices` 契约。
- 完整逻辑契约、数据源能力矩阵、调度和回退方案见 `docs/architecture/stage-78-0-data-governance-architecture-freeze.md`。
## 阶段 78.1 实现状态

- 六类规范事实表与版本、成员、质量报告治理表已增量创建，既有 `market_daily_prices` 契约未改变。
- 首个正式发布版本为 `scq-20260724-2135cd2b85852362`，截止交易日 `2026-07-24`。
- 新回测在创建或执行前解析并冻结 `published` 版本；无正式版本时明确进入 `data_not_ready`。
- 沪深 300 基准由 `market_index_daily_prices` 正式读取。
- 实施范围、数量、验证和边界见 `docs/architecture/stage-78-1-governance-skeleton-sample-integration.md`。
## 阶段 78.2 调度状态模型

- `market_incremental_sync_jobs`：规范增量任务、目标交易日、汇总进度、质量报告与发布版本。
- `market_incremental_sync_items`：按标的和复权口径持久化断点、尝试次数、退避、错误与隔离状态。
- `market_scheduler_settings`：应用内调度启用状态、时区、盘后时间、限频、并发、重试及最近调度信息。
- 调度顺序固定为目录、交易日历、目标日、沪深300、价格工作项、质量门禁、原子发布。
- 新版本重算行情、交易日历和指数成员摘要；未全市场刷新的上下文成员沿用上一正式版本并保留来源。
- 实现和运行边界见 `docs/architecture/stage-78-2-incremental-sync-scheduler.md`。

## M4 市场全景数据模型（P0—P3）

独立全景库：`var/runtime/market_panorama.sqlite3`

- `panorama_board_catalog`：行业/概念板块代码、名称、来源和观察时间。
- `panorama_board_daily`：板块日线、涨跌幅、成交量额及来源。
- `panorama_board_fund_flow`：行业/概念历史资金流分解。
- `panorama_events`：按交易日与证券保存公告、新闻、原文链接和证据。
- `panorama_sync_jobs`、`panorama_sync_items`：数据集级任务与板块/证券级工作项、进度、错误和重试状态。

全景查询不要求五个分区使用同一物理表，但必须逐分区声明请求日、有效日、状态和来源。行业本地回退按 `qfq` 横截面与 point-in-time 分类区间连接；分类标准证据保留，不静默混为单一标准。

## 阶段 87 因子研究数据模型

独立运行库：var/runtime/factor_research.sqlite3

- factor_definitions：factor_id + factor_version 唯一的元数据和定义哈希。
- factor_research_tasks：任务状态、配置、冻结上下文、版本、进度和结构化错误。
- factor_research_snapshots：股票池等不可变证据快照及内容哈希。
- factor_research_observations：交易日、标的、原始/处理/方向值、未来收益、点时行业和分组。
- factor_research_reports：每任务唯一的不可变报告载荷、context_hash 和 payload_hash。
- factor_index_component_intervals：指数、标的、valid_from/valid_to、来源、来源版本和证据。

研究身份由因子版本、数据版本、请求/有效区间、股票池快照、复权、前瞻周期、预处理、分组、调仓与成本假设共同组成，并计算 canonical SHA-256。

## 阶段 91 数据源与修复治理模型

- `data_source_probes`：能力级探测、结构化错误、延迟、样本量、可重试性与零写入证据。
- `market_incremental_sync_jobs.effective_config_json/actual_config_json`：创建时冻结策略与执行时实际策略。
- `data_quality_issues.issue_category/workflow_status/block_release`：问题分类、闭环状态与发布门禁。
- `data_quality_remediations`：重拉、历史补齐、纠错覆盖到版本与复检的统一工单。
- `data_correction_overlays.status/data_version_id`：保留原始事实的覆盖层发布状态与不可变版本归属。

## 拂经 v2 V7 点时证券状态候选模型

- `security_master_intervals`：按证券保存 `valid_from/valid_to`、`listing_status`、显式 `risk_warning`、`available_at`、来源观察时间、载荷哈希和证据。
- `is_active=1` 表示最新候选快照；无版本诊断读取只看活动行。较旧快照保留为非活动证据，显式版本回放可按冻结的快照引用读取旧行。
- `security_master_intervals.evidence_json.job_id` 是快照引用；区间身份包含该引用，保证同一快照幂等、不同快照并存。
- `data_version_members` 中 `dataset=security_master_intervals` 的成员通过 `details_json.snapshot_refs`（并兼容 `sync_run_ref`）冻结一个或多个快照；只有 `published/superseded` 且成员质量为 `passed` 的版本可回放。
- Baostock 日频 `isST` 仅作为沪深历史风险警示候选事实；历史名称不由当前名称倒推。
- 策略 resolver 通过 `fetch_symbol_history(..., data_version_id=...)` 按有效期和冻结快照读取；严格 `as_of_trade_date` 契约缺版本、缺成员、缺失、重叠、未来可得或风险警示值不明确时失败关闭。
- 正式数据版本仍须通过全市场覆盖门禁；北交所历史风险警示事实未接入前，不得把沪深覆盖表述为点时全 A 股 ready。

## 阶段 2 交易状态修正版消费账本

- `trading_status_remediation_release_bindings`：追加式保存每个交易状态修复运行被哪个独立修正版消费，并绑定 change-set、质量报告、checkpoint、候选清单、写入键、候选指纹和物理行内容哈希。
- `run_id` 全局唯一；表级触发器禁止更新和删除。完全相同的发布重试只允许幂等读取既有绑定，不同版本、change-set 或证据不能重新消费同一运行。
- 专用修正版在同一 `BEGIN IMMEDIATE` 事务内完成父版本 CAS、版本/成员写入、旧发布状态切换和全部运行绑定；默认版本指针不随发布自动变化。
- 闭环从独立账本判定已消费运行，不依赖当前父版本成员详情，因此普通增量版本重建 manifest 后不会让历史运行或旧封口任务复活。
- 账本只冻结修复运行的消费与证据关系，不提供旧交易状态物理快照。旧版本严格隔离仍需追加式修正层、差异快照或等价的按版本解析能力。
