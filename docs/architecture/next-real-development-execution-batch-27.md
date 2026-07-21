# 下一批真实开发执行记录（Batch 27）

时间：`2026-07-02`

## 本批目标

继续沿着 factor 只读查询补两类最小一致性验证：

- `summary / cross-section-summary` 在不同 `trade_date` 组合下的显式空结果一致性
- `pool-members` 在 `date=None` 与显式日期输入下的默认行为验证

## 本批实际落地

### 1. 扩展默认日期行为验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- `pool-members` 在 `date=None` 时返回当前默认股票池成员
- `cross-section-summary` 在 `date=None` 时返回与默认股票池一致的 `symbol` 集合
- 上述行为在 services / API / HTTP 三层一致

### 2. 扩展不同 trade_date 下的空结果一致性验证

新增验证：

- 单标的 `summary` 在已知 `symbol` 但无对应 `trade_date` 结果时返回空列表
- `cross-section-summary` 在已知股票池但无对应 `trade_date` 结果时，保留股票池 `symbol` 集合但每只股票的 `rows` 为空
- 上述行为在 services / API / HTTP 三层一致

## 本批为何这样切

这一步仍然保持保守策略：

- 不扩新接口
- 不改 service / store 行为
- 仅把默认日期语义和空结果语义补成显式回归验证

## 下一步建议

1. 若继续保守推进，可补 `summary` / `cross-section-summary` 在 `factor_ids` 过滤与空 `trade_date` 场景组合下的验证
2. 或补 `top-n` 在 `date` 变化后的研究侧联动验证
3. 暂不进入前端与 AI 侧扩展
