# 下一批真实开发执行记录（Batch 44）

时间：`2026-07-03`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的 batch 摘要业务可读性增强：

- 不再新增入口规则
- 转向让 batch failures 更清楚可读

## 本批实际落地

### 1. 为 batch failures 增加显式分类

- `app/services/batch_research_service.py`

本批为 batch 执行摘要中的 failures 增加：

- `failure_type`

当前已落地两类：

- `runtime_error`
- `unexpected_status`

这样 failures 不再只有一段 `error_message`，调用方可以先按类型判断，再决定如何展示或处理。

### 2. 补 services / reporting 透传验证

- `scripts/smoke_test_formal_services.py`

新增最小失败场景：

- 构造一个 batch，其中一个 run 抛 `RuntimeError`
- 断言 batch 结果状态为 `partial_failed`
- 断言 `failure_type == "runtime_error"`
- 断言 reporting summary 侧也能保留该 `failure_type`

### 3. 保持 API / HTTP / formal 验证稳定

本批没有新增 API/HTTP 结构字段断言，只确认这次增强不会误伤既有 smoke 和 formal verifications。

## 本批为何这样切

这一步符合上一轮建议中的“从输入规则转向摘要可读性增强”：

- 不扩 reporting 层模型
- 不改回测执行逻辑
- 只在 batch failures 这一层增加最小但有用的分类语义

本批的价值在于：阶段 4 的 batch 执行结果，不再只有“失败了”这一层信息，而开始具备最基本的失败类型识别能力。

## 验证结果

已通过：

- `python scripts/smoke_test_formal_services.py`
- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

说明：本轮默认 sandbox helper 仍无法稳定创建进程，实际验证继续使用沙箱外执行；阻塞点属于工具链 helper 层，不是项目代码运行失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：继续增强 batch failures 的可读性，例如补 `failure_stage` 或更细的 failure 分类，而不是只靠 `failure_type`。
2. `阶段 4：回测内核（backtest-kernel）`：如果想再回到输入约束，也可以继续评估 `strategy_name` 是否需要一致性约束，但这一步更依赖产品语义。
3. `阶段 5：报告层（reporting）`：当前仍不建议切换过去。