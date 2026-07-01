# 领域对象边界规划

## 一、文档定位

- `已确认` 本文档是领域对象边界的规划版，不是实现文档。
- `已确认` 本文档只定义对象职责、最小字段范围、对象关系和语义来源。
- `已确认` 本文档不直接落地为数据库表、API schema 或代码模型。

## 二、输入来源

- `docs/architecture/quant-platform-recomposition-plan.md`
- `docs/workflows/recomposition-execution-plan.md`
- `docs/code-archaeology/reference-repository-routing.md`
- `docs/code-archaeology/candidate-capability-routing.md`
- `docs/architecture/phase-1-stitching-plan.md`

## 三、范围边界

### 3.1 纳入对象

- `Stock`
- `Bar`
- `Tick`
- `Order`
- `Trade`
- `Position`
- `Account`
- `BacktestRequest`
- `BacktestResult`
- `AnalysisReport`
- `BacktestReport`
- `FactorDefinition`
- `FactorValue`
- `StrategyDefinition`

### 3.2 当前不纳入

- 数据库表结构
- 事件总线实现对象
- 页面视图对象
- 外部接口 DTO
- 配置中心对象

## 四、总体边界原则

### 4.1 已确认

- 领域对象优先服务于 `data-platform`、`backtest-kernel`、`reporting` 和后续 `factor-lab`。
- 领域对象应先稳定语义，再进入模块实现。
- 领域对象不应直接绑定某一来源仓库的工程结构。

### 4.2 语义参考优先级

- 交易对象与账户对象语义：优先参考 `vnpy-master`，补充参考 `rqalpha-master`
- 回测请求与回测结果语义：优先参考 `SleeperCloudQuant-old`，补充参考 `rqalpha-master`
- 研究与报告对象语义：优先参考 `SleeperCloudQuant-old`
- 因子与策略定义对象：以新项目自有边界为主，参考现有方案文档约束

## 五、对象边界

### 5.1 `Stock`

#### 职责

- 表达可分析标的的最小静态身份信息。
- 作为行情、因子、回测和报告的核心关联对象。

#### 最小字段范围

- `symbol`
- `exchange`
- `name`
- `market`
- `industry`
- `status`

#### 主要关系

- 一个 `Stock` 可以关联多个 `Bar`
- 一个 `Stock` 可以关联多个 `Tick`
- 一个 `Stock` 可以关联多个 `FactorValue`
- 一个 `Stock` 可以出现在多个 `AnalysisReport`

#### 语义来源

- `基于当前上下文推断` 以新项目自定义为主
- `补充参考` `vnpy-master` 的交易标的表达习惯

#### 待确认

- `exchange` 与 `market` 是否同时保留
- 行业分类是否在领域对象内保留，还是下沉到数据扩展层

### 5.2 `Bar`

#### 职责

- 表达固定周期行情条目。
- 作为因子计算、回测输入和报告摘要的基础行情对象。

#### 最小字段范围

- `symbol`
- `exchange`
- `datetime`
- `interval`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `turnover`

#### 主要关系

- 属于一个 `Stock`
- 可被 `BacktestRequest` 引用为输入数据范围
- 可被 `FactorValue` 计算过程引用

#### 语义来源

- `主参考` `vnpy-master`

#### 待确认

- `turnover` 是否为强制字段
- 复权处理是对象外约定，还是字段内显式标识

### 5.3 `Tick`

#### 职责

- 表达逐笔或细粒度实时/准实时行情快照。
- 为后续扩展更高频研究能力预留统一对象语义。

#### 最小字段范围

- `symbol`
- `exchange`
- `datetime`
- `last_price`
- `volume`
- `turnover`
- `bid_price_1`
- `ask_price_1`

#### 主要关系

- 属于一个 `Stock`
- 当前阶段不作为首批回测核心输入

#### 语义来源

- `主参考` `vnpy-master`

#### 待确认

- 首阶段是否只保留一级盘口字段
- 是否允许当前阶段只定义对象，不进入数据落盘

### 5.4 `Order`

#### 职责

- 表达策略或回测过程中产生的委托意图。
- 统一回测运行时与结果记录中的订单语义。

#### 最小字段范围

- `order_id`
- `symbol`
- `exchange`
- `side`
- `type`
- `price`
- `volume`
- `filled_volume`
- `status`
- `submitted_at`

#### 主要关系

- 可关联一个或多个 `Trade`
- 可归属于一个 `Account`
- 可归属于一次 `BacktestResult`

