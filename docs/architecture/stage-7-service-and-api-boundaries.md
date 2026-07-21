# 阶段 7 服务职责与 API 契约边界
时间：`2026-07-05`

## 一、文档定位

- `已确认`：本文档用于收束阶段 7 中 `app/services`、`app/api` 与 `http_adapter` 的最小职责边界。
- `已确认`：本文档不新增生产功能，只整理当前实现中哪些能力属于阶段 7 必要闭环，哪些能力暂不继续外扩。
- `已确认`：本文档服务于阶段 7“最小本地量化服务闭环”，不替代阶段 5 `reporting` 冻结基线，也不重开阶段 6 报告快照实现。

## 二、当前服务层职责判断

### 2.1 `MarketDataService`

当前职责可收束为：

- 行情读取
- 指数成分读取
- 交易日历读取
- 最小同步摘要与同步状态透出

阶段 7 判断：

- `已确认`：该服务属于阶段 7 必要服务
- `已确认`：当前可接受“读取 + 最小同步摘要”组合
- `不建议`：继续在本阶段加入更复杂的数据清洗编排、批量同步编排或远程数据源切换逻辑

### 2.2 `FactorResearchService`

当前职责可收束为：

- 因子定义枚举
- 股票池成员读取
- 单因子运行
- 多标的 / 指数组合运行
- 因子结果查询、截面摘要与 top-n 排序

阶段 7 判断：

- `已确认`：该服务属于阶段 7 必要服务
- `已确认`：它是当前服务层里相对更厚的一层，但仍在“最小研究闭环”范围内
- `不建议`：继续在本阶段扩成通用研究工作流引擎、任务编排器或复杂导出层

### 2.3 `BacktestService`

当前职责可收束为：

- 把应用层请求模型映射为回测用例输入
- 返回最小回测结果摘要
- 透出原始运行结果供上层持久化服务使用

阶段 7 判断：

- `已确认`：该服务属于阶段 7 必要服务
- `已确认`：应继续保持“薄封装”定位
- `不建议`：在本服务中直接叠加持久化、副作用控制或批量编排逻辑

### 2.4 `PersistentBacktestService`

当前职责可收束为：

- 在单次回测前后写入运行态元数据
- 提取并持久化 logs / trades / positions / accounts / yearly_returns
- 把执行失败转写为最小失败状态

阶段 7 判断：

- `已确认`：该服务属于阶段 7 必要服务
- `已确认`：它是“回测执行”和“运行态留痕”之间的边界层
- `不建议`：继续在本阶段扩成更通用的生命周期引擎、任务调度器或报告快照入口

### 2.5 `BatchResearchService`

当前职责可收束为：

- 对多个单次回测请求做顺序编排
- 汇总成功 / 失败结果
- 产出最小实验摘要并写入运行态存储

阶段 7 判断：

- `已确认`：该服务属于阶段 7 必要服务
- `已确认`：当前同步串行批量执行仍符合阶段 7 边界
- `不建议`：继续扩为异步队列、分布式任务系统或更复杂的实验调度层

### 2.6 `ReportingService`

当前职责可收束为：

- 读取单次回测详情
- 读取批量实验摘要
- 将底层 reporting 读取对象映射为稳定应用模型

阶段 7 判断：

- `已确认`：该服务属于阶段 7 必要服务
- `已确认`：它只承接阶段 5 冻结后的只读面
- `不建议`：继续在本阶段加入 reporting 列表、搜索、过滤或快照存储入口

## 三、当前 API 契约面判断

### 3.1 `market` 契约面

当前入口包括：

- `GET /api/market/price-history`
- `GET /api/market/trading-calendar`
- `POST /api/market/sync-price-history`
- `POST /api/market/sync-trading-calendar`
- `GET /api/market/sync-status/{dataset}`

阶段 7 判断：

- `已确认`：当前市场数据契约面可继续保留
- `不建议`：继续新增更复杂的筛选、聚合或页面专用返回结构

### 3.2 `factors` 契约面

当前入口包括：

- `GET /api/factors/definitions`
- `GET /api/factors/pool-members`
- `GET /api/factors/summary`
- `GET /api/factors/cross-section-summary`
- `GET /api/factors/values`
- `GET /api/factors/top-n`

阶段 7 判断：

- `已确认`：因子只读与研究查询面属于阶段 7 闭环的一部分
- `已确认`：当前范围已经足够覆盖最小研究访问面
- `不建议`：继续新增导出接口、批量任务接口或前端专用视图契约

### 3.3 `backtest` 契约面

当前入口包括：

- `POST /api/backtest/run-once`
- `POST /api/backtest/run-batch`

阶段 7 判断：

- `已确认`：这两条接口构成当前最小执行面
- `已确认`：批量接口的约束校验已经是阶段 4 收束成果的一部分
- `不建议`：继续新增任务查询列表、取消任务、异步提交等接口

### 3.4 `reporting` 契约面

当前入口包括：

- `GET /api/reporting/run-detail/{run_id}`
- `GET /api/reporting/batch-summary/{experiment_id}`

阶段 7 判断：

- `已确认`：当前 reporting 契约面继续完全受阶段 5 冻结基线约束
- `不建议`：继续新增 reporting 列表、搜索、过滤或页面专用聚合接口

## 四、`http_adapter` 边界判断

当前 `http_adapter` 的职责可收束为：

- 将 `RouteDefinition` 绑定到最小 HTTP 访问面
- 处理 GET query / POST body 的最小参数装配
- 将 `DispatchError` 稳定映射为 HTTP 错误响应
- 对缺失资源返回 `404 {"detail":"resource not found"}`

阶段 7 判断：

- `已确认`：`http_adapter` 属于阶段 7 必要访问层
- `已确认`：当前目标是保持其作为“最小 stdlib adapter”稳定工作
- `不建议`：继续在本阶段扩成完整 Web 框架替代层、认证层或中间件系统

## 五、阶段 7 明确保留的最小闭环

阶段 7 当前应保留的最小闭环为：

1. `market`：读取与最小同步状态
2. `factors`：定义、运行结果读取与基础排序
3. `backtest`：单次执行与批量执行
4. `reporting`：run detail 与 batch summary 只读查询
5. `http_adapter`：最小 HTTP 暴露与错误语义映射
6. `run_formal_verifications.py`：统一阶段 7 回归入口

## 六、阶段 7 当前不建议继续扩的方向

- 不继续扩 `reporting` route 面
- 不继续扩报告快照相关 API 或服务入口
- 不继续扩前端专用契约结构
- 不继续扩异步任务、队列、取消、重试类接口
- 不继续扩 AI 分析任务或 AI 结果接口
- 不继续扩认证、权限、租户或会话语义

## 七、阶段判断

- `已确认`：当前 `app/services` 与 `app/api` 已足以支撑阶段 7 的最小本地量化服务闭环。
- `已确认`：下一步更适合做“职责边界收束”和“契约面收束”，而不是继续加新接口或新能力。
- `基于当前上下文推断`：若后续要继续进入代码收束，优先顺序应是 `services -> api -> http_adapter`，而不是反过来从页面或 AI 入口开始。
