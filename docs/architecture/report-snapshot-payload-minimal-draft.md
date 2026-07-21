# 报告快照最小字段草案
时间：`2026-07-04`

## 一、文档定位

- `已确认`：本文档用于在 `阶段 6：报告存储与模板边界` 中，进一步收窄 `snapshot_payload` 的最小结构草案。
- `已确认`：本文档只做字段草案整理，不新增 dataclass、schema、repository 或 route。
- `已确认`：本文档以前置文档 `docs/architecture/report-object-and-template-boundaries.md` 为准。

## 二、为什么还需要这一层草案

在上一份边界文档中，已经确认报告快照层的最小公共字段包括：

- `report_id`
- `report_type`
- `source_kind`
- `source_id`
- `title`
- `summary_text`
- `snapshot_payload`
- `created_at`

其中最容易失控的部分是 `snapshot_payload`。

如果不先收窄它的最小结构，后续一旦进入实现，很容易把：

- route 包裹层
- 页面展示细节
- 临时前端需求
- 任意附加字段

一起塞进快照正文，导致报告对象边界重新变模糊。

## 三、当前建议的最小公共骨架

无论哪一类报告快照，`snapshot_payload` 都建议先收敛为以下公共骨架：

- `headline`
- `key_stats`
- `body`
- `generated_from`

字段说明：

### 3.1 `headline`

用途：

- 放最小标题补充信息
- 适合作为导出或列表中的一眼摘要

建议内容：

- `title`
- `subtitle`
- `status`

边界：

- 只放简短抬头信息
- 不放大块正文

### 3.2 `key_stats`

用途：

- 放适合摘要透出的关键统计
- 便于模板层做摘要卡片或导出摘要区

建议内容：

- list 结构的键值对集合
- 每项至少包括：
  - `name`
  - `value`

可选补充：

- `unit`
- `display_value`

边界：

- 不要求穷举所有底层字段
- 只放真正有摘要价值的少量统计

### 3.3 `body`

用途：

- 放报告正文的核心结构化内容
- 这是 `snapshot_payload` 中最主要的部分

建议内容：

- list 结构的 section 集合
- 每个 section 最小包括：
  - `section_id`
  - `section_title`
  - `section_type`
  - `content`

边界：

- `section_type` 只描述内容形态，例如 `text`、`table`、`chart`、`json`
- 不在这里塞页面布局、栅格、颜色、折叠态等前端细节

### 3.4 `generated_from`

用途：

- 记录当前快照正文是从什么读取对象或来源对象整理而来
- 便于未来复盘和调试

建议内容：

- `source_kind`
- `source_id`
- `report_type`

可选补充：

- `generated_at`
- `generator_version`

边界：

- 这里只记录溯源信息
- 不等于完整审计日志

## 四、面向当前两类报告的最小映射建议

### 4.1 `backtest_run_detail` 报告快照

建议最小 `headline`：

- `title`：例如“回测运行明细报告”
- `subtitle`：可包含 `strategy_name`
- `status`

建议最小 `key_stats`：

- `benchmark`
- `start_date`
- `end_date`
- 若已有稳定 metrics，可挑少量核心指标进入摘要

建议最小 `body` section：

- `metrics` section
- `account_value_chart` section
- `trade_activity_chart` section
- `position_exposure_chart` section
- `yearly_return_chart` section

说明：

- 这里说的是“正文区块如何组织”
- 不是要求当前 route 或 dataclass 改结构

### 4.2 `batch_experiment_summary` 报告快照

建议最小 `headline`：

- `title`：例如“批次实验摘要报告”
- `subtitle`：可包含 `profile`
- `status`

建议最小 `key_stats`：

- `request_count`
- `success_count`
- `failure_count`

若已有稳定 failures 聚合结果，可补：

- `failure_type_counts`
- `failure_stage_counts`
- `failure_code_counts`

建议最小 `body` section：

- `rows` section
- `yearly_rows` section
- `failures` section
- `failure_counts` section

说明：

- `failure_counts` 可作为聚合区块存在
- 不要求把所有失败明细都提升成摘要字段

## 五、当前明确不建议放进 `snapshot_payload` 的内容

以下内容当前不建议进入最小草案：

- route 包裹层字段：`detail`、`summary`
- 前端布局字段：列宽、分栏、卡片顺序
- 纯 UI 状态：展开/折叠、分页、当前 tab
- 页面专用文案修饰字段
- 与报告事实无关的临时调试字段

原因：

- 这些内容容易让快照对象被页面实现绑死
- 当前阶段的重点是保存“报告事实”，不是保存“页面长相”

## 六、当前草案的刻意保守点

本草案刻意没有继续细化：

- `section.content` 的统一子 schema
- chart / table / text 的标准字段全集
- 不同 `report_type` 之间的强统一结构

原因：

- 当前还没有真实存储实现
- 当前也没有真实模板接入压力
- 现在把结构定得过细，反而容易过早架构化

## 七、下一步进入实现前至少还需确认的事

若后续真的进入快照实现，建议至少先补确认：

1. 首批支持哪些 `report_type`
2. `snapshot_payload` 是否允许按 `report_type` 有不同 section 内容
3. 是否需要单独保存导出产物元数据
4. 是否需要版本号或生成器版本字段

## 八、阶段判断

- `已确认`：当前最合理的做法，是把 `snapshot_payload` 先收窄到“公共骨架 + 按类型映射建议”这一层。
- `基于当前上下文推断`：在没有真实存储触发条件落地前，这份字段草案已经足够支撑后续是否进入实现的判断。