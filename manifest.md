# SleeperCloudQuant Manifest

## 基本信息

- `project_name`: `SleeperCloudQuant`
- `project_type`: `local-quant-web-system`
- `current_stage`: `stage-86-data-center-upgrade-stage-c-completed`
- `priority_goal`: `维护阶段 C 质量闭环候选基线；阶段 D M4 可视化增强或阶段 87 独立因子研究均须再次人工批准。`

## 业务属性

- `industry`: `量化分析 / 金融科技`
- `product_shape`: `本地化 PC Web 量化研究系统`
- `target_users`:
- 量化研究人员
- 交易分析人员

## 技术属性

- `primary_lang`: `Python 3.14`
- `secondary_langs`:
- `JavaScript`
- `HTML`
- `CSS`
- `framework`: `自定义轻量路由与服务层；前端为原生 Web 技术`
- `frontend_table`: `VisActor VTable 1.23.1（本地固定版本，全局统一使用）`
- `frontend_design_system`: `SleeperCloudQuant Quant UI Standard（2026-07-30 人工批准，全局生效）`
- `runtime`: `Python 标准库 ThreadingHTTPServer，本地单机运行`
- `database`: `SQLite 为主，JSON 用于少量任务索引与运行草稿`

## 路由属性

- `allowed_domains`:
- `software-dev`
- `default_domain`: `software-dev`
- `requires_business_review`: `true`
- `requires_mvp_approval_before_deep_build`: `true`

## 复用属性

- `reference_projects`:
- `backtrader`
- `rqalpha`
- `SleeperCloudQuant-old`
- `TradingAgents-CN-main`
- `vnpy`
- `reuse_policy`: `先考古评估，再决定自研 / 复用 / 局部提取`
- `code_archaeology_report_path`: `projects/SleeperCloudQuant/docs/code-archaeology/repository-map.md`
- `multi_repo_comparison_path`: `projects/SleeperCloudQuant/docs/code-archaeology/repo-comparison.md`
- `reuse_integration_plan_path`: `projects/SleeperCloudQuant/docs/architecture/reuse-integration-plan.md`

## 启动属性

- `startup_bootstrap_script`: `python memory_system/project_bootstrap.py --write --input-file <payload.json>`
- `startup_query`: `数据中心升级阶段 C 已完成；下一步等待阶段 D 或阶段 87 的人工批准`
- `project_profile_path`: `projects/SleeperCloudQuant/docs/decision-log/project-profile.md`
- `verification_baseline_path`: `projects/SleeperCloudQuant/docs/verification/verification-baseline.md`
- `verification_report_template_path`: `projects/SleeperCloudQuant/docs/verification/verification-report-template.md`

## 项目约束

- `project_rules_source`: `projects/SleeperCloudQuant/AGENTS.md`
- `global_rules_source`: `AGENTS.md`
- `memory_scope`: `global_memory/projects/SleeperCloudQuant/`
- `log_scope`: `traces/task_logs.jsonl`


## 当前交付状态

- `latest_completed_stage`: `stage-86-data-center-upgrade-stage-c`
- `latest_ui_iteration`: `quant-ui-global-standard-2026-07-30`
- `current_release_judgment`: `86.3.6 配置治理已闭环：20 个数据集、22 条路由，必需路由缺失与孤儿路由均为 0；本轮未执行同步，历史 queued 任务保持原状；同步任务统一操作口径待人工确认`
- `current_data_boundary`: `正式版本截止 2026-07-24；覆盖 5,528 个截止日当前标的的生命周期、日交易状态和复权因子，并包含公司行动、三复权日线、交易日历与沪深300；2026-07-27 局部增量仅为未发布观察`
- `usage_boundary`: `非商用、本地研究；优先使用免费且可实现适配的数据接口，不把免费访问表述为授权或 SLA`
- `next_manual_approval`: `同步任务体系的统一方式与操作口径、数据中心升级阶段 D、阶段 87 独立因子实现、新增依赖、破坏性全量重建或商用边界变更需单独确认`
- `next_stage_entry`: `docs/architecture/data-center-upgrade-stage-c-implementation.md`
## 关键关注点

- `core_terms`:
- `量化分析`
- `本地化`
- `回测`
- `策略研究`
- `数据权限`
- `risks`:
- `金融场景结论误导风险`
- `数据来源与授权边界不清`
- `本地运行环境差异导致验证不稳定`

## 关键路径

- `key_paths`:
- `projects/SleeperCloudQuant/AGENTS.md`
- `projects/SleeperCloudQuant/manifest.md`
- `projects/SleeperCloudQuant/docs/decision-log/project-profile.md`
- `projects/SleeperCloudQuant/docs/verification/verification-baseline.md`
- `projects/SleeperCloudQuant/docs/code-archaeology/repository-map.md`
- `projects/SleeperCloudQuant/docs/architecture/reuse-integration-plan.md`
- `projects/SleeperCloudQuant/docs/architecture/stage-86-0-governance-product-freeze.md`
- `projects/SleeperCloudQuant/docs/interaction/stage-86-data-center-factor-mvp.md`
- `agents/orchestrator.md`
- `agents/domains/software-dev.md`
