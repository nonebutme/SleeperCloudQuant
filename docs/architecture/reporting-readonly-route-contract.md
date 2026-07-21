# Reporting 只读路由契约
时间：`2026-07-04`

## 一、文档定位

- `已确认`：本文档描述当前 reporting 只读路由的最小契约。
- `已确认`：本文档只覆盖现有两条 GET 路由，不扩展新的 reporting endpoint。
- `已确认`：本文档以当前 `app/api/reporting.py`、`app/schemas/reporting.py` 和 `app/runtime/http_adapter.py` 的实装为准。

## 二、当前路由清单

当前 reporting 只读路由包括：

- `GET /api/reporting/run-detail/{run_id}`
- `GET /api/reporting/batch-summary/{experiment_id}`

这两条路由都使用路径参数，不使用 query string，也不接收 request body。

## 三、路由契约

### 3.1 `GET /api/reporting/run-detail/{run_id}`

用途：
读取单次回测 run 的明细视图。

路径参数：

- `run_id`：目标回测运行标识

200 响应包裹层：

- `detail`

`detail` 当前对应：

- `BacktestRunDetailModel`

当前已确认的核心字段包括：

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

404 语义：

- 当 `ReportingService.get_run_detail(run_id)` 返回 `None` 时，route handler 返回 `None`
- `dispatch_request()` 会统一转成：`404 {"detail": "resource not found"}`

边界：

- 当前只读已落盘明细，不额外补推断字段
- 当前不在该接口返回 batch 维度信息

### 3.2 `GET /api/reporting/batch-summary/{experiment_id}`

用途：
读取一个 batch experiment 的聚合摘要视图。

路径参数：

- `experiment_id`：目标批次实验标识

200 响应包裹层：

- `summary`

`summary` 当前对应：

- `BatchExperimentSummaryModel`

当前已确认的核心字段包括：

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

404 语义：

- 当 `ReportingService.get_batch_summary(experiment_id)` 返回 `None` 时，route handler 返回 `None`
- `dispatch_request()` 会统一转成：`404 {"detail": "resource not found"}`

边界：

- 当前只做读取，不接收 POST 更新
- 当前只消费已稳定存在的 failures 明细字段
- 当前不在该接口加入 AI 报告、模板渲染或前端专用重组字段

## 四、HTTP 层统一行为

当前 HTTP adapter 对 reporting 只读路由的统一行为为：

- 成功返回 `200`
- 资源缺失返回 `404 {"detail": "resource not found"}`
- `Content-Type` 为 `application/json; charset=utf-8`
- dataclass 响应会经 `_to_jsonable()` 递归转为普通 JSON 结构

说明：
reporting 这两条 GET 路由当前没有 request model，因此不存在 query 参数校验失败导致的 `400 invalid request parameters` 场景。

## 五、当前明确不做的事

- `已确认`：当前不新增 reporting 列表接口
- `已确认`：当前不新增 reporting 搜索/过滤 query 参数
- `已确认`：当前不在 route 层重写字段名或重组嵌套结构
- `已确认`：当前不引入版本化路由
- `已确认`：当前不把 reporting 只读契约扩展为前端页面契约

## 六、调用建议

### 6.1 需要单次回测细节

优先调用：

- `GET /api/reporting/run-detail/{run_id}`

### 6.2 需要批次聚合摘要

优先调用：

- `GET /api/reporting/batch-summary/{experiment_id}`

### 6.3 需要判断资源是否存在

当前应根据：

- `200`：资源存在
- `404 {"detail": "resource not found"}`：资源不存在或当前不可读

## 七、阶段止步判断

- `已确认`：截至 Batch 58，reporting 只读契约仍保持极小，只覆盖 run detail 与 batch summary 两条读取路径。
- `已确认`：下一步若继续推进，更适合围绕现有契约补说明或消费面整理，而不是立刻新增更多 reporting endpoint。
