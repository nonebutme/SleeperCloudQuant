# 复用整合方案

## 复用目标

- `已确认` 按最初需求把五仓库能力重构为 `SleeperCloudQuant` 的本地量化分析 MVP。
- `已确认` 复用方式以“能力、语义、分层、交互经验”为主，不做整库继承。
- `已确认` 每个复用结果必须落到新项目模块、API 契约和 Web 页面验收点。

## 来源项目

| 来源项目 | 复用目标 | 当前落点 |
| --- | --- | --- |
| `SleeperCloudQuant-old` | 数据仓储、回测抽象、报告读侧 | `data_platform`, `backtest_kernel`, `reporting` |
| `TradingAgents-CN-main` | Web/API 分层、配置中心、AI 分析模式 | `app`, `config_center`, `AIAnalysisService`, Web MVP |
| `rqalpha-master` | 回测运行时语义、账户/订单/持仓边界 | `domain.backtest`, `backtest_kernel` |
| `vnpy-master` | 统一交易对象和 Gateway 语义 | `domain.market`, `domain.backtest` |
| `backtrader-master` | 轻量回测体验、指标组织启发 | Web 回测体验、因子/指标展示方式 |

## 采纳边界

### 直接采纳

- `SleeperCloudQuant-old` 的仓储抽象、回测请求/结果抽象、回测结果读侧思路。
- 项目内已落点：`data_platform/repository`、`backtest_kernel/gateway`、`reporting/run_results_reader.py`。

### 改造后采纳

- `SleeperCloudQuant-old` 的 SQLite 缓存与回测服务层：拆分数据缓存、运行结果、报告读侧职责。
- `TradingAgents-CN-main` 的配置和 Web/API 分层：保留统一入口和分层思路，裁剪数据库、用户系统和外部服务强依赖。

### 语义参考

- `rqalpha-master` 的运行生命周期、订单、账户、持仓和回测配置语义。
- `vnpy-master` 的 Bar、Tick、Order、Trade、Position、Account、Gateway 语义。

### 冻结参考

- `backtrader-master` 当前只作为体验与指标组织参考，不进入源码拼接。

## 适配层

| 适配层 | 职责 | 当前状态 |
| --- | --- | --- |
| 数据 provider 适配 | 统一外部数据源和本地缓存读取 | demo provider + SQLite cache 已存在 |
| 回测运行时适配 | 将标准 BacktestRequest 转换为运行时输入 | fake rqalpha runtime + gateway 已存在 |
| 报告读侧适配 | 从运行结果存储生成报告详情和批量摘要 | reporting service 已存在 |
| AI 分析适配 | 在 mock/真实 LLM 之间保持同一报告契约 | 本阶段新增最小服务/API |
| 配置中心适配 | 暴露数据源、模型、回测参数、模板状态 | 本阶段新增 API 接入 |
| Web 展示适配 | 将 API 结果转为图表、表格、状态和详情 | 本阶段重做 Web MVP |

## 迁移步骤

1. 补齐需求基线，建立可验收范围。
2. 补齐五仓库比较和复用整合矩阵。
3. 保持已有数据、因子、回测、报告服务闭环。
4. 新增 AI 分析与配置中心最小 API。
5. 重做 Web MVP：总览、数据中心、因子分析、策略回测、AI 分析、报告中心、配置中心、重构溯源。
6. 扩展验证脚本，覆盖新增 API 和 Web demo。
7. 输出验收结果和剩余风险。

## 验证门禁

- `python scripts/run_formal_verifications.py` 必须通过。
- Web demo 首页必须返回 200。
- 以下 API 必须可访问：
  - `/api/market/price-history`
  - `/api/factors/definitions`
  - `/api/backtest/run-once`
  - `/api/reporting/run-detail/{run_id}`
  - `/api/ai/analyze`
  - `/api/config/status`
- Web 页面必须显示各模块摘要、核心表格/图表和溯源矩阵。

## 回退方案

- 若新增 AI 或配置 API 失败，可回退到只读 mock 服务，不影响数据、因子、回测、报告主链路。
- 若 Web 产品化页面失败，可保留原 API demo 文件并回退路由脚本，但需在验收报告标记 Web MVP 未通过。
- 若真实外部服务不可用，继续使用 demo/runtime 数据，并明确标记为 MVP demo 边界。

## 发布判断

### 已验证项

- 复用目标、来源项目、采纳边界、适配层和验证门禁已形成闭环。

### 未验证项

- 真实外部数据源、真实 rqalpha、真实 LLM Provider。

### 阻塞原因

- 真实外部服务需要授权、密钥和合规确认。

### 潜在风险

- 若未在 Web 层展示采纳边界，用户仍难以确认五仓库重构成果。

### 发布判断

- `已确认` 本文档可作为阶段 1 复用整合基线。
