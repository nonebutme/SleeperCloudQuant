# 阶段四因子消费闭环

## 状态与边界

- `已确认`：策略只消费调用方显式提供的不可变 `artifact_id`，不按 `factor_id` 回退到最新制品。
- `已确认`：策略因子默认字段为 `aligned_value`。
- `已确认`：导出是只读声明生成，`writes=0`、`task_started=false`；策略或回测任务仍须由现有入口显式启动。
- `已确认`：本增量不启动阶段五，也不启动 91.4。

## 因子值数据集注册

审计确认 `factor_values` 已存在于数据中心权威目录，因此不重复注册第二个数据集。此次补齐正式 schema：

- `symbol`
- `trade_date`
- `factor_id`
- `artifact_id`
- `value`
- `aligned_value`

因子依赖合同默认要求 `artifact_id` 与 `aligned_value`，点时策略为 `same_trade_date_immutable_artifact`。

## 受治理的策略声明导出

只读入口：

```text
GET /api/factor-research/artifacts/{artifact_id}/strategy-declaration
```

返回 `strategy-factor-declaration-v1`，包含：

- 精确制品身份、内容哈希、来源研究任务、数据版本和质量报告；
- `DATASET_REQUIREMENTS = ["a_share_daily", "factor_values"]`；
- 固定 `FACTOR_REQUIREMENTS`；
- 参数中的 `factor_artifacts[factor_id] = artifact_id`；
- 默认 `factor_value_field = aligned_value`；
- 可直接由 `target-weights-v1` 执行器消费的静态策略源码；
- 原研究配置快照，供审计和复现使用。

导出前检查全部制品行均具备 `aligned_value`。制品不存在、来源任务缺失或默认字段覆盖不完整时显式失败。

## 调用示例

```python
declaration = factor_service.export_strategy_factor_declaration(artifact_id)
frozen = dataset_resolver.freeze_parameters(
    declaration["source_code"],
    declaration["parameters"],
)
resolved = dataset_resolver.resolve(declaration["source_code"], bars, frozen)
weights = execute_target_weights(
    declaration["source_code"], resolved["bars"], frozen
)
```

`freeze_parameters` 不再接受缺少 `factor_artifacts` 的因子策略。错误制品 ID、因子与制品不匹配、日期覆盖不完整都会阻断执行。

## 明确非目标

- 不自动创建、启动策略或回测任务。
- 不生成或执行任意用户 Python。
- 不联网、不读取或写入新的行情版本。
- 不承诺模拟盘、实盘或投资收益。
