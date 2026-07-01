# 候选能力路由清单

## 一、文档定位

- `已确认` 本文档用于承接当前保守型推进策略下的下一阶段入口。
- `已确认` 本文档只处理能力类别级候选、语义对齐方向和参考冻结边界。
- `已确认` 本文档不是逐文件拼接清单，不直接授权进入源码复制或目录迁移。

## 二、输入来源

- `docs/architecture/quant-platform-recomposition-plan.md`
- `docs/workflows/recomposition-execution-plan.md`
- `docs/code-archaeology/reference-repository-routing.md`

## 三、目标输出

本文件只回答以下问题：

1. `SleeperCloudQuant-old` 和 `TradingAgents-CN-main` 分别有哪些能力类别值得进入后续拆解。
2. `rqalpha-master` 和 `vnpy-master` 需要提炼哪些语义，不进入哪些源码拼接。
3. `backtrader-master` 当前为什么冻结在参考层。
4. 下一阶段若继续推进，应优先进入哪些能力类别。

## 四、主拼接来源候选能力

### 4.1 `SleeperCloudQuant-old`

当前角色：

- `主底座`
- `研究中台主参考`
- `平台适配层主参考`

候选能力类别：

#### A. 数据平台候选能力

- `MarketDataRepository`
- 本地缓存与查询抽象
- 历史行情读取能力
- 交易日历读取能力
- 数据仓储访问边界

目标模块：

- `data-platform`

当前判断：

- `直接采纳候选`
- `改造后采纳候选`

说明：

- 适合优先进入后续拆解。
- 重点是能力边界、仓储抽象和缓存职责，不是立即复制实现文件。

#### B. 回测内核候选能力

- `BacktestGateway`
- `BacktestRequest`
- `BacktestResult`
- 回测服务层
- 回测运行元数据结构
- 回测结果落库结构

目标模块：

- `backtest-kernel`

当前判断：

- `直接采纳候选`
- `改造后采纳候选`

说明：

- 这是当前最值得优先拆解的能力簇之一。
- 后续应先做回测请求、执行、结果三段式能力边界确认。

#### C. 回测报告候选能力

- 回测摘要结构
- 指标统计结构
- 回测日志展示数据结构
- 报告数据服务边界

目标模块：

- `reporting`

当前判断：

- `改造后采纳候选`

说明：

- 可作为 `reporting` 的首个稳定输入来源。
- 需要结合新项目统一领域对象后再判断最终形态。

### 4.2 `TradingAgents-CN-main`

当前角色：

- `Web 产品层主参考`
- `配置中心主参考`
- `AI 分析层主参考`

候选能力类别：

#### A. Web 架构候选能力

- FastAPI 分层方式
- API 组织方式
- 服务层与接口层分离方式
- 页面导航与最小产品壳结构

目标模块：

- `web-app`
- `app`

当前判断：

- `改造后采纳候选`

说明：

- 更适合作为架构模式来源，而不是直接搬现成页面。
- 后续应先抽象接口层和服务层边界，再讨论具体页面实现。

#### B. 配置中心候选能力

- 数据源配置模型
- 大模型配置模型
- 默认参数配置思路
- 配置读取与校验流程

目标模块：

- `config-center`

当前判断：

- `改造后采纳候选`

说明：

- 是当前非常适合进入后续拆解的能力类别。
- 尤其适合在未锁定全部技术细节前，先定义配置边界。

#### C. AI 编排候选能力

- graph 编排模式
- agent state 组织方式
- 数据流聚合方式
- LLM 调用抽象

目标模块：

- `ai`

当前判断：

- `仅参考`
- `改造后采纳候选`

说明：

- 当前阶段只建议吸收最小链路组织方式。
- 不建议一开始引入完整多智能体产品化能力。

#### D. Provider 分层候选能力

- 数据流 provider 分层方式
- 外部数据适配边界
- 数据聚合入口组织方式

目标模块：

- `data-platform`
- `ai`

当前判断：

- `仅参考`
- `改造后采纳候选`

说明：

- 适合作为后续统一外部依赖接入方式的结构参考。
- 当前不应直接等同为新项目的数据平台实现。

## 五、语义对齐清单

