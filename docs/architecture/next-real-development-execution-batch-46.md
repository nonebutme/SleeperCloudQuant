# 下一批真实开发执行记录（Batch 46）
时间：`2026-07-03`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的保守收口，在既有 `failure_type` / `failure_stage` 与 batch 输入一致性约束基础上，再完成两项最小增强：

- 为 `batch failures` 增加稳定的机器可读 `failure_code`
- 为 `run-batch` 输入补齐 `frequency` 一致性约束

## 本批实际落地

### 1. 为 batch failures 增加 `failure_code`

- `app/services/batch_research_service.py`

本批在既有失败摘要上继续补一个稳定编码字段：

- 运行期异常：`failure_code = "BACKTEST_RUN_ONCE_RUNTIME_ERROR"`
- 返回状态异常：`failure_code = "BACKTEST_UNEXPECTED_RESULT_STATUS"`

这一步仍然只发生在 batch 摘要层，不改回测执行主流程，也不引入新的错误模型类型。

### 2. 为 run-batch 增加 `frequency` 一致性约束

- `app/schemas/backtest.py`

本批继续沿用前几批已建立的 batch payload 校验方式，在 `benchmark` 与 `strategy_name` 之后，补齐 `frequency` 批内一致性校验：

- 当同一批 `runs` 中存在不同 `frequency` 时，抛出 `ValueError("batch frequency values must be consistent")`

之所以优先选择 `frequency`，是因为它更接近批量运行的执行条件，语义比日期、资金等字段更稳，也更适合先做最小收口。

### 3. 补齐最小 smoke 验证闭环

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

本批补齐两类验证：

- services / reporting 链路中 `failure_code` 的透传验证
- API / HTTP 层对 `frequency` 不一致输入的拒绝验证

## 本批为何这样切

这一步仍然属于 `阶段 4：回测内核（backtest-kernel）` 的最小推进：

- 没有改动领域模型结构
- 没有扩展到 reporting 对外协议重构
- 没有引入更深层的策略配置校验

选择 `failure_code` 与 `frequency`，是因为两者都满足：

- 影响面小
- 可读性或可判定性明显提升
- 可以直接复用现有 smoke 与 formal verifications 验证闭环

## 验证结果

已通过：
- `python scripts/smoke_test_formal_services.py`
- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

另已通过：
- `git diff --check -- app/services/batch_research_service.py app/schemas/backtest.py scripts/smoke_test_formal_services.py scripts/smoke_test_formal_api.py scripts/smoke_test_formal_http_adapter.py`

说明：当前线程内 `apply_patch` 与默认 sandbox helper 仍不稳定；本批编辑与验证继续通过提权后的 PowerShell / 命令执行完成。该问题属于工具链环境问题，不是项目代码失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续检查 batch failures 是否还需要一项最小且稳定的机器可读补充字段，例如是否要区分输入校验失败与运行期失败来源。
2. `阶段 4：回测内核（backtest-kernel）`：继续筛查 batch 输入中是否还存在一个语义非常明确、适合在 payload 层收口的一致性字段。
3. `阶段 5：报告层（reporting）`：暂不建议前移，等 `阶段 4` 的 failures 摘要语义再稳定一轮后再评估对外展示增强。
