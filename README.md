# SleeperCloudQuant

## 项目概览

- 项目名称：`SleeperCloudQuant`
- 行业：`量化分析 / 金融科技`
- 产品形态：`本地化 PC Web 量化研究系统`
- 默认领域：`software-dev`
- 当前阶段：`stage-77-governance-and-results-analysis`

## 最终目标

建设一个本地运行、面向 A 股量化研究人员的 PC Web 研究工作台，覆盖本地数据治理、因子研究、版本化策略编写、单股/独立账户批量回测/投资组合回测三类回测、结果证据查看、专业分析报告、Run 对比和 AI 辅助复盘，并保证结果可复现、数据可追溯、分析口径不误导。

当前不承担实盘交易执行，也不输出确定性投资建议。

## 当前状态

- 已完成：阶段 76.9，统一策略回测工作台、三模式任务入口、统一结果查看器和分层分析报告已落地。
- 当前门禁：A 股行情数据最新日期为 2026-07-17，完整正式验证在数据新鲜度检查处中止。
- 下一主线：先完成阶段 77.0 治理基线，再由用户重点确认“查看结果 / 查看分析”的业务口径和交互方案。
- 阶段入口：`docs/decision-log/stage-77-0-governance-baseline.md`

## 关键文档入口

1. `AGENTS.md`
2. `manifest.md`
3. `docs/decision-log/project-profile.md`
4. `docs/decision-log/stage-77-0-governance-baseline.md`
5. `docs/verification/verification-baseline.md`
6. `docs/architecture/technical-boundaries.md`
7. `docs/architecture/data-model.md`
8. `docs/architecture/runtime-notes.md`
9. `docs/architecture/stage-76-unified-backtest-workspace.md`

## README 7 章结构

1. `docs/requirements/project-scope.md`
2. `docs/requirements/function-breakdown.md`
3. `docs/requirements/business-flow.md`
4. `docs/interaction/interaction-confirmation.md`
5. `docs/architecture/technical-boundaries.md`
6. `docs/architecture/data-model.md`
7. `docs/architecture/runtime-notes.md`

## 当前技术栈

- 主语言：Python 3.14
- 前端：原生 HTML、CSS、JavaScript
- 服务层：自定义 `RouteDefinition`、Schema、Service 与依赖装配
- HTTP 运行时：Python 标准库 `ThreadingHTTPServer`
- 数据库：本地 SQLite；少量任务索引与配置草稿使用 JSON
- 统一验证：`python scripts/run_formal_verifications.py`

## 协作与发布边界

- 需求、业务口径和交互由前置角色起草并由项目负责人确认。
- 技术架构、数据结构和运行时说明由架构与开发角色维护。
- 结果层回答“发生了什么”；分析层回答“为什么、是否可信、风险在哪里”。
- 三种回测模式可统一入口和外壳，但不可混用账户、统计和报告语义。
- 最终由 `memory-curator` 汇总稳定共识，新增经验先进入 staging。
- 行情新鲜度恢复并完整验证通过前，不宣称全系统可发布。
