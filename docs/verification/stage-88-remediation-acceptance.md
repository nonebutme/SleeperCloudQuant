# 阶段 88 验收记录

## 已验证项

- 历史质量复检：33,172,283 行，3 条规则，0 个问题，状态 `passed`。
- 历史质量问题：13 条 `corrected`、1 条 `rejected`，无开放/隔离问题。
- 默认数据版本：`scq-20260810-27cd5406fa3a12a9`，质量报告与 9 个版本成员均为 `passed`。
- 统一版本解析：全局默认选择、显式版本复现、成员缺失和质量失败门禁通过测试。
- 指数权威表：快照替换、旧开放区间闭合、历史日期解析和只读委托通过测试。
- 因子制品：自动发布、内容寻址、幂等、不可变约束、列表/详情 API 通过测试。
- 策略桥梁：`factor_values` 目录、因子依赖声明、创建时冻结、同日值注入和证据输出通过测试。
- 三类回测：单品种、独立账户批量、投资组合均具备创建时数据版本冻结；后两类原有回归通过。
- 报告可信度：因子报告、模式报告和高级回测报告的结构化披露及页面常驻提示通过测试。

## 已执行的定向验证

- `smoke_test_stage86_data_center.py`
- `smoke_test_stage86_data_center_ui.py`
- `smoke_test_stage87_factor_research_core.py`
- `smoke_test_stage87_factor_research_api.py`
- `smoke_test_stage87_factor_research_ui.py`
- `smoke_test_stage88_integrity_bridge.py`
- 统一正式验证：`scripts/run_formal_verifications.py`，最终退出码 0，输出 `[formal] all verifications passed`。
- 运行态 HTTP：未授权指数同步返回 400；指数覆盖返回 `unavailable/index_component_facts_unavailable`；因子制品列表返回 `ready`。
- `smoke_test_strategy_datasets.py`
- `smoke_test_backtest_mode_reports.py`
- `smoke_test_stage80_85_advanced_reports.py`

以上定向测试均已通过。

## 未验证项

- 三个正式指数快照的生产落库及真实指数池研究任务。
- 浏览器人工视觉验收。
- 模拟盘或实盘有效性验证。

## 阻塞原因

- 外部指数成分的来源授权及本地落库许可尚未获得人工确认；因此不执行真实导入。

## 潜在风险

- 公开接口字段、可用性和使用条款可能变化。
- 当前快照不能证明快照日期以前的历史成员关系。
- 历史回测与因子统计不能证明未来收益；市场冲击和排队成交未被完整建模。

## 发布判断

- 阶段 88 项目内代码候选：通过。
- 全 A/自选池“因子创建 → 分析 → 制品 → 策略消费”：可用。
- 正式三指数池：数据授权门禁阻塞，保持不可用，不影响其他研究路径。
- 统一正式验证已通过（`scripts/run_formal_verifications.py`，退出码 0，最终输出 `[formal] all verifications passed`）；全系统正式发布仍需用户执行浏览器/业务验收。

