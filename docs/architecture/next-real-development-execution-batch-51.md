# 下一批真实开发执行记录（Batch 51）
时间：`2026-07-04`

## 本批目标

继续推进 `阶段 4：回测内核（backtest-kernel）` 的最小收口，按顺序处理上一轮建议：

- 先评估 `unexpected_status` 摘要是否还值得继续扩展
- 再为 batch payload 补一项仍然语义清晰的一致性约束

## 本批实际落地

### 1. 对 `unexpected_status` 摘要扩展做止步判断

- `已确认`：当前 `unexpected_status` 相关机器可读字段已经包括：
  - `failure_type`
  - `failure_stage`
  - `failure_code`
  - `failure_source`
  - `expected_status`
  - `result_status`
  - `status_transition`

本批评估后未继续新增生产字段。原因是继续扩展的收益已经明显下降，且更容易滑向业务解释层，而不是保持在最小摘要层。

### 2. 为 run-batch 增加 `extra_config` 一致性约束

- `app/schemas/backtest.py`

本批继续沿用既有 payload 校验方式，在 `parameters` 之后补齐：

- 当同一批 `runs` 中存在不同 `extra_config` 字典时，抛出 `ValueError("batch extra_config values must be consistent")`

该约束仍然只停留在 payload 校验层，不改服务层业务逻辑，不引入新依赖。

### 3. 补齐最小 smoke 验证闭环

- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

本批补齐两类验证：

- API 层对 `extra_config` 不一致输入抛出 `ValueError`
- HTTP 层对 `extra_config` 不一致输入返回 400

说明：services 层本批没有新增生产逻辑，因此只做回归 smoke，未新增 services 专项断言。

## 本批为何这样切

这一步仍然符合 `阶段 4：回测内核（backtest-kernel）` 的保守推进方式：

- 没有继续堆叠 failures 摘要字段
- 没有扩展 reporting 对外协议
- 没有改变回测执行流程

本批的核心是两件事：

- 对 failures 摘要扩展做一次明确止步，避免范围继续失控
- 只把仍然清晰、且明显属于实验配置一部分的 `extra_config` 收口到 payload 层

## 验证结果

已通过：
- `python scripts/smoke_test_formal_services.py`
- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

另已通过：
- `git diff --check -- app/schemas/backtest.py scripts/smoke_test_formal_api.py scripts/smoke_test_formal_http_adapter.py`

说明：当前线程内 `apply_patch` 仍不稳定；本批最终继续通过提权后的 PowerShell / 命令执行完成。该问题属于工具链环境问题，不是项目代码失败。

## 下一步建议

1. `阶段 4：回测内核（backtest-kernel）`：如无新的明确批内一致性字段，建议停止继续扩 payload 约束，避免开始进入偏业务判断区域。
2. `阶段 5：报告层（reporting）`：如果后续要继续推进，更适合转向消费这些已稳定摘要字段的展示或读取层，而不是继续堆叠回测内核输入约束。
