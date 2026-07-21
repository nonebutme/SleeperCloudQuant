# 量化分析平台正式方案版

## 一、文档定位

- `已确认` 本文档是 `SleeperCloudQuant` 新项目的正式方案版文档。
- `已确认` 目的不是继续比较历史仓库，而是为后续在项目内直接进行“拼接”提供可执行蓝图。
- `已确认` 本文档聚焦以下目标：
  - 明确新项目功能边界
  - 明确分层架构
  - 明确各能力模块的推荐来源
  - 明确第一阶段 MVP 的拼接顺序
  - 明确许可证和复用边界

## 二、项目目标

### 2.1 总目标

设计并实现我自己的 PC 端 Web 量化分析平台，核心能力包括：

- 本地 A 股数据库
- 因子分析库
- 策略回测库
- AI 分析报告
- 回测分析报告

### 2.2 当前偏好

- `已确认` 比较偏好 `SleeperCloudQuant-old` 已经沉淀过的 A 股数据与回测分析报告链路。
- `已确认` 比较偏好 `TradingAgents-CN-main` 的 Web 架构、数据源配置、大模型配置管理能力。
- `已确认` 初版只考虑 PC 端 Web 界面。

### 2.3 当前非目标

- 不做移动端
- 不做实盘交易
- 不优先做多用户复杂权限系统
- 不优先做完整交易终端生态
- 不优先做跨市场全量扩展
- 不优先做复杂多智能体辩论产品化全量能力

## 三、总体判断

### 3.1 项目角色分工判断

基于前期代码考古，当前几个参考项目更适合承担如下角色：

- `SleeperCloudQuant-old`
  - 适合作为研究中台和平台适配层的主参考来源
- `TradingAgents-CN-main`
  - 适合作为 Web 产品层、配置中心、AI 分析层的主参考来源
- `rqalpha-master`
  - 适合作为回测运行语义、账户/订单/持仓抽象和回测适配目标来源
- `vnpy-master`
  - 适合作为统一交易对象模型、事件总线、网关接口语义来源
- `backtrader-master`
  - 适合作为轻量回测体验、指标组织和样例结构的参考来源

### 3.2 主架构选择

- `已确认` 新项目不建议从任何单一历史仓库整库继承。
- `已确认` 新项目建议采用“按能力拼接，而不是按仓库拼接”的方式。

建议的主干组合：

- `主底座`：`SleeperCloudQuant-old`
- `主产品层参考`：`TradingAgents-CN-main`
- `主回测适配目标`：`rqalpha-master`
- `统一对象模型语义参考`：`vnpy-master`
- `轻量回测和指标体验参考`：`backtrader-master`

## 四、目标系统分层

建议新项目按以下 8 层进行组织。

### 4.1 `domain`

职责：

- 统一领域对象
- 统一回测和分析过程中的核心数据结构

建议对象：

- `Stock`
- `Bar`
- `Tick`
- `FactorDefinition`
- `FactorValue`
- `StrategyDefinition`
- `BacktestRequest`
- `BacktestResult`
- `Order`
- `Trade`
- `Position`
- `Account`
- `AnalysisReport`
- `BacktestReport`

来源建议：

- 主参考 `vnpy-master` 的对象模型语义
- 补充参考 `rqalpha-master` 的账户、订单、持仓语义
- 延续 `SleeperCloudQuant-old` 的 `BacktestRequest / BacktestResult`

### 4.2 `data-platform`

职责：

- 本地 A 股数据库
- 数据同步、缓存、清洗、查询
- 标的基础信息、行情、财务、行业分类等数据管理

首期能力：

- 股票基础信息管理
- 日线行情缓存
- 财务指标缓存
- 指数成分缓存
- 交易日历缓存

来源建议：

- 主参考 `SleeperCloudQuant-old`
- 数据源配置方式参考 `TradingAgents-CN-main`

### 4.3 `factor-lab`

职责：

- 因子定义
- 因子计算
- 因子结果落库
- 因子排序、筛选和验证

首期能力：

- 基础价量因子
- 简单财务因子
- 技术指标型因子
- 因子结果查询与导出

来源建议：

- 以新项目自建为主
- 数据读取走 `data-platform`
- 后续可参考 `vnpy.alpha` 的研究组织方式

### 4.4 `backtest-kernel`

职责：

- 标准化回测请求
- 策略执行协议
- 回测执行器
- 回测日志、指标、结果标准化

首期能力：

- 单策略回测
- 参数化回测
- 结果落库
- 回测日志记录
- 回测指标提取

来源建议：

- 主参考 `SleeperCloudQuant-old`
- 运行时适配目标优先 `rqalpha-master`

### 4.5 `reporting`

职责：

- AI 分析报告
- 回测分析报告
- 历史报告查询与展示

首期能力：

- 单只股票 AI 研究报告
- 回测结果摘要报告
- 策略回测运行记录与指标说明

来源建议：

- AI 报告主参考 `TradingAgents-CN-main`
- 回测分析报告主参考 `SleeperCloudQuant-old`

### 4.6 `ai`

职责：

