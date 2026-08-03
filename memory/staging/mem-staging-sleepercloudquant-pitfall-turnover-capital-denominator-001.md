# 投资组合换手率分母不得使用单位净值

- id: `mem-staging-sleepercloudquant-pitfall-turnover-capital-denominator-001`
- category: `Pitfall`
- project: `SleeperCloudQuant`
- created_at: `2026-07-27`
- status: `staging`
- validation_status: `已确认`
- confirmation_count: `1`
- source: 回测分析报告 v4.1 三模板指标审计
- scope: 共享资金账户回测报告

## 压缩结论

双边换手率的分子是买卖成交额绝对值之和，分母必须是同口径的平均账户总资产；若误用约为 `1` 的单位净值，结果会被放大约等于账户资金规模的倍数。

## 抽象规则

凡是“金额 ÷ 资本”的比率，分子和分母必须保持货币量纲一致。单位净值只适合计算收益和回撤，不可直接作为成交额换手率的资本分母。

## 验证证据

真实组合任务在误用单位净值时显示约 `28 亿%`，改用账户 `total_value` 后为约 `2805%`；后者与短样本期成交额和平均资金规模一致。

