# 阶段 63：双模式专业分析报告

## 模式边界

- 共享资金池组合报告复用报告中心当前 7 维策略评估模板，数据来自一个共享账户和一条组合净值曲线。
- 独立选股建仓汇总报告仅统计至少产生一笔有效 BUY 成交且运行完成的股票。
- 未建仓和失败股票保留在筛选漏斗中，不进入收益分布，不把独立单股结果伪装成组合净值。

## 独立选股统计方法

- 描述统计：均值、中位数、样本方差、标准差、最小值、最大值及 5%/25%/75%/95% 分位数。
- 分布形态：偏度、超额峰度、Freedman-Diaconis 直方图。
- 正态性：Jarque-Bera 检验；样本少于 8 时不执行，不能把“未拒绝”解释成“证明服从正态分布”。
- 区间估计：均值 95% 置信区间；小样本使用 t 临界值，并提供固定种子的 1,000 次 bootstrap 百分位区间。
- 下行风险：亏损概率、95% VaR、95% CVaR、盈亏比。
- 分组比较：市场、首次建仓月份、历史行业和历史概念，输出样本量、均值、中位数、标准差、正收益概率和四分位数。

## 历史时点分类

- 独立 SQLite 分类库存储 `symbol + dimension + category + valid_from + valid_to + source`。
- 报告以股票首次有效 BUY 成交日执行 as-of 匹配，禁止用当前行业或概念快照回填历史任务。
- 行业通过 AKShare `stock_industry_change_cninfo` 同步上市公司行业归属变更。
- AKShare 当前未提供等价的 A 股概念历史成分接口；概念只接受带有效日期、来源和证据的 JSONL 数据导入。
- 分类不足时报告展示覆盖率和“未分类”，不推断、不伪造。

## API 与 Web

- `GET /api/reporting/backtest-modes/shared-portfolio/{task_id}`
- `GET /api/reporting/backtest-modes/independent-screening/{task_id}`
- 报告中心新增双模式任务查询、统计摘要、收益直方图、正态性与置信区间、分组比较和分类覆盖率。
- 同步脚本：`scripts/sync_a_share_classification_history.py`。

## 验证

- `scripts/smoke_test_backtest_mode_reports.py` 已纳入统一正式验证。
- 完整 `scripts/run_formal_verifications.py` 全部通过。
- 真实共享资金池任务成功复用当前 7 维模板，返回 7 个维度及综合评分。
- 真实三股独立任务行业历史覆盖率为 100%，分为“货币金融服务”和“房地产业”。
- 真实三股样本少于 8，正态性状态正确返回 `insufficient_sample`；概念历史覆盖率为 0%，未使用当前快照回填。
