# SleeperCloudQuant

日常启动：双击根目录 **`启动系统.cmd`**，系统就绪后自动打开 **http://127.0.0.1:8010/**。全部正式业务与 API 共用此入口；停止请双击 `停止系统.cmd`。

`web/index.html` 由服务加载；PowerShell/Python 脚本是内部启动层。8000/8020 仅供显式开发测试，详见 [统一启动说明](docs/workflows/windows-double-click-launchers.md)。

## 项目概览

- 项目名称：`SleeperCloudQuant`
- 行业：`量化分析 / 金融科技`
- 产品形态：`本地化 PC Web 量化研究系统`
- 默认领域：`software-dev`
- 当前阶段：`r2-indicator-library-candidate`；[指标库契约](docs/architecture/r2-indicator-library.md)。R1 正式数据与整页业务验收限制继续保留。

## 最终目标

建设一个本地运行、面向 A 股量化研究人员的 PC Web 研究工作台，覆盖本地数据治理、因子研究、版本化策略编写、单股/独立账户批量回测/投资组合回测三类回测、结果证据查看、专业分析报告、Run 对比和 AI 辅助复盘，并保证结果可复现、数据可追溯、分析口径不误导。

当前不承担实盘交易执行，也不输出确定性投资建议。
当前项目仅用于非商用、本地研究；数据源优先选择免费且可由项目适配的接口。

## 当前状态
- 阶段 91.0—91.3 已实施并通过专项与统一正式验证：数据源能力级只读探测、任务冻结与实际配置证据、统一质量修复工单、纠错覆盖版本、复检后关闭及发布就绪度已接通；人工浏览器业务验收待执行，91.4 暂不启动。
- 阶段 90 数据分层治理：P0 分层纠偏、P1 关键血缘已完成并通过统一验证；P2/P3 仅冻结规则，未拆表、未重写业务数据、未删除文件。
- 阶段 89.0—89.4 已完成：双轴分层、正式运行库提升、77 项资产/9 条血缘、消费就绪度、纠错版本字段、8 个回测查询索引和保留策略通过统一验证；89.5 未启动。
- 阶段 88 已完成：历史质量问题复检闭环，最新发布版本已设为全局默认；因子研究、策略数据集和回测统一冻结数据版本。
- 阶段 88 已完成：因子任务自动发布不可变 `factor_values` 制品，策略声明因子依赖后由三类回测任务在创建时冻结并逐日消费。
- 阶段 88 已完成：因子/回测报告统一披露历史模拟、数据版本、因子制品、市场冲击未建模和未做模拟盘/实盘验证。
- 待人工确认：沪深 300、中证 500、中证 1000 外部成分数据的来源授权和本地落库许可；未确认前指数池保持不可用，不倒推历史。
- 实施与验收：`docs/architecture/stage-88-remediation-implementation.md`、`docs/verification/stage-88-remediation-acceptance.md`。
- 已完成：阶段 77.2，A 股 raw/qfq/hfq 已增量补齐至 2026-07-24，三口径质量状态均为 `passed`。
- 已完成：单品种、独立账户批量和投资组合三类真实任务的结果/分析验收，完整统一验证全部通过。
- 已完成：阶段 78.1 增量治理 schema、小样本上下文事实、沪深 300 正式基准、质量门禁与 `published data_version` 强绑定。
- 正式版本：`scq-20260810-27cd5406fa3a12a9`，质量报告 `stage782-20260810-2e42c465479e` 与 9 个版本成员均为 `passed`；HFQ 修复后已纳入全局默认版本。
- 当前边界：raw/qfq/hfq 均到 2026-08-10，交易状态、复权因子与公司行动到 2026-07-24，生命周期到 2026-07-16；独立因子研究流水线已落地，正式指数点时成分仍未导入。
- 已完成：阶段 78.2 持久化增量队列、全局请求限频、重试/隔离、启动补偿、参考数据预刷新和原子发布。
- 已完成：阶段 78.3 全市场生命周期、日交易状态、公司行动和复权因子回填，质量门禁与三类真实回测验收通过。
- 已完成：策略回测统一分析报告 v4.1，不再区分“查看结果 / 查看分析”，统一为回测分析、交易明细、持仓快照、账户快照四个顶层 Tab。
- 阶段入口：`docs/architecture/backtest-analysis-report-v4-1.md`
- 已完成：v4.1 三模板指标审计，补齐真实可推导指标、原始成交/持仓/账户证据，并对 IC、分层收益、VWAP 等缺失证据显示明确不可用状态。
- 审计入口：`docs/verification/backtest-report-v4-1-metric-audit.md`
- 已完成：独立账户策略暴露 IC、Rank IC、Newey-West t、ICIR 与信号统计；Q1—Q5 按每期至少 5 个标的执行严格门槛。
- 分析口径：`docs/architecture/independent-strategy-exposure-analysis.md`
- 已完成：阶段 79 全市场策略暴露横截面验收，以及阶段 80—85 原始信号证据、行业中性分析、成本/容量、样本外稳健性和报告产品化候选成果。
- 已完成：阶段 86 数据中心 M0—M5、增量控制层、规范库只增迁移、真实浏览器和统一正式验证。
- 已完成：阶段 87.0 治理冻结、87.1 六个 P0 因子研究闭环、87.2 点时指数合同与增强分析代码；正式指数事实缺失时保持 unavailable。
- 因子治理：docs/architecture/stage-87-0-factor-governance-freeze.md
- 因子验收：docs/verification/stage-87-factor-analysis-acceptance.md
- 阶段入口：`docs/architecture/stage-86-0-governance-product-freeze.md`
- 交互基线：`docs/interaction/stage-86-data-center-factor-mvp.md`
- 已完成：数据中心升级阶段 B1—B4及阶段 C 质量闭环，包含全库摘要、多值/日期筛选、原子批量处置、受控批量重拉和结果回写；阶段 D 尚未启动。
- 升级冻结：`docs/architecture/data-center-upgrade-stage-a-freeze.md`
- 阶段 B 实施：`docs/architecture/data-center-upgrade-stage-b-implementation.md`
- 阶段 C 实施：`docs/architecture/data-center-upgrade-stage-c-implementation.md`
- 已补齐：数据中心受控目录共 9 项；AKShare、AKShare 同花顺及巨潮已验证启用，其余候选继续停用；免费接口适配优先级已完成评估。
- 数据源评估：`docs/architecture/data-center-free-source-adaptation-priority.md`
- P1 验证：AKShare 同花顺为受控失败回退源；巨潮仅开放行业目录与行业变更两条 `fill_missing` 路由。首个正式受控任务 `000001` 对账一致并以 `completed_noop` 完成，写入 0、未发布；公告和股本继续停用。证据见 `docs/verification/data-center-p1-source-contract-validation.md`。
- 配置治理：控制元数据已升级至 86.3.6，概念目录与全球指数目录/路由已对齐，内部生产者显式登记；必需路由缺失与孤儿路由均为 0，且版本迁移不再覆盖人工配置。

