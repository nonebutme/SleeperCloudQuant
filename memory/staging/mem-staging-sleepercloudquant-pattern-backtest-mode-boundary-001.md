# Memory Entry

## Basic

- `id`: mem-staging-sleepercloudquant-pattern-backtest-mode-boundary-001
- `type`: Pattern
- `scope`: project:SleeperCloudQuant
- `status`: staging
- `summary`: 单品种测试、独立账户批量回测和投资组合回测可以统一任务目录、操作入口和结果外壳，但必须隔离账户、聚合和分析口径。

## Content

- `rule`: 三种回测模式共享入口时，后端能力、任务上下文和查看器容器可以复用；资金账户、样本范围、绩效汇总、报告评价对象和跨 Run 比较门禁必须按模式隔离。
- `context`: 适用于回测任务工作台、结果查看、专业分析和同口径 Run 对比。
- `abstraction_note`: 移除了具体页面节点、函数名、端口和阶段批次，只保留稳定业务边界。

## Evidence

- `source`: stages-60-76.9-design-and-verification
- `evidence`: 版本化策略、独立账户批量回测、投资组合回测、双模式报告和统一工作台阶段文档与专项验证记录。
- `timestamp`: 2026-07-25T09:30:00+08:00
- `confirm_count`: 1
- `retrieval_count`: 0

## Notes

- `notes`: stage77_governance_baseline_candidate | synced_to_root_staging | local_reference_only
