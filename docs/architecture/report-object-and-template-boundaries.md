# 报告对象与模板边界
时间：`2026-07-04`

## 一、文档定位

- `已确认`：本文档用于定义 `阶段 6：报告存储与模板边界` 的最小讨论起点。
- `已确认`：本文档只做对象边界与分层说明，不新增生产代码、不修改现有 reporting route contract。
- `已确认`：本文档以当前 `domain/report/models.py`、reporting 冻结基线文档和只读契约文档为基础整理。

## 二、为什么现在进入这一步

截至 `Batch 61`，`阶段 5：报告层（reporting）` 已经形成阶段性冻结基线：

- run detail 可读
- batch summary 可读
- failures 聚合字段已冻结到当前层级
- route contract 与验证基线已清晰

因此，下一步更适合先回答两个边界问题：

1. 报告在系统里应该被当成什么对象
2. 哪些内容属于可保存的报告快照，哪些内容只属于展示模板

## 三、当前已存在的只读报告对象

基于当前代码，reporting 已经存在两类只读对象：

### 3.1 `BacktestRunDetailModel`

当前字段：

- `run_id`
- `strategy_name`
- `status`
- `benchmark`
- `start_date`
- `end_date`
- `metrics`
- `account_value_chart`
- `trade_activity_chart`
- `position_exposure_chart`
- `yearly_return_chart`

当前定位：

- 更接近“单次回测运行明细对象”
- 适合做运行详情读取
- 当前还不等同于“可长期沉淀的一份报告快照”

### 3.2 `BatchExperimentSummaryModel`

当前字段：

- `experiment_id`
- `profile`
- `status`
- `started_at`
- `finished_at`
- `request_count`
- `success_count`
- `failure_count`
- `rows`
- `yearly_rows`
- `failures`
- `failure_type_counts`
- `failure_stage_counts`
- `failure_code_counts`

当前定位：

- 更接近“批次实验聚合读取对象”
- 适合做 batch summary 查询与对比
- 当前还不等同于“模板化报告对象”

## 四、建议区分的三个层次

### 4.1 读取对象层

用途：

- 服务层 / route 层直接返回当前已落盘数据

当前对应：

- `BacktestRunDetailModel`
- `BatchExperimentSummaryModel`

边界：

- 优先忠实反映现有数据结构
- 不要求具备稳定导出、版本留痕、模板渲染语义

### 4.2 报告快照层

用途：

- 保存“某一时刻生成出来的一份固定报告结果”
- 便于后续历史查看、版本对比、导出、回放

建议最小公共字段：

- `report_id`
- `report_type`
- `source_kind`
- `source_id`
- `title`
- `summary_text`
- `snapshot_payload`
- `created_at`

字段说明：

- `report_id`：报告快照唯一标识
- `report_type`：例如 `backtest_run_detail`、`batch_experiment_summary`
- `source_kind`：来源对象类型，例如 `run`、`batch_experiment`
- `source_id`：来源对象标识，例如 `run_id`、`experiment_id`
- `title`：面向展示或导出的最小标题
- `summary_text`：允许为空的最小摘要文本
- `snapshot_payload`：该次快照保存的结构化正文载荷
- `created_at`：快照生成时间

当前边界判断：

- `已确认`：这是一份建议中的最小对象边界，不代表当前代码已实现
- `已确认`：当前不在本批引入新的 dataclass、repository 或 storage schema

### 4.3 模板层

用途：

- 决定报告如何展示、如何排版、如何组织标题与区块

建议只放展示规则，不放业务事实字段：

- 页面区块顺序
- 区块标题文案
- 表格 / 图表 / 文本的展示方式
- 默认展开或折叠规则
- 导出格式差异配置

当前边界：

- 模板层不应反向定义领域事实
- 模板层不应成为 route contract 的替代物
- 模板层不应要求修改当前阶段 5 的只读字段面

## 五、哪些内容建议进入快照存储

基于当前上下文，建议优先进入快照层的内容包括：

- 报告身份字段：`report_id`、`report_type`
- 来源关联字段：`source_kind`、`source_id`
- 最小展示字段：`title`、`summary_text`
- 生成时刻字段：`created_at`
- 一份固定结构的 `snapshot_payload`

其中 `snapshot_payload` 对当前 reporting 来说，建议优先容纳：

- run detail 视图的核心正文
- batch summary 视图的核心正文
- 当时已经生成完成的 failures 聚合结果

原因：

- 这些内容属于“那一刻的报告结果”
- 以后即使底层读取对象继续演化，也能保留当时导出的稳定版本

## 六、哪些内容暂不进入快照公共字段

当前不建议进入快照公共字段的内容包括：

- 前端页面专用布局字段
- route 层包裹字段名，例如 `detail`、`summary`
- UI 层交互状态，例如折叠、分页、选中态
- 只服务某一版页面的展示性文案

这些内容更适合作为：

- 模板配置
- 前端局部状态
- 导出器内部规则

而不是报告对象本身的公共边界。

## 七、当前建议的最小推进顺序

### 7.1 先定义对象边界

本批先完成：

- 把“读取对象”与“报告快照对象”区分开
- 把“报告快照对象”与“模板层”区分开

### 7.2 再决定是否需要真实存储

只有在出现以下情况之一时，才建议继续进入存储实现：

- 需要历史版本留痕
- 需要导出固定报告
- 需要多次查看同一版报告结果
- 需要与前端真实模板接入

### 7.3 当前明确不做

- `已确认`：本批不新增报告快照 repository
- `已确认`：本批不新增报告模板引擎
- `已确认`：本批不改现有 reporting service / api / schema
- `已确认`：本批不把当前读取对象直接升格为正式快照模型实现

## 八、阶段判断

- `已确认`：当前更适合先把报告对象和模板边界说清，再决定是否进入快照存储实现。
- `基于当前上下文推断`：如果下一步继续推进，最小可行方向不是先写代码，而是先补一份“报告快照最小字段草案”或“报告快照存储触发条件”文档。