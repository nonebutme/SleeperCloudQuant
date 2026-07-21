# Reporting Batch Summary 字段边界
时间：`2026-07-04`

## 一、文档定位

- `已确认`：本文档只描述当前 `GET /api/reporting/batch-summary/{experiment_id}` 的已落地字段边界。
- `已确认`：本文档面向阶段 5 `reporting`，用于约束读取面，不定义新的 backtest-kernel 生产字段。
- `已确认`：若后续字段扩展与本文档冲突，以新增批次文档和代码实装为准，再回写本文档。

## 二、当前返回层级

当前 reporting batch summary 的最小响应层级为：

- `summary.experiment_id`
- `summary.profile`
- `summary.status`
- `summary.started_at`
- `summary.finished_at`
- `summary.request_count`
- `summary.success_count`
- `summary.failure_count`
- `summary.rows`
- `summary.yearly_rows`
- `summary.failures`
- `summary.failure_type_counts`
- `summary.failure_stage_counts`
- `summary.failure_code_counts`

说明：
`summary` 由 `BatchSummaryResponse.summary` 包裹，当前 API/HTTP 层不再额外重组字段。

## 三、字段分层

### 3.1 基础批次元信息

用于标识一个 batch experiment 的整体状态：

- `experiment_id`
- `profile`
- `status`
- `started_at`
- `finished_at`
- `request_count`
- `success_count`
- `failure_count`

边界：
这些字段表达“批次整体发生了什么”，不表达单次 run 的详细失败语义。

### 3.2 成功结果比较视图

用于比较已落盘 run 的表现：

- `rows`
- `yearly_rows`

边界：
- `rows` 主要服务于 run 间横向比较与排序。
- `yearly_rows` 主要服务于逐年收益读取。
- 这两个字段不负责承载 failures 聚合语义。

### 3.3 失败明细视图

用于保留原始失败摘要明细：

- `failures`

当前已确认 failures 明细中已经稳定存在且可被 reporting 直接消费的核心字段包括：

- `run_id`
- `failure_type`
- `failure_stage`
- `failure_code`
- `failure_source`
- `expected_status`
- `result_status`
- `status_transition`
- `error_message`

边界：
- `failures` 是明细层，不负责排序或聚合统计的最终读取便利性。
- 若调用方只需要机器可读计数，优先读取对应 `*_counts` 字段，而不是每次手扫 `failures`。

### 3.4 失败聚合视图

用于对 failures 明细做稳定、轻量的读取聚合：

- `failure_type_counts`
- `failure_stage_counts`
- `failure_code_counts`

当前语义分别是：

- `failure_type_counts`：按 `failure_type` 聚合计数
- `failure_stage_counts`：按 `failure_stage` 聚合计数
- `failure_code_counts`：按 `failure_code` 聚合计数

当前实现边界：

- 只统计已有且非空的对应字段
- 输出为 `dict[str, int]`
- 按 key 排序，降低展示与断言波动
- 不补推断值，不生成缺失字段的默认分类

## 四、当前明确不做的事

- `已确认`：当前不继续新增 `failure_source_counts`
- `已确认`：当前不继续新增 `expected_status_counts` / `result_status_counts`
- `已确认`：当前不把 reporting summary 扩展为完整报告模板系统
- `已确认`：当前不在 reporting 层引入 AI 解释字段
- `已确认`：当前不为前端展示专门改写数据结构

## 五、读取建议

### 5.1 调用方只关心是否有失败

优先读取：

- `failure_count`
- `status`

### 5.2 调用方只关心失败分类分布

优先读取：

- `failure_type_counts`
- `failure_stage_counts`
- `failure_code_counts`

### 5.3 调用方需要失败上下文

优先读取：

- `failures`

必要时再结合：

- `failure_type_counts`
- `failure_stage_counts`
- `failure_code_counts`

### 5.4 调用方需要比较成功 run 表现

优先读取：

- `rows`
- `yearly_rows`

## 六、阶段止步判断

- `已确认`：截至 Batch 56，阶段 5 reporting 在 failures 聚合侧已经覆盖 `type / stage / code` 三个核心机器可读字段。
- `已确认`：下一步更适合转向字段边界文档化、只读 schema/API 说明或消费面整理，而不是继续无限制增加新的同级 `*_counts` 字段。
- `基于当前上下文推断`：除非后续出现明确消费痛点，否则当前不建议再继续扩 failures 聚合种类。