## 关键文档入口

1. `AGENTS.md`
2. `manifest.md`
3. `docs/decision-log/project-profile.md`
4. `docs/decision-log/stage-77-0-governance-baseline.md`
5. `docs/verification/verification-baseline.md`
6. `docs/architecture/technical-boundaries.md`
7. `docs/architecture/data-model.md`
8. `docs/architecture/runtime-notes.md`
9. `docs/architecture/stage-77-2-data-freshness-recovery.md`
10. `docs/architecture/stage-78-0-data-governance-architecture-freeze.md`
11. `docs/architecture/stage-78-1-governance-skeleton-sample-integration.md`
12. `docs/architecture/stage-78-2-incremental-sync-scheduler.md`
13. `docs/architecture/stage-78-3-full-market-context-backfill.md`
14. `docs/architecture/backtest-analysis-report-v4-1.md`

15. `docs/architecture/stage-79-0-cross-sectional-analysis-freeze.md`
16. `docs/architecture/stage-80-85-backtest-evidence-and-productization.md`
17. `docs/architecture/stage-86-0-governance-product-freeze.md`
18. `docs/interaction/stage-86-data-center-factor-mvp.md`
19. `docs/architecture/stage-86-data-center-implementation.md`
20. `docs/verification/stage-86-data-center-acceptance.md`
21. `docs/architecture/vtable-global-adoption.md`
22. `docs/architecture/quant-ui-global-standard.md`
23. `docs/architecture/data-center-upgrade-stage-a-freeze.md`
24. `docs/architecture/data-center-upgrade-stage-b-implementation.md`
25. `docs/architecture/data-center-upgrade-stage-c-implementation.md`
26. `docs/architecture/data-center-free-source-adaptation-priority.md`
27. `docs/verification/data-center-p1-source-contract-validation.md`

28. docs/architecture/stage-87-factor-analysis-design-proposal.md
29. docs/architecture/stage-87-0-factor-governance-freeze.md
30. docs/verification/stage-87-factor-analysis-verification-baseline.md
31. docs/verification/stage-87-factor-analysis-acceptance.md
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
- 前端：原生 HTML、CSS、JavaScript；全局使用 Quant UI Standard 亮暗主题与本地 VisActor VTable 1.23.1
- 服务层：自定义 `RouteDefinition`、Schema、Service 与依赖装配
- HTTP 运行时：Python 标准库 `ThreadingHTTPServer`
- 数据库：本地 SQLite；阶段 87 使用独立 var/runtime/factor_research.sqlite3，行情主库只读；少量任务索引与配置草稿使用 JSON
- 统一验证：`python scripts/run_formal_verifications.py`

## 协作与发布边界

- 需求、业务口径和交互由前置角色起草并由项目负责人确认。
- 技术架构、数据结构和运行时说明由架构与开发角色维护。
- 结果层回答“发生了什么”；分析层回答“为什么、是否可信、风险在哪里”。
- 三种回测模式可统一入口和外壳，但不可混用账户、统计和报告语义。
- 最终由 `memory-curator` 汇总稳定共识，新增经验先进入 staging。
- 正式回测只读取 `published` 数据版本；未发布观察与正式范围分层展示。
- 独立因子研究与策略暴露分析复用统计能力但保持业务对象、输入证据和报告命名分离。

## P0—P3 市场全景增量状态（2026-07-30）

- M4 已支持从 K 线交易日下钻行业热度、概念热度、行业资金流、概念资金流、当日新闻与公告五个分区，并统一使用本地 VisActor VTable 展示可见表格。
- `2026-07-28` 当前 5 个分区中 4 个可用；行业资金流因免费上游失败保持 `unavailable`。
- A 股 qfq 目标日任务已发布为 `scq-20260728-033fc57a7de87fe4`，5533 项全部完成，9 个原隔离项均有明确停牌证据。
- 当前仍非商用；不承诺免费上游 SLA，不以推断或模拟数据填补缺口。
