# 多仓库比较

## 比较目标

- `已确认` 本文档用于把五个参考仓库的功能价值、复用边界和目标落点整理成可验收矩阵。
- `已确认` 比较目标不是整库继承，而是按需求能力拆解、按模块重构、按页面展示验证。
- `已确认` 本文档承接 `quant-platform-recomposition-plan.md`、`reference-repository-routing.md` 与 `candidate-capability-routing.md`。

## 候选仓库

| 仓库 | 当前角色 | 主要价值 | 采纳方式 |
| --- | --- | --- | --- |
| `SleeperCloudQuant-old` | 主底座 / 研究中台主参考 | 本地 A 股数据、回测抽象、报告读侧 | 直接采纳 + 改造后采纳 |
| `TradingAgents-CN-main` | Web 产品层 / 配置中心 / AI 分析主参考 | FastAPI 分层、配置模型、AI graph 与报告体验 | 改造后采纳 + 模式参考 |
| `rqalpha-master` | 回测运行时语义来源 | 账户、订单、持仓、回测配置与生命周期语义 | 语义对齐，不直接拼源码 |
| `vnpy-master` | 统一对象模型语义来源 | Tick、Bar、Order、Trade、Position、Account、Gateway 语义 | 语义对齐，不直接拼源码 |
| `backtrader-master` | 轻量回测体验与指标组织参考 | 策略体验、指标组织、教学样例 | 参考冻结，不直接拼源码 |

## 比较矩阵

| MVP 需求 | `SleeperCloudQuant-old` | `TradingAgents-CN-main` | `rqalpha-master` | `vnpy-master` | `backtrader-master` | 新项目落点 | Web 验收页 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 本地 A 股数据中心 | 主参考：仓储、缓存、Ricequant 封装 | 参考：provider 分层和数据源配置 | 无直接采纳 | 参考：Bar/Tick 语义 | 无直接采纳 | `data_platform`, `app/api/market.py` | 数据中心 |
| 因子分析库 | 参考：研究中台数据使用方式 | 参考：产品化展示方式 | 无直接采纳 | 参考：研究对象语义 | 参考：指标组织体验 | `factor_lab`, `app/api/factor.py` | 因子分析 |
| 策略回测库 | 主参考：BacktestGateway、Request、Result、服务层 | 参考：API 分层 | 语义来源：配置、账户、订单、生命周期 | 语义来源：Order/Trade/Position/Account | 参考：轻量回测体验 | `backtest_kernel`, `app/api/backtest.py` | 策略回测 |
| AI 分析报告 | 补充参考：报告对象 | 主参考：AI graph、agent state、LLM 配置 | 无直接采纳 | 无直接采纳 | 无直接采纳 | `app/services/ai_analysis_service.py`, `app/api/ai.py` | AI 分析 |
| 回测分析报告 | 主参考：结果摘要、日志、指标、读侧 | 参考：报告列表/详情 API | 参考：指标语义 | 参考：交易对象语义 | 参考：指标体验 | `reporting`, `app/api/reporting.py` | 报告中心 |
| 配置中心 | 参考：回测 profile、Ricequant 配置 | 主参考：配置模型、统一配置入口 | 参考：回测参数 | 无直接采纳 | 无直接采纳 | `config_center`, `app/api/config.py` | 配置中心 |
| 重构溯源 | 主来源之一 | 主来源之一 | 语义来源 | 语义来源 | 冻结参考 | 文档 + Web 静态溯源模型 | 重构溯源 |

## 采纳建议

1. `SleeperCloudQuant-old`
   - `已确认` 继续作为数据平台、回测内核、报告中心的主承接来源。
   - `已确认` 采纳时必须拆分旧项目耦合，不能整目录搬迁。
2. `TradingAgents-CN-main`
   - `已确认` 继续作为 Web 产品层、配置中心和 AI 分析的主参考来源。
   - `已确认` 当前只吸收分层、配置与 AI 编排思路，不复制完整多智能体产品。
3. `rqalpha-master`
   - `已确认` 作为首个回测运行时语义对齐目标。
   - `已确认` 当前不直接复用源码，避免授权和适配成本失控。
4. `vnpy-master`
   - `已确认` 作为统一领域对象和后续网关扩展语义来源。
   - `已确认` 当前不引入完整事件引擎和交易终端生态。
5. `backtrader-master`
   - `已确认` 冻结为体验、指标组织和样例结构参考。
   - `已确认` 鉴于 GPLv3 风险，当前不直接拼入核心代码。

## 风险与待确认事项

- `待确认` 外部仓库许可证和具体文件级复用授权仍需在真实复制前单独审查。
- `待确认` 真实 rqalpha 运行时接入范围和非商业/授权边界。
- `待确认` TradingAgents-CN-main 中 AI 与前端相关代码的可复用边界。
- `已确认` 当前 MVP 可以先用 demo/runtime 和自建服务表达重构成果，再进入真实外部依赖。

## 发布判断

### 已验证项

- 五个仓库的角色、采纳方式、目标模块和 Web 验收页已建立矩阵。
- 每个最初需求都能追踪到至少一个来源判断和一个新项目落点。

### 未验证项

- 文件级许可证复核。
- 真实外部运行时和真实 AI Provider 接入。

### 阻塞原因

- 真实复制源码前需要授权确认。
- 真实外部服务接入前需要密钥、数据权限和合规边界确认。

### 潜在风险

- 若把语义参考仓库误当作源码拼接来源，会扩大维护与授权风险。
- 若 Web 只展示 API JSON，用户仍无法判断功能正确性。

### 发布判断

- `已确认` 本文档可作为阶段 1 的多仓库比较基线。
