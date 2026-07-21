# 下一批真实开发执行记录（Batch 28）

时间：`2026-07-02`

## 本批目标

继续沿着 factor 只读查询补两类组合边界验证：

- `summary / cross-section-summary` 在 `factor_ids` 过滤与空 `trade_date` 场景组合下的验证
- `pool-members / cross-section-summary` 在更多默认参数组合下的边界一致性验证

## 本批实际落地

### 1. 扩展空 trade_date 与 factor_ids 组合验证

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增验证：

- 单标的 `summary` 在空 `trade_date` 结果下，即使指定 `factor_ids` 过滤，仍返回空列表
- `cross-section-summary` 在空 `trade_date` 结果下，即使指定 `factor_ids` 过滤，仍保留股票池 `symbol` 集合且所有 `rows` 为空
- 上述行为在 services / API / HTTP 三层一致

### 2. 扩展默认参数组合一致性验证

新增验证：

- `pool-members` 在未知股票池且 `date=None` 时返回空列表
- `cross-section-summary` 在未知股票池且 `date=None` 时返回空列表
- 上述行为与显式 `date` 版本保持一致

## 本批为何这样切

这一步仍然保持最小变更原则：

- 不扩新接口
- 不改 service / store 逻辑
- 仅把组合边界语义补成显式回归验证，避免后续查询扩展时产生默认行为漂移

## 下一步建议

1. 若继续保守推进，可补 `top-n` 查询在默认 / 空参数解析下的边界一致性验证
2. 或补 `factor values` 在更多默认日期与未知股票池联动场景下的显式空结果验证
3. 暂不进入前端与 AI 侧扩展
