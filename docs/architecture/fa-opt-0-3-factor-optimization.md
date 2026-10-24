# FA-OPT 0→3 因子制品优化实施

## 状态与边界

- `已确认`：FA-OPT 0→3 为阶段 91.0–91.3 之后的独立因子研究增量，不启动 91.4。
- `已确认`：每个优化任务必须固定一个已发布的 `artifact_id`，禁止按 `factor_id` 自动追随最新制品。
- `已确认`：默认优化字段为 `aligned_value`，其语义为“数值越高，方向对齐后的预期越优”。
- `已确认`：创建任务只写入 `ready` 状态；必须显式调用 `start` 才允许执行。
- `已确认`：执行器不读取行情库、不触发同步、不切换数据版本，只消费不可变制品和其来源研究观测。

## FA-OPT 0：合同冻结

预检冻结以下身份：

- `artifact_id`
- `artifact_content_hash`
- `source_task_id`
- `factor_id` / `factor_version`
- `data_version_id` / `quality_report_id`
- `value_field`
- 前瞻周期、分组数、成本候选和最小横截面样本数

冻结结果生成 `context_hash`。任务执行前再次比较制品内容哈希；若发生变化，任务失败，不使用替代制品。

## FA-OPT 1：持久任务

新增两项受治理资产：

- `factor_optimization_tasks`：C1 控制审计层，保存冻结输入、状态、进度与错误。
- `factor_optimization_reports`：F4 因子资产层，保存不可变优化报告。

应用重启时，遗留 `running` 任务恢复为 `interrupted`，可由显式重试入口重新执行。

## FA-OPT 2：确定性候选评估

执行器在同一制品上比较：

- 前瞻周期 `forward_horizons`
- 分组数 `group_counts`
- 单边成本率 `one_side_rates`

每个交易日按冻结字段升序排列，计算最高组减最低组的前瞻收益；换手由最高组和最低组成员变化之和估计，成本为换手乘单边成本率。默认目标为平均净多空收益。

该结果只属于历史因子研究估算，不构成回测、模拟盘、实盘或投资建议。

## FA-OPT 3：API 与验证

API：

- `POST /api/factor-research/optimization/preflight`
- `POST /api/factor-research/optimization/tasks`
- `GET /api/factor-research/optimization/tasks`
- `GET /api/factor-research/optimization/tasks/{task_id}`
- `POST /api/factor-research/optimization/tasks/{task_id}/start`
- `POST /api/factor-research/optimization/tasks/{task_id}/retry`
- `GET /api/factor-research/optimization/reports/{report_id}`

最小验证：

```powershell
python scripts/smoke_test_factor_optimization.py
python scripts/smoke_test_stage89_data_governance.py
python scripts/smoke_test_stage88_integrity_bridge.py
```

## 明确非目标

- 不启动 91.4。
- 不联网、不导入正式指数事实、不写正式行情库。
- 不自动启动优化任务。
- 不自动选择最新制品。
- 不做任意 Python 优化器、实盘参数下发或收益承诺。
