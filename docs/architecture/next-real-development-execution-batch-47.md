# 下一批真实开发执行记录（Batch 47）
时间：`2026-07-03`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的最小收口，在既有 `failure_type` / `failure_stage` / `failure_code` 与 batch 输入一致性约束基础上，再完成两项小步增强：

- 为 `batch failures` 增加更明确的来源语义 `failure_source`
- 为 `run-batch` 输入补齐 `initial_cash` 一致性约束

## 本批实际落地

### 1. 为 batch failures 增加 `failure_source`

- `app/services/batch_research_service.py`

本批继续只在 batch 摘要层补充机器可读字段：

- 运行期异常：`failure_source = "single_run_service"`
- 返回状态异常：`failure_source = "result_summary"`

这一步与前几批的 `failure_type` / `failure_stage` / `failure_code` 一样，仍然不改回测执行流程，只增强摘要语义。

### 2. 为 run-batch 增加 `initial_cash` 一致性约束

- `app/schemas/backtest.py`

本批在已收口的 `benchmark`、`strategy_name`、`frequency` 之后，再补一项更接近实验条件的输入约束：

- 当同一批 `runs` 中存在不同 `initial_cash` 时，抛出 `ValueError("batch initial_cash values must be consistent")`

之所以优先选择 `initial_cash`，是因为它更像批量实验的基础比较条件，且当前示例与 smoke 中本就天然保持一致，风险低于直接锁定日期窗口等更强业务语义。

### 3. 补齐最小 smoke 验证闭环

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

本批补齐两类验证：

- services / reporting 链路中 `failure_source` 的透传验证
- API / HTTP 层对 `initial_cash` 不一致输入的拒绝验证

## 本批为何这样切

这一步仍然符合 `阶段 4：回测内核（backtest-kernel）` 的保守推进方式：

- 没有新增领域对象
- 没有改变外部协议结构
- 没有把输入校验下沉到更深服务层

选择 `failure_source` 与 `initial_cash`，是因为它们都满足：

- 影响面小
- 语义清晰
- 可以复用现有 smoke 与 formal verifications 直接验证

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

1. `阶段 4：回测内核（backtest-kernel）`：继续评估 batch failures 是否还需要一项最小的补充字段，例如仅对 `unexpected_status` 增加显式结果状态值，而不扩整体模型。
2. `阶段 4：回测内核（backtest-kernel）`：继续筛查 batch payload 中是否还存在一个语义非常明确、且适合在 payload 层收口的一致性字段。
3. `阶段 5：报告层（reporting）`：暂不建议前移，等 `阶段 4` 的 failures 摘要语义再稳定一轮后再评估。