### 5.1 `rqalpha-master`

当前角色：

- `回测运行时语义来源`
- `首个回测适配目标参考`

应吸收的语义：

- 订单语义
- 账户语义
- 持仓语义
- 回测配置组织方式
- 事件与执行流程语义

目标模块：

- `backtest-kernel`
- `domain`

当前明确不进入的内容：

- 不把当前目标定义为整合 `rqalpha` 源码
- 不直接进入逐文件拼接
- 不在未确认授权边界前直接复制其回测实现

### 5.2 `vnpy-master`

当前角色：

- `统一对象模型语义来源`

应吸收的语义：

- `TickData`
- `BarData`
- `OrderData`
- `TradeData`
- `PositionData`
- `AccountData`
- `BaseGateway` 的结构思想

目标模块：

- `domain`
- `backtest-kernel`

当前明确不进入的内容：

- 不把 `vnpy-master` 作为主拼接代码源
- 不直接复制其工程结构
- 不在当前阶段进入逐文件搬运

## 六、参考仓库冻结说明

### 6.1 `backtrader-master`

当前角色：

- `轻量回测体验参考`
- `指标组织参考`
- `样例结构参考`

当前冻结结论：

- `已确认` 当前停留在参考层
- `已确认` 当前不进入直接拼接候选

冻结原因：

- 当前方案中它不是主底座，也不是主适配目标
- 当前更需要的是统一领域对象与回测抽象，而不是另一套轻量运行框架
- 许可证边界需要额外谨慎审查

允许吸收的内容：

- 结构思路
- 指标组织启发
- 轻量回测体验启发

当前不允许推进的内容：

- 逐文件复制
- 作为主底座进入拼接队列
- 在未审查许可前直接复用代码

## 七、推荐优先级

### 7.1 第一优先级

- `SleeperCloudQuant-old` 的 `data-platform` 候选能力
- `SleeperCloudQuant-old` 的 `backtest-kernel` 候选能力
- `TradingAgents-CN-main` 的 `config-center` 候选能力

原因：

- 这三类最直接支撑最小研究闭环。
- 且不会过早把项目推向页面壳或复杂 AI 外壳。

### 7.2 第二优先级

- `TradingAgents-CN-main` 的 `web-app` 架构候选能力
- `rqalpha-master` 的回测语义清单
- `vnpy-master` 的领域对象语义清单

原因：

- 有助于后续把中后台能力映射为统一接口和统一对象。

### 7.3 第三优先级

- `TradingAgents-CN-main` 的 AI 编排候选能力
- `backtrader-master` 的体验与结构参考

原因：

- 当前不应让 AI 外壳或次要运行框架主导架构决策。

## 八、下一阶段入口建议

若继续保持保守型推进，下一步建议产出：

1. `docs/architecture/phase-1-stitching-plan.md`
   说明：
   只处理 `SleeperCloudQuant-old` 与 `TradingAgents-CN-main` 的第一批候选能力，不进入跨仓库全面展开。
2. `docs/architecture/domain-boundary-spec.md`
   说明：
   把 `vnpy-master` 与 `rqalpha-master` 的语义收敛为统一领域对象边界。
3. `docs/architecture/backtest-kernel-minimum-spec.md`
   说明：
   把 `SleeperCloudQuant-old` 的回测主抽象和 `rqalpha-master` 的语义对齐成可实现规格。

## 九、发布判断

### 已验证项

- 主拼接来源、语义对齐来源和参考冻结来源已经能清晰区分。
- 当前可以进入“能力类别级候选收敛”，仍不必进入逐文件拼接。

### 未验证项

- 每类候选能力的逐文件映射
- 每个候选能力的授权边界
- 具体目标位置与适配层设计

### 阻塞原因

- 当前仍缺少文件级落点映射
- 当前仍缺少逐项授权确认

### 潜在风险

- 若跳过候选能力收敛，直接进入文件级拼接，后续返工概率很高
- 若过早引入 Web 或 AI 外壳，容易让底层对象语义失稳

### 发布判断

- `已确认` 本文档可以作为下一轮保守型推进的直接入口
- `待确认` 逐文件拼接仍需你后续单独确认