- AI 分析状态管理
- 分析流程编排
- 大模型调用和提示词组织

首期能力：

- 单股分析任务
- 多来源数据摘要
- 生成结构化分析报告

来源建议：

- 主参考 `TradingAgents-CN-main`
- 仅保留与量化分析平台强相关的最小链路

### 4.7 `config-center`

职责：

- 数据源配置
- 大模型配置
- 回测参数配置
- 报告模板配置

首期能力：

- 配置数据源启用状态
- 配置 API Key 和模型
- 配置默认回测参数

来源建议：

- 主参考 `TradingAgents-CN-main`

### 4.8 `web-app`

职责：

- PC 端 Web 界面
- 页面导航、数据展示、任务触发、结果查询

来源建议：

- 主参考 `TradingAgents-CN-main`
- 初版仅保留核心页面，不追求完整平台复制

## 五、推荐目录结构

建议新项目未来逐步收敛到如下目录结构：

```text
SleeperCloudQuant/
├── app/
│   ├── api/
│   ├── services/
│   ├── schemas/
│   ├── config/
│   └── tasks/
├── domain/
│   ├── market/
│   ├── backtest/
│   ├── factor/
│   └── report/
├── data_platform/
│   ├── repositories/
│   ├── providers/
│   ├── cache/
│   └── sync/
├── factor_lab/
│   ├── definitions/
│   ├── calculators/
│   ├── evaluators/
│   └── storage/
├── backtest_kernel/
│   ├── gateway/
│   ├── runners/
│   ├── adapters/
│   └── metrics/
├── ai/
│   ├── graph/
│   ├── agents/
│   ├── prompts/
│   └── llm/
├── reporting/
│   ├── generators/
│   ├── templates/
│   └── storage/
├── web/
│   └── frontend/
├── docs/
└── tests/
```

## 六、模块采纳策略

### 6.1 本地 A 股数据库

推荐采纳结论：

- `直接采纳/改造后采纳`：`SleeperCloudQuant-old`
- `补充参考`：`TradingAgents-CN-main`

优先复用的能力类别：

- `MarketDataRepository`
- SQLite 元数据与缓存
- Ricequant 数据读取封装
- 历史行情与交易日历读取抽象

### 6.2 因子分析库

推荐采纳结论：

- `自建为主`
- `补充参考`：`vnpy.alpha`、`SleeperCloudQuant-old`

原因：

- 当前几个参考仓库都不是以“本地因子库产品化”作为首目标
- 因子库更适合围绕你自己的数据库结构和研究习惯自建

### 6.3 策略回测库

推荐采纳结论：

- `主抽象层`：`SleeperCloudQuant-old`
- `运行时语义与适配参考`：`rqalpha-master`

优先采纳：

- `BacktestGateway`
- `BacktestRequest`
- `BacktestResult`
- `StrategyBacktestService`
- 回测元数据落库结构

### 6.4 AI 分析报告

推荐采纳结论：

- `主参考`：`TradingAgents-CN-main`
- `改造后采纳`

优先采纳：

- agent state 组织方式
- graph 编排方式
- 数据流聚合逻辑
- LLM 配置与调用抽象

### 6.5 回测分析报告

推荐采纳结论：

- `主参考`：`SleeperCloudQuant-old`
- `直接采纳/改造后采纳`

优先采纳：

- 回测结果摘要结构
- 回测日志与指标表结构
- 页面展示数据服务

### 6.6 Web 架构与配置中心

推荐采纳结论：

- `主参考`：`TradingAgents-CN-main`
- `改造后采纳`

优先采纳：

- FastAPI 项目结构
- 配置中心设计
- 数据源配置模型
- 大模型配置模型
- Web 页面组织方式

## 七、第一阶段 MVP 页面

初版建议只做 5 个页面：

### 7.1 数据中心

- 查看股票基础信息
- 查看本地行情数据覆盖范围
- 触发数据同步
- 查看数据源状态

### 7.2 因子分析

- 选择股票池
- 选择因子
- 运行因子计算
- 查看结果排序

### 7.3 策略回测

- 选择策略
- 配置区间、基准、参数
- 提交回测
- 查看运行状态和结果摘要

### 7.4 AI 分析

- 选择股票
- 触发 AI 分析
- 查看结构化分析报告

### 7.5 报告中心

- 查看 AI 分析报告
- 查看回测分析报告
- 查看历史运行记录

## 八、第一阶段不做事项

- 不做实盘交易
- 不做完整网关生态
- 不做复杂风控中心
- 不做多用户权限细粒度控制
- 不做移动端
- 不做多市场全量支持
- 不做复杂多智能体辩论产品化全量链路

## 九、第一批建议复制/改造的能力类别

注意：本节先列“类别”，不是立即执行的文件复制清单。

### 9.1 从 `SleeperCloudQuant-old` 优先吸收

- `core/backtest_gateway.py`
- `core/repository.py`
- `core/services/strategy_backtest_service.py`
- `core/services/stage_a_backtest_service.py`
- `data/cache/sqlite_cache.py`
- `data/cache/cached_market_data_repository.py`
- `data/ricequant/ricequant_backtest_adapter.py`
- `data/ricequant/ricequant_repository.py`

