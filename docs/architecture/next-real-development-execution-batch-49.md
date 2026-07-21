# 下一批真实开发执行记录（Batch 49）
时间：`2026-07-03`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的最小收口，在既有 batch failures 摘要增强与 batch 输入一致性约束基础上，再完成两项小步增强：

- 为 `unexpected_status` 类型 failure 增加对照字段 `expected_status`
- 为 `run-batch` 输入补齐 `end_date` 一致性约束

## 本批实际落地

### 1. 为 `unexpected_status` 增加 `expected_status`

- `app/services/batch_research_service.py`

本批继续只在 `unexpected_status` 对应的 batch failure 摘要上补一项最小字段：

- `expected_status = "completed"`

它和上一批新增的 `result_status` 形成一对最小的机器可读对照值，使调用方无需解析错误文案，也能直接知道“期望状态”和“实际状态”。

### 2. 为 run-batch 增加 `end_date` 一致性约束

- `app/schemas/backtest.py`

本批在 `start_date` 之后，继续补齐时间窗的另一端：

- 当同一批 `runs` 中存在不同 `end_date` 时，抛出 `ValueError("batch end_date values must be consistent")`

这一步仍然停留在 payload 校验层，不下沉到更深服务层，继续保持最小修改边界。

### 3. 补齐最小 smoke 验证闭环

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

本批补齐两类验证：

- services / reporting 链路中 `unexpected_status.expected_status` 的透传验证
- API / HTTP 层对 `end_date` 不一致输入的拒绝验证

## 本批为何这样切

这一步仍然符合 `阶段 4：回测内核（backtest-kernel）` 的保守推进方式：

- 没有新增领域对象
- 没有扩展 reporting 对外协议
- 没有改变回测执行流程

选择 `expected_status` 与 `end_date`，是因为它们都满足：

- 影响面小
- 语义明确
- 可以直接复用现有 smoke 与 formal verifications 验证闭环

## 验证结果

已通过：
- `python scripts/smoke_test_formal_services.py`
- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

另已通过：
- `git diff --check -- app/services/batch_research_service.py app/schemas/backtest.py scripts/smoke_test_formal_services.py scripts/smoke_test_formal_api.py scripts/smoke_test_formal_http_adapter.py`

说明：当前线程内 `apply_patch`、`rg` 与默认 sandbox helper 仍不稳定；本批编辑、检索与验证继续通过提权后的 PowerShell / 命令执行完成。该问题属于工具链环境问题，不是项目代码失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续评估 `unexpected_status` 是否还有必要补充一项更细但仍然稳定的字段；若没有明显收益，可暂停 failures 摘要扩展。
2. `阶段 4：回测内核（backtest-kernel）`：继续筛查 batch payload 是否还存在一个语义明确、值得在 payload 层收口的一致性字段；若剩余候选都偏业务判断，可考虑停止继续收口。
3. `阶段 5：报告层（reporting）`：暂不建议前移，等 `阶段 4` 的摘要语义与批量输入约束确认稳定后再评估。
