# 策略数据集依赖校验

状态：M3 兼容校验基线。

`app/services/strategy_dataset_validation.py` 为策略编辑和保存前置校验提供独立入口，不替换现有 `StrategyService.validate_source`，也不改变现有策略编辑页面。

策略可通过显式参数或源码中的两个字面量声明依赖：

```python
DATASET_REQUIREMENTS = ["a_share_daily"]
FACTOR_REQUIREMENTS = ["close_to_ma2_bias"]
```

校验器检查：

- 数据集是否存在且处于 `connected` 状态；
- 因子是否有已登记的数据集绑定；
- 因子所需数据集是否同时被策略声明；
- 数据集字段和 point-in-time 策略是否可见；
- 始终返回 `target-weights-v1` 执行契约。

旧页面仍可继续调用现有策略校验逻辑，作为回退入口。后续新编辑入口接入该校验器后，才将数据依赖结果展示给用户。