### 9.2 从 `TradingAgents-CN-main` 优先吸收

- `app` 的 FastAPI 分层方式
- 数据源配置模型
- 大模型配置模型
- `tradingagents/graph` 的编排模式
- `tradingagents/agents/utils/agent_states.py`
- `tradingagents/dataflows` 的 provider 分层方式

### 9.3 从 `rqalpha-master` 对齐语义

- 订单模型语义
- 账户模型语义
- 事件源接口语义
- 回测配置组织方式

### 9.4 从 `vnpy-master` 对齐语义

- `TickData / BarData / OrderData / TradeData / PositionData / AccountData`
- `BaseGateway`
- `MainEngine / EventEngine` 结构思想

## 十、推荐拼接顺序

### 阶段 1：建立中台骨架

- 以 `SleeperCloudQuant-old` 为主参考
- 建立：
  - 统一 `BacktestGateway`
  - 统一 `MarketDataRepository`
  - SQLite 结果存储

阶段目标：

- 能跑一条最小回测链路
- 能保存回测结果

### 阶段 2：统一领域对象

- 引入 `vnpy` 风格对象语义
- 补齐 `Order / Trade / Position / Account / Bar` 等领域模型

阶段目标：

- 让数据、回测、报告使用同一套核心对象语义

### 阶段 3：稳固回测内核

- 以 `rqalpha` 为首个运行时适配目标
- 保持 `SleeperCloudQuant-old` 的服务层和结果层

阶段目标：

- 策略回测闭环可重复
- 回测报告可读取

### 阶段 4：接入 Web 架构

- 参考 `TradingAgents-CN-main`
- 建立 FastAPI 接口层
- 建立 PC Web 页面最小导航

阶段目标：

- 数据、回测、报告可以通过 Web 访问

### 阶段 5：接入 AI 分析层

- 参考 `TradingAgents-CN-main`
- 先做单股 AI 分析，不一开始上完整多智能体链

阶段目标：

- 形成“数据 -> 分析 -> 报告”最小研究闭环

## 十一、许可证与复用边界

### 11.1 `backtrader-master`

- `已确认` 许可证为 GPLv3
- 风险：
  - 不适合不加审查地直接拼入新项目核心代码
- 建议：
  - 只借鉴设计和结构思想
  - 直接复制代码前必须二次审查

### 11.2 `rqalpha-master`

- `已确认` 存在非商业/授权边界描述
- 风险：
  - 直接复用源码到新平台时必须谨慎
- 建议：
  - 优先借鉴抽象和语义
  - 直接采纳代码前做单独授权与合规确认

### 11.3 `TradingAgents-CN-main`

- `已确认` 存在混合许可边界
- 风险：
  - `app/` 和 `frontend/` 相关内容不能默认视为可自由拼接
- 建议：
  - 优先借鉴架构和模式
  - 直接复用具体代码前做边界确认

### 11.4 `SleeperCloudQuant-old`

- `待确认` 当前仓库内部可复用边界需要在项目会话内进一步结合项目目标再核对
- 建议：
  - 先优先复用抽象层和服务层思路
  - 真正复制具体文件前逐项确认

## 十二、后续执行建议

后续切换到项目内会话后，建议按以下顺序继续：

1. 先把本方案拆成“第一批真实拼接清单”
2. 明确新项目目录结构和模块壳
3. 先拼 `data-platform + backtest-kernel` 最小闭环
4. 再拼 `reporting`
5. 最后拼 `web-app` 与 `ai`

### 12.1 当前推进补充说明（截至 Batch 61）

- 已确认：阶段 5：报告层（reporting） 当前已形成阶段性冻结基线，基线文档为 docs/architecture/reporting-phase5-freeze-baseline.md。
- 已确认：若没有新的 reporting 消费需求、前端真实接入需求，或 smoke / formal verification 暴露的实际缺口，默认不继续扩展 reporting 字段与只读 endpoint。
- 已确认：若继续推进当前主线开发，优先转向 阶段 6：报告存储与模板边界，而不是回到 阶段 5 做细碎读取面扩展。
## 十三、下一份建议文档

在本方案之后，建议下一步补一份更细的执行文档，命名建议：

- `docs/architecture/phase-1-stitching-plan.md`

该文档应聚焦：

- 第一批真实复制/改造的具体文件名单
- 每个文件的目标位置
- 适配层设计
- 第一轮验证清单
- 回退点

## 十四、结论

- `已确认` 新项目应以 `SleeperCloudQuant-old` 为中台主底座，以 `TradingAgents-CN-main` 为 Web 和 AI 产品层主参考。
- `已确认` `rqalpha-master` 更适合作为回测抽象和运行时语义来源。
- `已确认` `vnpy-master` 更适合作为统一对象模型和后续平台扩展语义来源。
- `已确认` 初版目标应是 PC Web 端量化研究分析平台，而不是完整交易终端。
- `已确认` 后续拼接应按能力模块逐步推进，不应整库搬迁。
