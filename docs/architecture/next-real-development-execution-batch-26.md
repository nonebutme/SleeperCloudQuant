# 下一批真实开发执行记录（Batch 26）

时间：`2026-07-02`

## 本批目标

继续沿着 factor 只读查询补两类最小一致性验证：

- `top-n` 同值时按 `symbol` 稳定排序
- `cross-section-summary` 在更多 `date` 输入下与 `pool-members` 保持一致

## 本批实际落地

### 1. 扩展 top-n 同值排序验证

- `app/runtime/demo_registry.py`
- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

新增最小 tie fixture：

- 通过共享 SQLite 额外写入 `tie_rank_factor`
- `000001.XSHE` 与 `600000.XSHG` 在同一 `trade_date` 下拥有相同因子值

新增验证：

- `descending=true` 时，同值结果仍按 `symbol ASC` 稳定排序
- `descending=false` 时，同值结果仍按 `symbol ASC` 稳定排序

### 2. 扩展更多日期下的 pool-members / cross-section-summary 一致性验证

最小 fake 股票池调整：

- `date=2020-01-01` -> `000001.XSHE`
- `date=2020-01-02` -> `000001.XSHE, 600000.XSHG`
- `date=2020-01-03` -> `600000.XSHG`

新增验证：

- `pool-members` 在更多日期下返回预期成员
- `cross-section-summary` 在相同日期下返回与股票池一致的 `symbol` 集合
- 上述行为在 services / API / HTTP 三层一致

## 本批为何这样切

这一步继续保持最小变更原则：

- 不扩新接口
- 不改正式排序逻辑
- 仅通过最小测试夹具与 fake 数据切换，把已存在语义补成显式回归验证

## 下一步建议

1. 若继续保守推进，可补 `summary` / `cross-section-summary` 在不同 `trade_date` 组合下的显式空结果一致性
2. 或补 `pool-members` 在 `date=None` 与显式日期输入下的默认行为验证
3. 暂不进入前端与 AI 侧扩展
