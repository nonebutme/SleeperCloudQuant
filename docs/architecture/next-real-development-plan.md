# 下一阶段真实开发计划

## 1. 当前基线

### 1.1 已确认

- `data_platform`、`backtest_kernel`、`reporting`、`config_center` 已收束到正式模块。
- 深层 `phase1_*` 副本、兼容入口、fake/demo 资产均已清退完成。
- 当前统一验证入口为：`python scripts/run_formal_verifications.py`
- 当前本地验证链已通过，正式包导入检查也已通过。

### 1.2 已确认但仍然缺失

当前项目仍缺少以下正式开发骨架：

- `domain/` 统一领域对象层
- `app/` 应用服务层与 API 层
- 面向真实调用方的服务编排入口
- 最小 Web/API 访问面
- 真实运行态下的数据写入与回测任务编排边界

### 1.3 基于当前上下文推断

按照核心方案文档与当前仓结构，下一轮真实开发不应该直接跳到前端页面，而应该先补齐：

1. `domain` 最小统一对象层
2. `app` 最小服务编排层
3. 最小 FastAPI API 壳层

## 2. 下一阶段目标

把当前“可导入的正式模块”推进为“可被应用层调用的最小本地量化服务骨架”。

目标不是立刻做完整产品，而是先形成：

- 数据查询服务入口
- 单次回测服务入口
- 结果读取服务入口
- 最小 API 路由入口

## 3. 推荐推进顺序

### 3.1 第一批：补齐 `domain` 最小对象层

目标：为数据、回测、报告三条链提供统一输入输出对象语义。

建议新增：

- `domain/market/models.py`
- `domain/backtest/models.py`
- `domain/report/models.py`
- `domain/common/enums.py`

首批最小对象建议：

- `Bar`
- `Stock`
- `BacktestRequest`
- `BacktestResultSummary`
- `BacktestRunDetail`
- `BatchExperimentSummary`

本批原则：

- 只做最小 dataclass / typed model
- 不做大规模对象体系扩展
- 不提前引入复杂事件总线或交易对象全集

### 3.2 第二批：补齐 `app` 服务编排层

目标：让正式模块从“库”变成“应用服务”。

建议新增：

- `app/services/market_data_service.py`
- `app/services/backtest_service.py`
- `app/services/reporting_service.py`
- `app/schemas/` 下的最小请求/响应模型

建议服务职责：

- `MarketDataService`
  - 查询历史行情
  - 查询交易日历
- `BacktestService`
  - 提交单次回测
  - 返回最小回测结果摘要
- `ReportingService`
  - 查询单次回测详情
  - 查询批量实验摘要

本批原则：

- 只编排已存在的正式模块
- 不在服务层重复实现核心逻辑
- 先做同步最小链路，不急着做任务队列

### 3.3 第三批：补齐最小 API 壳层

目标：让本地 Web/API 系统第一次具备可访问入口。

建议新增：

- `app/api/market.py`
- `app/api/backtest.py`
- `app/api/reporting.py`
- `app/main.py`

建议首批 API：

- `GET /api/market/price-history`
- `GET /api/market/trading-calendar`
- `POST /api/backtest/run-once`
- `GET /api/reporting/run-detail/{run_id}`
- `GET /api/reporting/batch-summary/{experiment_id}`

本批原则：

- 只做最小只读/单次执行接口
- 不扩到 AI 分析接口
- 不扩到前端页面

### 3.4 第四批：补齐真实运行最小验证

目标：把当前“脚本级验证”提升为“服务级验证”。

建议新增：

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- 若项目接受，再补 `tests/` 目录最小测试样例

建议验证项：

- 服务层可构造并调用正式模块
- API 层可启动并返回最小响应
- 回测链和报告链在无真实外部依赖时可通过 fake 运行时完成 smoke test

## 4. 当前不建议立刻进入的方向

### 4.1 不建议立刻做

- 前端页面实现
- AI 分析流程接入
- 多用户权限
- 异步任务系统
- 完整领域对象全集
- 真实 Ricequant / RQAlpha 运行时集成落地

### 4.2 原因

- 当前正式模块虽已收束，但应用层还不存在。
- 若现在直接做前端或 AI，会把边界重新打散。
- 先把 `domain + app + api` 三层最小骨架立住，后续扩展会稳得多。

## 5. 推荐的下一批实际执行范围

如果进入下一轮真实开发，我建议先执行下面这一批，而不是一次全开：

### 推荐批次 A：`domain + app/services`

包含：

- 新建 `domain/` 最小对象层
- 新建 `app/services/` 三个正式服务
- 新建 `app/schemas/` 最小请求/响应模型
- 补一个本地 smoke 脚本验证服务层编排

这是当前最稳的一步，因为：

- 不引入新的运行时依赖
- 不引入前端复杂度
- 直接把已有正式模块变成可调用系统骨架

## 6. 发布判断

- `已确认`：Phase 1 回收与清退工作已闭环。
- `已确认`：项目可以进入下一阶段真实开发。
- `建议`：下一轮从 `domain + app/services` 最小骨架开始，而不是直接做前端或 AI。
