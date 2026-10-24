# 阶段 90 数据分层治理纠偏

## 1. 治理范围

本阶段以已确认的 9 个非空正式数据库、77 张受治理表为边界。治理优先修正元数据、权威关系和血缘，不移动业务表，不重写业务记录，不删除临时库、备份或占位文件。

## 2. 最终主层分布

| 主层 | 表数 | 定义 |
| --- | ---: | --- |
| F1 | 2 | 直接观察的来源事件事实 |
| F2 | 12 | 完成代码、日期、字段、有效期或复权口径标准化的事实 |
| F3 | 3 | 已发布版本数据集及回测域冻结输入 |
| F4 | 6 | 因子定义、观察值、快照、制品和值 |
| F5 | 3 | 策略定义、清单和不可变源码版本 |
| F6 | 10 | 执行和分析结果 |
| C1 | 35 | 配置、任务、质量、同步和审计控制 |
| X | 6 | 非权威兼容副本和可重建缓存 |

每张表只有一个主层。`secondary_layers` 仅表达混合职责，不形成第二个权威主层：

- `backtest.backtest_runs`：F6 主层，C1 辅助属性；
- `screening.screening_items`：F6 主层，C1 辅助属性；
- `single_task.single_backtest_tasks`：C1 主层，F6 辅助属性；
- `portfolio.portfolio_tasks`：C1 主层，F6 辅助属性。

## 3. P0 分层纠偏

- `market_daily_prices`、指数日线、证券主数据、交易日历、复权因子、生命周期和交易状态由 F1 调整为 F2。
- `classification_intervals` 和板块目录/日线/资金流由 F1 调整为 F2。
- `data_versions`、`data_version_members` 调整为 F3。
- `backtest_input_snapshots` 调整为 F3，并定义为“回测域冻结输入”。
- 因子、筛选、单品种、组合和研究任务控制表调整为 C1。
- `backtest_logs` 调整为 C1。
- 回测库旧 `market_sync_runs` 由 X 调整为 C1；其权威状态为 `legacy_control`。
- `data_correction_overlays` 保持 C1。发布后的标准事实和数据版本分别由 F2、F3 承载。

## 4. P1 权威顺序与血缘

关键血缘由 9 条扩展为 22 条，覆盖：

1. 公司行动 → 复权因子 → raw/qfq/hfq 物化行情；
2. 标准行情与质量报告 → 数据版本及成员；
3. 数据版本、分类区间、指数成分 → 因子任务、观察值及制品；
4. 数据版本和因子制品 → 回测输入快照 → 回测运行；
5. 回测运行 → 账户、持仓、成交、指标和报告；
6. 正式行情/交易日历 → 旧回测缓存投影。

权威顺序：

- 行情：`market.market_daily_prices` 高于回测库行情缓存；
- 交易日历：`market.market_trade_calendar` 高于回测库日历缓存；
- 指数成分：`market.index_component_intervals` 高于因子库兼容表；
- 回测结果：结构化 F6 表是计算与分析权威结果，任务表中的 JSON 只作为任务摘要；
- 报告：`report_snapshots` 是不可变报告快照，`report_packages` 是交付封装。

## 5. P2 重复和命名治理规则

本阶段先冻结规则，不进行物理拆表或重写：

- `market_daily_prices` 定义为 raw/qfq/hfq “同表分口径物化”，`adjustment` 是必需口径键。
- raw 是价格来源事实语义；qfq/hfq 是通过复权因子派生的标准化物化结果。
- 回测库 `market_price_bars`、`market_data_cache`、`trading_calendar_cache` 均不得反向成为正式行情权威源。
- 任务表的 `result_json`、`summary_json`、`metrics_json` 是展示/恢复摘要；与结构化 F6 表冲突时以结构化结果为准。
- 新增字段优先使用 `trade_date`；遗留 `date` 暂不重命名。
- 新增证券标识应明确类型：证券使用 `symbol`，指数使用 `index_code`；外部引擎代码作为映射字段，不作为全局主键。
- 时间字段语义固定：`observed_at` 表示来源观察，`imported_at` 表示入库，`created_at` 表示业务记录创建，`updated_at` 表示最后修改。

以下事项仍为待确认：raw/qfq/hfq 行数差异的逐证券原因；在性能和存储基准完成前，不决定是否取消 qfq/hfq 物化。

## 6. P3 文件生命周期登记口径

当前文件级盘点快照：

- 正式业务库：9 个非空 SQLite 文件；
- 活跃目录另有 2 个零字节占位文件，标记“待确认/待退出”；
- `tmp`：约 797 个 SQLite 文件、约 5.32 GB；
- 备份：4 个 SQLite 文件、约 38.74 GB；
- 全项目：约 812 个 SQLite 文件。

阶段 89 迁移源 `tmp/formal_http_demo.sqlite3` 不属于普通测试临时库，保持迁移源身份。任何文件删除、归档、压缩或迁移必须在 P3 执行阶段单独审批。

## 7. 实施结果

- 机器资产目录保持 77 项唯一资产；
- 资产注册表支持 `secondary_layers`；
- 血缘登记扩展到 22 条；
- 资产和血缘查询不再隐式执行 schema 刷新，GET/读取保持只读；
- 业务表、业务记录、临时文件、备份和占位文件均未改动。
