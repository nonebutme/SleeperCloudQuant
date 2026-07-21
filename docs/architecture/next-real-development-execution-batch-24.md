# 下一批真实开发执行记录（Batch 24）

时间：`2026-07-02`

## 本批目标

沿着已落地的 factor 只读查询，继续补两类保守型验证：

- `date` 参数切换股票池成员的显式验证
- `factor values / top-n` 的空结果边界一致性验证

## 本批实际落地

### 1. 扩展股票池成员日期切换验证

- `app/runtime/demo_registry.py`
- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

最小 fake 数据调整：

- `000300.XSHG` 在 `date=2020-01-01` 时仅返回 `000001.XSHE`
- 其他已知日期继续返回 `000001.XSHE, 600000.XSHG`

新增验证：

- pool-members 在不同 `date` 下返回不同成员集
- cross-section-summary 在不同 `date` 下返回与股票池一致的 `symbol` 集合

### 2. 扩展 factor values / top-n 空结果验证

新增验证：

- 未知 `factor_id` 的 factor values 返回空列表
- 未知 `symbol` 的 factor values 返回空列表
- 未知 `factor_id` 的 top-n 返回空排行
- 未知 `trade_date` 的 top-n 返回空排行
- 上述行为在 services / API / HTTP 三层保持一致

## 本批为何这样切

这一步仍然保持最小变更原则：

- 不扩新接口
- 不改正式 service 协议
- 仅通过最小 fake 数据切换与显式回归验证，补齐日期维度和空结果边界

## 下一步建议

1. 若继续保守推进，可补 `factor top-n` 的排序稳定性与 limit 边界验证
2. 或补 `factor values` 在不同日期区间下的显式行数约束验证
3. 暂不进入前端与 AI 侧扩展
