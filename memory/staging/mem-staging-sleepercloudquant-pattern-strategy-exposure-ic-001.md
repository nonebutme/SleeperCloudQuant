# 无显式因子时使用策略暴露 IC

- id: `mem-staging-sleepercloudquant-pattern-strategy-exposure-ic-001`
- category: `Pattern`
- project: `SleeperCloudQuant`
- created_at: `2026-07-28`
- status: `staging`
- validation_status: `已确认`
- confirmation_count: `1`
- source: 独立账户批量回测横截面分析实现与真实任务验证
- scope: 独立账户策略横截面能力评估

## 压缩结论

当回测任务没有显式绑定因子 ID 时，不应默认套用某个通用因子。可使用交易日收盘后的真实持仓权重作为“策略暴露信号”，与下一交易日标的收益做横截面 IC，但必须明确命名为策略暴露 IC。

## 抽象规则

1. 信号与结果必须按 `t→t+1` 对齐。
2. 横截面应包含已完成但空仓的账户，避免只选实际建仓标的造成选择偏差。
3. IC 至少需要 3 个有效标的且信号、收益均有差异。
4. Q1—Q5 每期至少需要 5 个有效标的；不足时明确不可用，不重复样本凑组。
5. 原始因子 IC 只有在策略显式输出因子分数后才能命名和计算。

## 验证证据

真实 3 股票任务形成 24 个有效日度横截面，成功计算 Pearson IC、Rank IC、Newey-West t 和 ICIR；Q1—Q5 因少于 5 个标的保持不可用。五股票确定性测试验证了 IC 与分层收益计算链。

