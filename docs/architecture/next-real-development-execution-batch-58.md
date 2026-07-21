# 下一批真实开发执行记录（Batch 58）
时间：`2026-07-04`

## 本批目标

继续按顺序推进 `阶段 5：报告层（reporting）`，在字段边界文档化之后，再补一层 route 级只读契约说明：

- 明确两条 reporting GET 路由
- 明确路径参数与 200 包裹层
- 明确 404 统一语义
- 保持最小变更，不改生产代码

## 本批实际落地

### 1. 新增 reporting 只读路由契约文档

- `docs/architecture/reporting-readonly-route-contract.md`

本批把当前 reporting 只读路由的契约整理为独立文档，覆盖：

- `GET /api/reporting/run-detail/{run_id}`
- `GET /api/reporting/batch-summary/{experiment_id}`

### 2. 明确包裹层与缺失资源语义

本批正式写清：

- run detail 的 200 包裹层为 `detail`
- batch summary 的 200 包裹层为 `summary`
- route handler 返回 `None` 时，HTTP 层统一转成 `404 {"detail": "resource not found"}`

### 3. 明确当前 route 边界

本批写清当前明确不做的事：

- 不新增 reporting 列表接口
- 不加 query 参数过滤
- 不做 route 层字段重组
- 不扩展为前端页面契约

## 本批为何这样切

这一步仍然延续阶段 5 的保守节奏：在不扩 API 面积的前提下，把已经存在的读取契约文档化。这样后续无论是继续做说明、接前端，还是补验证，都会更稳。

## 验证结果

已完成验证：

- 读取并复核 `app/api/reporting.py`
- 读取并复核 `app/schemas/reporting.py`
- 读取并复核 `app/runtime/http_adapter.py`
- `git diff --check -- docs/architecture/reporting-readonly-route-contract.md docs/architecture/next-real-development-execution-batch-58.md`

说明：本批仅新增文档，不涉及生产代码与 smoke 逻辑变更。

## 下一步建议

1. `[阶段 5：报告层（reporting）]` 如果继续开发，更适合补一份 reporting 验证基线说明，整理 services/API/HTTP 三层当前已覆盖的 smoke 范围。
2. `[阶段 5：报告层（reporting）]` 如果继续保持最小变更，也可以暂停代码推进，先以字段边界文档和路由契约文档作为当前 reporting 基线。
