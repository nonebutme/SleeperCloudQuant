# SleeperCloudQuant Manifest

## 基本信息

- `project_name`: `SleeperCloudQuant`
- `project_type`: `local-quant-web-system`
- `current_stage`: `r3-standard-factor-research`
- `priority_goal`: `暂缓 R2 验收；完成三项标准因子实证研究，验证 A 股规律；保留 R1 数据限制及 2025 年后既有封存样本。`
- `r3_protocol`: `docs/requirements/r3-standard-factor-protocol.md`
- `r2_implementation`: `docs/architecture/r2-indicator-library.md`
- `r2_acceptance`: `docs/verification/r2-indicator-library-acceptance.md`
- `r1_implementation`: `docs/architecture/r1-data-maintenance-simplification.md`

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

- `user_start_entry`: `启动系统.cmd`
- `user_stop_entry`: `停止系统.cmd`
- `user_web_url`: `http://127.0.0.1:8010/`
- `internal_launch_chain`: `scripts/start_sleepercloudquant.ps1 -> scripts/run_formal_web_demo.py`
- `development_entries`: `纯 API 8000 与策略工作室候选 8020 仅限 --developer-mode 显式启动`

- `startup_bootstrap_script`: `python memory_system/project_bootstrap.py --write --input-file <payload.json>`
- `startup_query`: `R1 自动维护整改候选验证；历史阶段基线保留，正式数据及多问题修复尚未验收`
- `project_profile_path`: `projects/SleeperCloudQuant/docs/decision-log/project-profile.md`
- `verification_baseline_path`: `projects/SleeperCloudQuant/docs/verification/verification-baseline.md`
- `verification_report_template_path`: `projects/SleeperCloudQuant/docs/verification/verification-report-template.md`

## 项目约束

- `project_rules_source`: `projects/SleeperCloudQuant/AGENTS.md`
- `global_rules_source`: `AGENTS.md`
- `memory_scope`: `global_memory/projects/SleeperCloudQuant/`
- `log_scope`: `traces/task_logs.jsonl`


## 当前交付状态

- `latest_completed_stage`: `stage-91-0-91-3-source-quality-governance-verified`
- `latest_ui_iteration`: `factor-research-f0-f3-2026-08-12`
- `latest_factor_optimization`: `fa-opt-0-3-fixed-artifact-aligned-value-explicit-start-verified`
- `factor_optimization_entry`: `docs/architecture/fa-opt-0-3-factor-optimization.md`
- `latest_stage_four_factor_consumption`: `fixed-artifact-aligned-value-strategy-declaration-verified`
- `stage_four_factor_consumption_entry`: `docs/architecture/stage-4-factor-consumption-bridge.md`
- `current_release_judgment`: `阶段 91.0—91.3 专项与统一正式验证通过；配置有效性、能力探测、修复工单、覆盖版本、复检关闭和发布门禁已闭环。人工浏览器业务验收尚未执行，91.4 未启动。`
- `current_data_boundary`: `全局默认与最新 published 均为 scq-20260810-27cd5406fa3a12a9；raw/qfq/hfq 到 2026-08-10，交易状态/复权因子/公司行动到 2026-07-24，生命周期到 2026-07-16；研究按版本成员交集裁剪`
- `usage_boundary`: `非商用、本地研究；优先使用免费且可实现适配的数据接口，不把免费访问表述为授权或 SLA`
- `next_manual_approval`: `人工浏览器业务验收、91.4 启动、P2/P3 物理处置、正式指数事实导入、新增依赖或破坏性操作需单独确认`
- `next_stage_entry`: `docs/verification/stage-91-source-quality-governance-acceptance.md`
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
