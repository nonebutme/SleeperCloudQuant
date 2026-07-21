# 报告快照首批 report_type 范围
时间：`2026-07-04`

## 一、文档定位

- `已确认`：本文档用于收窄 `阶段 6：报告存储与模板边界` 下，未来如果进入快照实现时的首批 `report_type` 范围。
- `已确认`：本文档只定义范围边界，不新增 dataclass、repository、schema、service 或 route。
- `已确认`：本文档以前置文档 `report-object-and-template-boundaries.md`、`report-snapshot-payload-minimal-draft.md`、`report-snapshot-implementation-gate-review.md` 为依据。

## 二、为什么需要先收窄范围

当前已经确认：

- 暂不进入快照存储实现
- 但如果未来要进入实现，不能从“所有可能的报告类型”一起开始
- 首批实现范围越宽，越容易把阶段 6 从边界澄清推成过早架构化

因此，先把首批可能支持的 `report_type` 收窄，是当前最小且合理的下一步。

## 三、当前建议纳入首批范围的 report_type

### 3.1 `backtest_run_detail`

纳入理由：

- 已有稳定读取对象：`BacktestRunDetailModel`
- 已有稳定 route contract：`GET /api/reporting/run-detail/{run_id}`
- 已有相对明确的正文映射候选：
  - `metrics`
  - `account_value_chart`
  - `trade_activity_chart`
  - `position_exposure_chart`
  - `yearly_return_chart`

判断：

- `已确认`：这是当前最适合进入首批范围的候选之一

### 3.2 `batch_experiment_summary`

纳入理由：

- 已有稳定读取对象：`BatchExperimentSummaryModel`
- 已有稳定 route contract：`GET /api/reporting/batch-summary/{experiment_id}`
- 已有已冻结的 failures 聚合字段：
  - `failure_type_counts`
  - `failure_stage_counts`
  - `failure_code_counts`
- 已有相对明确的正文映射候选：
  - `rows`
  - `yearly_rows`
  - `failures`
  - `failure_counts`

判断：

- `已确认`：这是当前最适合进入首批范围的候选之一

## 四、当前明确不纳入首批范围的 report_type

### 4.1 AI 报告类 report_type

例如：

- 单股 AI 分析报告
- 多来源聚合的研究报告
- 模板化 AI 导出报告

当前不纳入理由：

- `已确认`：当前阶段没有推进 AI 报告实现主线
- `已确认`：当前也没有稳定的 AI 报告只读对象与契约基线
- `基于当前上下文推断`：如果现在把 AI 报告一起纳入，会明显扩大阶段 6 范围

### 4.2 前端页面专用报告类型

例如：

- 页面聚合卡片专用对象
- 某个列表页或仪表板专用的轻量报告对象

当前不纳入理由：

- `已确认`：本轮范围明确不碰前端
- `已确认`：当前阶段不把页面契约当成快照对象边界

### 4.3 导出专用衍生 report_type

例如：

- PDF-only report
- Markdown-only report
- 带固定排版模板的导出版报告

当前不纳入理由：

- `待确认`：当前并没有真实导出需求输入
- `已确认`：导出格式差异目前应留在模板层或未来导出层处理

## 五、当前建议的首批范围边界

如果未来真的进入快照实现，建议首批只考虑：

- `backtest_run_detail`
- `batch_experiment_summary`

并保持：

- 不同时引入 AI 报告
- 不同时引入前端页面专用对象
- 不同时引入导出专用变体类型

## 六、为什么只收窄到这两个

原因不是它们最终一定就是全部，而是它们当前具备三项优势：

1. 已有稳定读取对象
2. 已有稳定 route contract 与验证基线
3. 已有初步的 `snapshot_payload` 映射建议

在当前上下文里，这两个类型是最接近“若将来要做，也应先从这里开始”的最小集合。

## 七、仍待后续确认的点

即使首批范围先收窄到这两个，后续若进入实现，仍需确认：

- 两个 `report_type` 是否共用完全一致的快照持久化骨架
- 是否需要版本号
- 是否需要导出元数据
- 是否需要生成器版本字段
- 是否允许 `body.section.content` 按类型保留差异

## 八、阶段判断

- `已确认`：当前最合理的范围压缩结果，是把首批 `report_type` 暂时收窄到 `backtest_run_detail` 与 `batch_experiment_summary`。
- `基于当前上下文推断`：在没有真实触发条件前，这份范围说明足够支持后续再次评估是否进入实现。