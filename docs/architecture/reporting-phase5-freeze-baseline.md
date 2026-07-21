# Reporting 阶段 5 冻结基线
时间：`2026-07-04`

## 一、文档定位

- `已确认`：本文档用于把当前 `阶段 5：报告层（reporting）` 的已完成成果固化为阶段性冻结基线。
- `已确认`：本文档不新增生产需求，只整理当前已经落地的读取面、契约面和验证面。
- `已确认`：后续若继续修改 reporting，默认先以本文档为对照基线评估是否越界。

## 二、当前冻结范围

当前冻结基线由以下三份文档共同组成：

- `docs/architecture/reporting-batch-summary-field-boundaries.md`
- `docs/architecture/reporting-readonly-route-contract.md`
- `docs/verification/reporting-verification-baseline.md`

三份文档分别覆盖：

- 字段边界
- 只读路由契约
- 三层验证基线

## 三、当前已确认能力边界

### 3.1 字段面

当前 `batch-summary` 已冻结的失败聚合字段包括：

- `failure_type_counts`
- `failure_stage_counts`
- `failure_code_counts`

当前不继续新增：

- `failure_source_counts`
- `expected_status_counts`
- `result_status_counts`

### 3.2 路由面

当前 reporting 只读路由冻结为：

- `GET /api/reporting/run-detail/{run_id}`
- `GET /api/reporting/batch-summary/{experiment_id}`

当前不继续新增：

- reporting 列表接口
- reporting 搜索/过滤 query 参数
- route 层字段重组
- 前端页面契约专用结构

### 3.3 验证面

当前 reporting 已冻结的最小验证组合为：

- `python scripts\smoke_test_formal_services.py`
- `python scripts\smoke_test_formal_api.py`
- `python scripts\smoke_test_formal_http_adapter.py`
- `python scripts\run_formal_verifications.py`

其中已确认覆盖：

- run detail 可读
- batch summary 可读
- `failure_type_counts` 透出
- `failure_stage_counts` 透出
- `failure_code_counts` 透出
- 缺失资源 `404` / `None` 语义

## 四、冻结后默认工作方式

在没有新需求前，默认按以下方式理解当前 reporting：

- 字段范围以字段边界文档为准
- 路由语义以只读契约文档为准
- 回归范围以验证基线文档为准

若只是做日常回归，建议顺序：

- `python scripts\smoke_test_formal_services.py`
- `python scripts\smoke_test_formal_api.py`
- `python scripts\smoke_test_formal_http_adapter.py`
- `python scripts\run_formal_verifications.py`

## 五、允许解冻的触发条件

只有出现以下情况之一，才建议解除当前冻结基线：

- 用户明确提出新的 reporting 消费需求
- 需要新增报告存储或报告模板边界
- 前端真实接入需要更细的只读契约说明
- 现有 smoke 暴露出当前字段/契约不足

如果没有以上触发条件，默认不继续扩 reporting 读取面。

## 六、当前止步判断

- `已确认`：截至 Batch 60，阶段 5 reporting 已具备可用的字段边界、只读契约和三层验证基线。
- `已确认`：当前最合理的做法是把它视作阶段性冻结基线，而不是继续细碎扩展代码面。
- `基于当前上下文推断`：下一步若继续开发，更适合切到 `阶段 6：报告存储与模板边界`，而不是继续停留在阶段 5 扩读取细节。
