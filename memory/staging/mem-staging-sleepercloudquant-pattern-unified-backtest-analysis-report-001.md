# Pattern：策略回测使用统一分析报告入口

- `memory_id`: `mem-staging-sleepercloudquant-pattern-unified-backtest-analysis-report-001`
- `category`: `Pattern`
- `source`: `用户确认的界面优化方案 v4.1`
- `timestamp`: `2026-07-27T23:05:00+08:00`
- `scope`: `项目专属；策略回测任务、结果阅读和报告交互`
- `validation_status`: `user_confirmed_and_implemented`
- `confirmation_count`: `1`

## 压缩结论

策略回测完成后只提供一个“分析报告”入口，不再把“查看结果”和“查看分析”设计成两套页面。统一报告的顶层结构固定为“回测分析 / 交易明细 / 持仓快照 / 账户快照”。

## 分类与抽象

- `Pattern`：统一阅读入口，证据按顶层 Tab 分层。
- 三种模式共享外壳，但账户和统计语义仍严格隔离。
- 单品种测试围绕单标的行为轨迹。
- 独立账户批量回测只评价横截面能力，禁止汇总净值。
- 投资组合回测围绕共享资金账户进行业绩审计。
- 缺少真实证据时显示不可用，不用演示值补齐。

## 证据

- 用户明确要求不再刻意区分“查看结果”和“查看分析”。
- v4.1 实现已通过完整统一正式验证。
- 三种真实任务均完成无头浏览器点击和渲染验收。

## 取代关系

本条目取代 `mem-staging-sleepercloudquant-pattern-backtest-report-information-architecture-001` 中“查看结果—查看分析—底部原始数据”的旧外壳描述；旧条目的三种账户语义和“缺失证据不补演示值”规则继续有效。
