# SleeperCloudQuant Manifest

## 基本信息

- `project_name`: `SleeperCloudQuant`
- `project_type`: `local-quant-web-system`
- `current_stage`: `startup-bootstrap`
- `priority_goal`: `先完成本地化量化分析系统的项目画像、边界澄清与最小验证基线，再进入真实开发。`

## 业务属性

- `industry`: `量化分析 / 金融科技`
- `product_shape`: `本地化 Web 分析系统`
- `target_users`:
- 量化研究人员
- 交易分析人员

## 技术属性

- `primary_lang`: `待确认`
- `secondary_langs`:
- `待确认`
- `framework`: `待确认`
- `runtime`: `待确认`
- `database`: `待确认`

## 路由属性

- `allowed_domains`:
- `software-dev`
- `default_domain`: `software-dev`
- `requires_business_review`: `true`
- `requires_mvp_approval_before_deep_build`: `true`

## 复用属性

- `reference_projects`:
- `待确认`
- `reuse_policy`: `先考古评估，再决定自研 / 复用 / 局部提取`
- `code_archaeology_report_path`: `projects/SleeperCloudQuant/docs/code-archaeology/repository-map.md`
- `multi_repo_comparison_path`: `projects/SleeperCloudQuant/docs/code-archaeology/repo-comparison.md`
- `reuse_integration_plan_path`: `projects/SleeperCloudQuant/docs/architecture/reuse-integration-plan.md`

## 启动属性

- `startup_bootstrap_script`: `python memory_system/project_bootstrap.py --write --input-file <payload.json>`
- `startup_query`: `量化分析 / 金融科技 本地化 Web 分析系统 待确认`
- `project_profile_path`: `projects/SleeperCloudQuant/docs/decision-log/project-profile.md`
- `verification_baseline_path`: `projects/SleeperCloudQuant/docs/verification/verification-baseline.md`
- `verification_report_template_path`: `projects/SleeperCloudQuant/docs/verification/verification-report-template.md`

## 项目约束

- `project_rules_source`: `projects/SleeperCloudQuant/AGENTS.md`
- `global_rules_source`: `AGENTS.md`
- `memory_scope`: `global_memory/projects/SleeperCloudQuant/`
- `log_scope`: `traces/task_logs.jsonl`

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