#### 语义来源

- `主参考` `rqalpha-master`
- `补充参考` `vnpy-master`

#### 待确认

- `side` 与 `direction` 是否二选一
- 是否需要在对象层显式区分开平语义

### 5.5 `Trade`

#### 职责

- 表达订单成交结果。
- 作为持仓变化、收益计算和结果报告的事实依据。

#### 最小字段范围

- `trade_id`
- `order_id`
- `symbol`
- `exchange`
- `side`
- `price`
- `volume`
- `traded_at`
- `commission`

#### 主要关系

- 必须关联一个 `Order`
- 可影响一个 `Position`
- 可归属于一个 `BacktestResult`

#### 语义来源

- `主参考` `vnpy-master`
- `补充参考` `rqalpha-master`

#### 待确认

- 成交税费是否独立字段建模
- 成交对象是否保留更细粒度执行信息

### 5.6 `Position`

#### 职责

- 表达账户对某标的的持仓状态。
- 为收益、风险、仓位和报告分析提供统一持仓对象。

#### 最小字段范围

- `symbol`
- `exchange`
- `direction`
- `volume`
- `available_volume`
- `avg_price`
- `market_value`
- `floating_pnl`

#### 主要关系

- 归属于一个 `Account`
- 可被多个 `Trade` 更新
- 可被 `BacktestReport` 汇总分析

#### 语义来源

- `主参考` `rqalpha-master`
- `补充参考` `vnpy-master`

#### 待确认

- A 股长仓场景下是否仍保留通用 `direction`
- 是否需要区分昨日持仓、今日持仓等扩展字段

### 5.7 `Account`

#### 职责

- 表达回测账户或研究账户的资金与持仓聚合状态。
- 为回测结果和报告输出提供账户层统一视角。

#### 最小字段范围

- `account_id`
- `currency`
- `initial_cash`
- `available_cash`
- `frozen_cash`
- `total_value`
- `positions_value`
- `net_value`

#### 主要关系

- 可关联多个 `Position`
- 可关联多个 `Order`
- 可归属于一次 `BacktestResult`

#### 语义来源

- `主参考` `rqalpha-master`
- `补充参考` `vnpy-master`

#### 待确认

- 是否需要把收益率字段放在账户对象，还是只放在结果对象
- 首阶段是否默认单账户

### 5.8 `BacktestRequest`

#### 职责

- 表达一次标准化回测请求。
- 作为回测执行入口的统一协议对象。

#### 最小字段范围

- `request_id`
- `strategy_id`
- `symbols`
- `start_date`
- `end_date`
- `benchmark`
- `initial_cash`
- `parameters`
- `frequency`

#### 主要关系

- 关联一个 `StrategyDefinition`
- 生成一个 `BacktestResult`

#### 语义来源

- `主参考` `SleeperCloudQuant-old`
- `补充参考` `rqalpha-master`

#### 待确认

- `symbols` 是单标的还是标的池统一字段
- 参数是否保持弱约束字典结构

### 5.9 `BacktestResult`

#### 职责

- 表达一次回测执行后的标准化结果。
- 为报告、查询和历史记录提供统一结果出口。

#### 最小字段范围

- `result_id`
- `request_id`
- `status`
- `started_at`
- `finished_at`
- `account_snapshot`
- `orders_summary`
- `trades_summary`
- `metrics`

#### 主要关系

- 必须关联一个 `BacktestRequest`
- 可关联多个 `Order`
- 可关联多个 `Trade`
- 可生成一个 `BacktestReport`

#### 语义来源

- `主参考` `SleeperCloudQuant-old`
- `补充参考` `rqalpha-master`

#### 待确认

- `account_snapshot` 是聚合对象还是独立版本化对象
- `metrics` 是否在领域对象内只保留摘要

### 5.10 `AnalysisReport`

#### 职责

- 表达单标的或研究任务输出的结构化分析结果。
- 为 AI 分析与研究结果查询提供统一对象出口。

#### 最小字段范围

- `report_id`
- `report_type`
- `symbol`
- `generated_at`
- `summary`
- `key_points`
- `risks`
- `conclusion`

#### 主要关系

- 可关联一个 `Stock`
- 后续可与 `FactorValue`、`BacktestResult` 建立弱关联

#### 语义来源

- `主参考` `SleeperCloudQuant-old`
- `补充参考` `TradingAgents-CN-main`

#### 待确认

- 首阶段是否允许 `symbol` 为空以支持组合级分析
- `key_points` 和 `risks` 是否强制结构化

