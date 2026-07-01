# SleeperCloudQuant 项目级 AGENTS 规则

## 一、项目定位

- 项目名称：`SleeperCloudQuant`
- 行业：`量化分析 / 金融科技`
- 产品形态：`本地化 Web 分析系统`
- 当前阶段：`startup-bootstrap`
- 当前目标：`先完成本地化量化分析系统的项目画像、边界澄清与最小验证基线，再进入真实开发。`

## 二、项目内优先约束

1. 本项目规则只补充项目特定边界，不重复全局 `AGENTS.md`、`agents/orchestrator.md` 和领域编排器已定义内容。
2. 软件开发任务默认走 `software-dev` 领域，并使用 `agents/role-registry.md` 中的正式角色名记录 `role_used`。
3. 项目创建或启动后，应先执行项目启动引导，自动生成项目画像、验证基线与启动清单，再进入真实迭代。
4. 未完成项目画像或验证基线前，不应直接进入高成本实现。
5. 若任务涉及已有代码理解、开源仓库比较或模块复用，应先进入 `code-archaeologist -> multi-repo-comparator -> reuse-integration-planner -> solution-architect` 链路，再进入实现。

## 三、项目工作原则

1. 所有需求、边界和术语都应区分 `已确认`、`待确认`、`基于当前上下文推断`。
2. 每轮验证输出默认使用固定结构：
   - `已验证项`
   - `未验证项`
   - `阻塞原因`
   - `潜在风险`
   - `发布判断`
3. 任何需要进入日志的 `role_used` 都必须使用正式角色名；历史别名只允许通过脚本兼容映射，不再新增。
4. 正式记忆与正式日志可写时，优先直写根级正式层，不长期滞留项目本地缓冲。
5. README 的 7 章由各阶段角色分章起草，最终由 `memory-curator` 汇总落盘。

## 四、项目特定关注点

- 核心术语：
- `量化分析`
- `本地化`
- `回测`
- `策略研究`
- `数据权限`

- 主要风险：
- `金融场景结论误导风险`
- `数据来源与授权边界不清`
- `本地运行环境差异导致验证不稳定`

- 本轮非目标：
- 当前不直接承诺实盘交易执行
- 当前不直接引入远程数据服务依赖

## 五、启动后必须具备的最小文档

- `docs/decision-log/project-profile.md`
- `docs/verification/verification-baseline.md`
- `docs/verification/verification-report-template.md`
- `docs/workflows/project-startup-checklist.md`
- `docs/requirements/project-scope.md`
- `docs/architecture/technical-boundaries.md`
- `docs/requirements/function-breakdown.md`
- `docs/requirements/business-flow.md`
- `docs/interaction/interaction-confirmation.md`
- `docs/architecture/data-model.md`
- `docs/architecture/runtime-notes.md`
- `docs/code-archaeology/repository-map.md`
- `docs/code-archaeology/repo-comparison.md`
- `docs/architecture/reuse-integration-plan.md`

## 六、项目内必须人工确认的事项

- 行业业务定义存在分歧时
- MVP 是否通过审批
- 新依赖引入或结构性改动时
- 权限、合规、数据边界存在不确定性时
