# SleeperCloudQuant Manifest

## 基本信息

- `project_name`: `SleeperCloudQuant`
- `project_type`: `local-quant-web-system`
- `current_stage`: `stage-77-governance-and-results-analysis`
- `priority_goal`: `在阶段 76.9 统一策略回测工作台基础上，先完成治理、角色与记忆闭环修复，再由用户重点确认“查看结果 / 查看分析”的业务口径和交互方案。`

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
- `startup_query`: `阶段 77 治理与策略回测结果/分析体验`
- `project_profile_path`: `projects/SleeperCloudQuant/docs/decision-log/project-profile.md`
- `verification_baseline_path`: `projects/SleeperCloudQuant/docs/verification/verification-baseline.md`
- `verification_report_template_path`: `projects/SleeperCloudQuant/docs/verification/verification-report-template.md`

## 项目约束

- `project_rules_source`: `projects/SleeperCloudQuant/AGENTS.md`
- `global_rules_source`: `AGENTS.md`
- `memory_scope`: `global_memory/projects/SleeperCloudQuant/`
- `log_scope`: `traces/task_logs.jsonl`


## 当前交付状态

- `latest_completed_stage`: `stage-76.9`
- `current_release_judgment`: `可继续迭代；全系统发布受 A 股行情新鲜度门禁阻断`
- `current_data_boundary`: `规范 A 股库最新交易日为 2026-07-17，需恢复新鲜度后重跑完整正式验证`
- `next_manual_approval`: `查看结果 / 查看分析的业务定义、信息层级与三模式差异`
- `next_stage_entry`: `docs/decision-log/stage-77-0-governance-baseline.md`
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
- `agents/orchestrator.md`
- `agents/domains/software-dev.md`