### 5.11 `BacktestReport`

#### 职责

- 表达对某次回测结果的结构化总结。
- 统一回测结果摘要、指标解释和风险提示的承载形式。

#### 最小字段范围

- `report_id`
- `result_id`
- `generated_at`
- `summary`
- `performance_metrics`
- `risk_metrics`
- `observations`
- `conclusion`

#### 主要关系

- 必须关联一个 `BacktestResult`

#### 语义来源

- `主参考` `SleeperCloudQuant-old`

#### 待确认

- `performance_metrics` 与 `risk_metrics` 的边界是否拆分过细
- 是否需要保留可回放的图表数据引用

### 5.12 `FactorDefinition`

#### 职责

- 表达因子的静态定义、计算标识与使用边界。
- 为因子计算、筛选和结果解释提供统一定义入口。

#### 最小字段范围

- `factor_id`
- `name`
- `category`
- `description`
- `formula_ref`
- `parameters`
- `frequency`

#### 主要关系

- 可关联多个 `FactorValue`

#### 语义来源

- `基于当前上下文推断` 以新项目自建为主

#### 待确认

- `formula_ref` 是文本表达、代码引用还是注册键
- 因子参数是否统一弱约束

### 5.13 `FactorValue`

#### 职责

- 表达因子在某标的、某时点或某区间上的计算结果。
- 为排序、筛选、验证和报告引用提供统一值对象。

#### 最小字段范围

- `factor_id`
- `symbol`
- `datetime`
- `value`
- `version`
- `source_window`

#### 主要关系

- 必须关联一个 `FactorDefinition`
- 必须关联一个 `Stock`

#### 语义来源

- `基于当前上下文推断` 以新项目自建为主

#### 待确认

- `value` 是否允许向量或多字段结果
- 是否需要把标准化值与原始值分开

### 5.14 `StrategyDefinition`

#### 职责

- 表达策略的静态定义、参数边界和执行入口标识。
- 为回测请求和策略管理提供统一引用对象。

#### 最小字段范围

- `strategy_id`
- `name`
- `description`
- `entry_ref`
- `parameters_schema`
- `universe_scope`
- `frequency`

#### 主要关系

- 可关联多个 `BacktestRequest`

#### 语义来源

- `基于当前上下文推断` 以新项目自建为主
- `补充参考` `SleeperCloudQuant-old`

#### 待确认

- `entry_ref` 是代码路径、注册名还是任务标识
- 参数模式是否要在领域层强约束

## 六、对象关系摘要

### 6.1 数据与研究关系

- `Stock` -> `Bar`
- `Stock` -> `Tick`
- `Stock` -> `FactorValue`
- `FactorDefinition` -> `FactorValue`
- `Stock` -> `AnalysisReport`

### 6.2 回测关系

- `StrategyDefinition` -> `BacktestRequest`
- `BacktestRequest` -> `BacktestResult`
- `BacktestResult` -> `Order`
- `BacktestResult` -> `Trade`
- `BacktestResult` -> `BacktestReport`
- `Account` -> `Position`
- `Order` -> `Trade`

## 七、当前阶段不做的事

- 不定义 ORM 模型
- 不定义 API schema
- 不定义数据库字段类型
- 不定义事件驱动接口细节
- 不定义序列化格式

## 八、后续建议

1. 基于本文件继续产出 `backtest-kernel-minimum-spec.md`
2. 基于本文件继续产出 `data-platform-minimum-spec.md`
3. 在进入实现前，再把对象字段从“最小范围”推进到“字段级确认版”

## 九、发布判断

### 已验证项

- 交易、回测、研究、报告、因子和策略定义对象已形成统一候选边界
- 主要语义来源已区分为 `vnpy-master`、`rqalpha-master`、`SleeperCloudQuant-old` 和新项目自建

### 未验证项

- 各对象字段是否最终足够支撑首批实现
- 部分对象是否需要拆成摘要对象与明细对象
- 多标的、多账户和组合级场景是否在首阶段保留

### 阻塞原因

- 当前仍未进入字段级实现确认
- 回测结果、报告和因子结果之间的关联粒度仍待后续规格化

### 潜在风险

- 若在字段未确认前直接编码，后续对象调整会连带影响多个模块
- 若过早把对象绑定到某来源仓库实现，会削弱新项目的统一边界

### 发布判断

- `已确认` 本文档可作为下一轮模块规格文档的共同基础
- `待确认` 仍不应直接把本文件视为最终实现契约

