# 下一批真实开发执行记录（Batch 25）

时间：`2026-07-02`

## 本批目标

继续沿着 factor 只读查询补最小一致性验证：

- `factor top-n` 的排序稳定性与 `limit` 边界
- `factor values` 的日期作用域显式行数约束

## 本批实际落地

### 1. 扩展 factor values 日期作用域验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- 已落盘的精确 `start_date/end_date` 作用域能命中结果
- 不匹配的 `start_date/end_date` 作用域返回空列表
- 上述行为在 services / API / HTTP 三层一致

### 2. 扩展 factor top-n 排序与 limit 边界验证

新增验证：

- `descending=true` 时结果顺序符合因子值降序
- `descending=false` 时结果顺序符合因子值升序
- `limit=0` 时 service 层最小钳制为 1 条结果
- 不匹配的 `start_date/end_date` 作用域返回空排行
- 上述行为在 services / API / HTTP 三层一致

## 本批为何这样切

这一步仍然保持保守策略：

- 不扩新接口
- 不改 service / store 逻辑
- 仅把已存在行为补成显式回归验证，降低后续演进时的语义漂移风险

## 下一步建议

1. 若继续保守推进，可补 `top-n` 在同值场景下按 `symbol` 稳定排序的显式验证
2. 或补 `cross-section-summary` 与 `pool-members` 在更多日期输入下的一致性验证
3. 暂不进入前端与 AI 侧扩展
