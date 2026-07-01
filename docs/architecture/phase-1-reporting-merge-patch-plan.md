# phase-1-reporting-merge-patch-plan

## 1. 文档定位

- 目标：把 `reporting` 正式回收所需的逐文件 patch 计划写清楚。
- 范围：只覆盖 `reporting` 正式骨架回收。
- 状态：`已确认（逐文件 patch 计划层）`

## 2. 本计划对应的正式目标文件

- `reporting/run_results_reader.py`
- `reporting/replay_service.py`
- `reporting/batch_comparison_service.py`

## 3. 本计划对应的来源文件

- `reporting/phase1_store_protocols.py`
- `reporting/phase1_run_results_reader.py`
- `reporting/phase1_replay_service.py`
- `reporting/phase1_batch_comparison_service.py`

## 4. 文件级 patch 计划

### 4.1 `run_results_reader.py`

#### 当前目标

- 让正式 reader 文件承载 phase-1 已验证通过的单次结果聚合逻辑。

#### 应替换/新增内容

- 保留并对齐：
  - `BacktestRunDetail`
  - `RunResultsReader`

- 正式纳入以下逻辑：
  - `get_run_detail`
  - `build_account_value_chart`
  - `build_trade_activity_chart`
  - `build_position_exposure_chart`
  - `build_yearly_return_chart`

- 同时纳入配套私有函数：
  - `_ensure_account_snapshot_times`
  - `_coerce_float`
  - `_parse_sortable_time`
  - `_fill_derived_metrics`
  - `_select_preferred_account_rows`
  - `_account_row_priority`

- 在正式文件中明确 store 依赖方式：
  - 可直接引入最小协议定义
  - 或在文件内内联最小依赖说明

#### 当前阶段不引入

- API 层
- 页面层
- fake store 资产

#### 合并来源

- `reporting/phase1_store_protocols.py`
- `reporting/phase1_run_results_reader.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- fake reporting 链路仍通过

### 4.2 `replay_service.py`

#### 当前目标

- 让正式 replay 文件承载 phase-1 已验证的回放数据接线能力。

#### 应替换/新增内容

- 保留并对齐：
  - `BacktestReplayDetail`
  - `ReplayService`

- 正式纳入以下逻辑：
  - `list_replay_symbols`
  - `build_trade_replay`
  - `_resolve_start_date`
  - `_resolve_end_date`
  - `_normalize_trade_row`
  - `_normalize_price_rows`

- 同时纳入配套私有函数：
  - `_pick_price_date`
  - `_parse_date`
  - `_coerce_float`

- 正式文件中明确最小 repository 协议依赖

#### 当前阶段不引入

- 实际 Web 回放页面
- 前端可视化层

#### 合并来源

- `reporting/phase1_replay_service.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- 静态导入 replay 相关类型不报错

### 4.3 `batch_comparison_service.py`

#### 当前目标

- 让正式 batch comparison 文件承载 phase-1 已验证的批量对比读侧逻辑。

#### 应替换/新增内容

- 保留并对齐：
  - `BatchExperimentRow`
  - `BatchExperimentSummary`
  - `BatchComparisonService`

- 正式纳入以下逻辑：
  - `summarize_experiment`
  - `_build_row`
  - `_build_yearly_rows`
  - `_index_metrics`
  - `_coerce_mapping`
  - `_coerce_sequence`
  - `_to_optional_text`
  - `_to_optional_int`
  - `_to_optional_float`

#### 当前阶段不引入

- 前端排序与展示层逻辑
- fake store 资产

#### 合并来源

- `reporting/phase1_batch_comparison_service.py`
- `reporting/phase1_store_protocols.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- fake reporting batch summary 仍通过

## 5. 推荐执行顺序

建议执行顺序固定为：

1. `run_results_reader.py`
2. `replay_service.py`
3. `batch_comparison_service.py`

原因：

- 先统一单次结果读侧主链路
- 再统一 replay 扩展
- 最后统一 batch comparison 扩展

## 6. 每一步执行后的检查点

每更新一个正式文件后，都应立即检查：

1. 文件是否能被导入
2. `scripts/run_phase1_verifications.py` 是否仍通过
3. 当前更新是否要求同步修改 `backtest_kernel`

若第 3 条发生，则说明 reporting 边界回流，应立即停止并重审边界。

## 7. 本轮不应一起处理的内容

以下内容本轮不应掺入：

- fake store 迁移
- `phase1.py` 聚合导出清理
- API 路由
- 页面/前端层
- 真实 backtest 结果表 schema 改造

## 8. 合并后的预期状态

当本轮完成后，应达到：

- 正式 `run_results_reader.py` 承载单次结果聚合逻辑
- 正式 `replay_service.py` 承载回放数据接线逻辑
- 正式 `batch_comparison_service.py` 承载批量对比读侧逻辑
- fake reporting 验证仍通过

## 9. 本计划执行后的下一步

完成 `reporting` 正式回收后，后续才建议进入：

- fake 资产迁移
- `phase1.py` 聚合导出清理
- `phase1_*` 实现层收尾删除或兼容保留
