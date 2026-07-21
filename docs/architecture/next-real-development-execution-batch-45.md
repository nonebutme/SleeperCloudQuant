# 下一批真实开发执行记录（Batch 45）
时间：`2026-07-03`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的最小增强，在不扩架构、不引入新依赖的前提下，完成两项已进入可验证范围的收口：

- 为 `batch failures` 增加更细一层的阶段语义，避免只有 `failure_type`
- 为 `run-batch` 输入补齐 `strategy_name` 一致性约束，保持 batch 语义收敛

## 本批实际落地

### 1. 为 batch failures 增加 `failure_stage`

- `app/services/batch_research_service.py`

本批在既有 `failure_type` 基础上继续补一层最小可读性字段：

- 运行期异常：`failure_stage = "run_once"`
- 返回结果状态异常：`failure_stage = "result_status_check"`

这样调用方在不解析整段错误文案的情况下，可以先按失败阶段做最小分类，再决定如何展示或追踪。

### 2. 为 run-batch 增加 `strategy_name` 一致性约束

- `app/schemas/backtest.py`

本批继续沿用前几批已建立的 batch 输入约束风格，在 `benchmark` 一致性之后，补齐 `strategy_name` 一致性校验：

- 当同一批 `runs` 中存在多个不同的 `strategy_name` 时，抛出 `ValueError("batch strategy_name values must be consistent")`

该约束仍然停留在 payload 归一化/校验层，不下沉到更深服务层，符合本轮“先收口输入层，再决定是否扩到业务层”的边界。

### 3. 补齐最小 smoke 验证闭环

- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

本批补齐两类验证：

- services/reporting 链路中 `failure_stage` 的透传验证
- API/HTTP 层对 `strategy_name` 不一致输入的拒绝验证

## 本批为何这样切

这一步仍然属于 `阶段 4：回测内核（backtest-kernel）` 的保守收口，而不是扩到新的层面：

- 没有改动回测执行主流程
- 没有改动 reporting 输出结构之外的外围协议
- 没有把 batch 输入语义扩展成更复杂的业务模型

选择先做这两点，是因为它们都满足：

- 影响面小
- 现有语义清晰
- 可以用现有 smoke 与 formal verifications 做直接验证

## 验证结果

已通过：
- `python scripts/smoke_test_formal_services.py`
- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：当前线程内 `apply_patch` 与默认 sandbox helper 仍不稳定，实际编辑与验证继续通过提权后的 PowerShell/命令执行完成；该问题属于工具链环境问题，不是本项目代码失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续细化 `batch failures` 的机器可读摘要，例如评估是否补充稳定的失败代码字段，而不只依赖 `failure_type/failure_stage`。
2. `阶段 4：回测内核（backtest-kernel）`：继续检查 `run-batch` 其他已明显具备批内一致性语义的字段，确认是否还存在一个最小且值得收口的输入约束点。
3. `阶段 5：报告层（reporting）`：暂不建议前移；应等 `阶段 4` 的 batch 失败摘要语义再稳定一轮后再评估是否需要对外展示增强。
