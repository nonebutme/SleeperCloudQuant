# phase-1-file-candidate-confirmation-round-1-reporting

## 1. 文档定位

- 目标：对 `reporting` 在第一阶段最小拼接范围内的候选文件做逐文件确认。
- 依据：
  - `docs/architecture/reporting-minimum-spec.md`
  - `docs/architecture/phase-1-stitching-plan.md`
  - `docs/architecture/phase-1-file-candidate-confirmation-plan.md`
- 范围：本轮仅做候选归类，不执行代码拆解、拼接或 UI 实现。

## 2. 本轮检查来源

### 2.1 已检查仓库

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old`
- `D:\Dev-AI\Dev\projects\TradingAgents-CN-main`

### 2.2 本轮聚焦文件

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\backtest_results_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\backtest_replay_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\batch_backtest_analysis_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\stage_a_backtest_service.py`
- `D:\Dev-AI\Dev\projects\TradingAgents-CN-main\app\utils\report_exporter.py`
- `D:\Dev-AI\Dev\projects\TradingAgents-CN-main\app\routers\reports.py`

## 3. 最小能力回看

按当前已确认边界，`reporting` 第一阶段最小能力仅要求：

- 读取单次回测结果明细
- 输出指标、交易、持仓、账户、年度收益等查询结构
- 提供基础图表数据组织能力
- 为后续批量对比和回放预留接缝

本阶段不要求直接纳入：

- 通用富文本报告导出
- 面向 AI 分析任务的报告管理后台
- 完整 Web 报告路由系统
- 非回测场景的跨任务报告中心

## 4. 逐文件确认结论

### 4.1 直接采纳候选

#### 4.1.1 `core/services/backtest_results_service.py`

- 结论：`直接采纳候选`
- 判断依据：
  - 该文件就是回测结果读侧的核心聚合服务。
  - 已完整覆盖第一阶段 reporting 所需的最关键能力：
    - `get_run_detail`
    - `metrics / logs / trades / positions / accounts / yearly_returns` 聚合
    - 账户净值图、交易活跃图、仓位暴露图、年度收益图的数据构造
  - 职责集中，虽然依赖 `SqliteMetadataStore`，但没有明显混入 UI 页面耦合。
- 采纳方式建议：
  - 优先整体吸收其读侧聚合结构与图表数据组织方式。
  - 落地时只做仓储接口和模块路径适配。

### 4.2 修改后采纳候选

#### 4.2.1 `core/services/backtest_replay_service.py`

- 结论：`修改后采纳候选`
- 判断依据：
  - 该文件负责把结果明细与行情历史拼成交易回放数据集。
  - 它是 reporting 的自然扩展能力，但不是最小结果查询主链路的唯一阻塞项。
  - 当前实现依赖 `MarketDataRepository` 与具体 price-history 接口，需要与新项目 data-platform 接缝重新对齐。
- 采纳方式建议：
  - 保留“symbol 列表解析 + 回放窗口推导 + K 线数据归一化”的骨架。
  - 后续在 `reporting/replay` 子模块中单独落位，不建议和最小结果查询服务揉成一个文件。

#### 4.2.2 `core/services/batch_backtest_analysis_service.py`

- 结论：`修改后采纳候选`
- 判断依据：
  - 该文件承担“批量实验结果对比”这一 reporting 扩展面。
  - 数据结构清晰，包含排序、排名、年度收益拼接和失败记录汇总。
  - 但它依赖 `research_run` 元数据和批量实验上下文，不属于单次结果读侧最小闭环。
- 采纳方式建议：
  - 保留其“批量对比 summary”模型与排序逻辑。
  - 等单次回测结果查询稳定后，再以独立子服务方式接入。

### 4.3 参考保留

#### 4.3.1 `core/services/stage_a_backtest_service.py`

- 结论：`参考保留`
- 判断依据：
  - 该文件提供的是 Stage-A 页面摘要数据和 metric cards，偏页面聚合层。
  - 它对“最新运行摘要 / 最近运行列表 / 指标卡片”组织方式有参考价值。
  - 但本质更接近 dashboard view-model，而不是 reporting 核心读侧服务。

#### 4.3.2 `app/utils/report_exporter.py`

- 结论：`参考保留`
- 判断依据：
  - 该文件提供 Markdown / Word / PDF 导出能力，适用于 AI 分析报告导出场景。
  - 当前项目第一阶段 reporting 还未进入富文本导出主线。
  - 不适合作为回测结果 reporting 的直接拼接源，但后续“结果导出”阶段可参考其格式转换与依赖探测思路。

#### 4.3.3 `app/routers/reports.py`

- 结论：`参考保留`
- 判断依据：
  - 该文件本质是分析报告 API 路由，不是回测 reporting 核心逻辑。
  - 但它体现了报告列表、详情、查询条件、分页结构这些 API 组织思路。
  - 若未来需要做 Web 结果报告页，可参考其查询入口设计，而不应直接迁入。

## 5. 当前归类汇总

### 5.1 直接采纳候选

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\backtest_results_service.py`

### 5.2 修改后采纳候选

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\backtest_replay_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\batch_backtest_analysis_service.py`

### 5.3 参考保留

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\stage_a_backtest_service.py`
- `D:\Dev-AI\Dev\projects\TradingAgents-CN-main\app\utils\report_exporter.py`
- `D:\Dev-AI\Dev\projects\TradingAgents-CN-main\app\routers\reports.py`

## 6. 交叉说明

- `SleeperCloudQuant-old` 已经提供了较完整的“回测结果读侧”实现，因此是本轮 reporting 的主来源。
- `TradingAgents-CN-main` 更偏“分析报告管理 / 导出 / API 暴露”，与当前回测 reporting 主线并不完全同类。
- 当前判断是：
  - 第一阶段 reporting 应优先围绕 `backtest_results_service.py` 建最小结果查询闭环。
  - `replay` 和 `batch comparison` 作为第二层扩展接口保留接缝。
  - `export` 与 `reports API` 暂不纳入第一阶段最小拼接清单。

## 7. 下一步建议

- 若继续做逐文件候选确认，下一步可以进入：
  - `phase-1 candidate -> target module` 映射阶段
  - 或对 `backtest-kernel / data-platform / config-center / reporting` 四块做汇总交叉表
- 若继续深化 `reporting`，建议下一步改做：
  - 单次回测结果读侧接口清单
  - 图表数据结构统一草图
  - replay 与 batch-comparison 的独立模块边界说明

## 8. 状态标记

- 状态：`已确认（本轮候选归类层）`
- 未确认项：
  - 第一阶段是否需要立即暴露 Web API 层
  - 报表导出是否进入第一阶段
  - batch comparison 是否和 reporting 一起落地，还是后置到第二轮
