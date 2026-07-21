# Reporting 验证基线
时间：`2026-07-04`

## 一、文档定位

- `已确认`：本文档描述当前 `reporting` 模块已经具备的最小验证基线。
- `已确认`：本文档面向阶段 5 `reporting`，覆盖 services / API / HTTP 三层当前已落地 smoke 范围。
- `已确认`：本文档只记录已落地验证，不把“应该验证但尚未实现”的内容写成已覆盖。

## 二、当前验证分层

当前 reporting 的验证基线分为三层：

- services 层：`scripts/smoke_test_formal_services.py`
- API 层：`scripts/smoke_test_formal_api.py`
- HTTP 层：`scripts/smoke_test_formal_http_adapter.py`

补充回归入口：

- `scripts/run_formal_verifications.py`

## 三、Services 层基线

当前已验证：

- `ReportingService.get_run_detail(run_id)` 可返回已落盘 run detail
- `ReportingService.get_batch_summary(experiment_id)` 可返回已落盘 batch summary
- reporting summary 能保留 runtime failure 的：
  - `failure_type`
  - `failure_stage`
  - `failure_code`
  - `failure_source`
- reporting summary 能保留 unexpected status failure 的：
  - `expected_status`
  - `result_status`
  - `status_transition`
- reporting summary 已验证以下聚合字段：
  - `failure_type_counts`
  - `failure_stage_counts`
  - `failure_code_counts`

当前已验证的代表性结果：

- runtime failure：
  - `failure_type_counts == {"runtime_error": 1}`
  - `failure_stage_counts == {"run_once": 1}`
  - `failure_code_counts == {"BACKTEST_RUN_ONCE_RUNTIME_ERROR": 1}`
- unexpected status：
  - `failure_type_counts == {"unexpected_status": 1}`
  - `failure_stage_counts == {"result_status_check": 1}`
  - `failure_code_counts == {"BACKTEST_UNEXPECTED_RESULT_STATUS": 1}`

当前未覆盖：

- `None` 结果下 services 层的显式空资源断言未单独做专门 smoke
- 失败明细中 `failure_source` 的聚合字段未验证，因为当前未提供对应聚合字段

## 四、API 层基线

当前已验证：

- `reporting_run_detail` route 可读取已存在 run detail
- `reporting_batch_summary` route 可读取已存在 batch summary
- API route 返回的 `summary` 中可稳定透出：
  - `failure_type_counts`
  - `failure_stage_counts`
  - `failure_code_counts`

当前已验证的代表性结果：

- 对手工 seed 的失败 batch，API route 可返回：
  - `{"runtime_error": 1, "unexpected_status": 1}`
  - `{"run_once": 1, "result_status_check": 1}`
  - `{"BACKTEST_RUN_ONCE_RUNTIME_ERROR": 1, "BACKTEST_UNEXPECTED_RESULT_STATUS": 1}`

当前边界说明：

- reporting route 在资源缺失时的 API shell 返回 `None` 行为已做专项 smoke 断言
- API 层当前没有 request model，因此不存在 reporting query 参数校验 smoke

## 五、HTTP 层基线

当前已验证：

- `GET /api/reporting/run-detail/{run_id}` 可返回 `200` 与 `detail`
- `GET /api/reporting/batch-summary/{experiment_id}` 可返回 `200` 与 `summary`
- HTTP JSON 响应中的 `summary` 可稳定透出：
  - `failure_type_counts`
  - `failure_stage_counts`
  - `failure_code_counts`

当前已验证的代表性结果：

- 对手工 seed 的失败 batch，HTTP JSON 可返回：
  - `summary.failure_type_counts == {"runtime_error": 1, "unexpected_status": 1}`
  - `summary.failure_stage_counts == {"result_status_check": 1, "run_once": 1}`
  - `summary.failure_code_counts == {"BACKTEST_RUN_ONCE_RUNTIME_ERROR": 1, "BACKTEST_UNEXPECTED_RESULT_STATUS": 1}`

当前未覆盖：

- reporting GET route 的 `Content-Type` 未做 reporting 专项断言，当前只由通用 HTTP adapter 语义覆盖

当前边界说明：

- reporting 两条 GET 路由的 `404 {"detail": "resource not found"}` 已做专项 HTTP smoke 断言

## 六、统一回归基线

当前已确认的 reporting 相关统一回归入口为：

- `python scripts\smoke_test_formal_services.py`
- `python scripts\smoke_test_formal_api.py`
- `python scripts\smoke_test_formal_http_adapter.py`
- `python scripts\run_formal_verifications.py`

说明：
当前 `run_formal_verifications.py` 并不会逐一直接调用 reporting 三个 smoke 脚本，但本项目最近批次已将 reporting 相关 smoke 作为阶段 5 交付验证的一部分显式执行。

## 七、当前基线使用建议

### 7.1 需要确认 reporting service 是否仍稳定

优先运行：

- `python scripts\smoke_test_formal_services.py`

### 7.2 需要确认 route / schema 透出是否仍稳定

优先运行：

- `python scripts\smoke_test_formal_api.py`

### 7.3 需要确认最终 HTTP JSON 读取面是否仍稳定

优先运行：

- `python scripts\smoke_test_formal_http_adapter.py`

### 7.4 需要做一轮阶段性交付回归

建议顺序：

- `python scripts\smoke_test_formal_services.py`
- `python scripts\smoke_test_formal_api.py`
- `python scripts\smoke_test_formal_http_adapter.py`
- `python scripts\run_formal_verifications.py`

## 八、阶段止步判断

- `已确认`：截至 Batch 60，reporting 已具备字段边界文档、只读路由契约文档和三层验证基线说明。
- `已确认`：当前 404 专项 smoke 已补齐，下一步更适合停在当前基线等待下一阶段需求，或只补极小的说明型整理。
- `基于当前上下文推断`：若没有新的消费面需求，阶段 5 reporting 已接近一个清晰可交付的止步点。
