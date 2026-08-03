# Memory Entry

## Basic

- `id`: mem-staging-sleepercloudquant-pitfall-report-metric-evidence-integrity-001
- `type`: Pitfall
- `scope`: project:SleeperCloudQuant
- `status`: staging
- `summary`: 报告层可能把缺失值转换为零、把成交记录数当完整交易数，或因窄表持久化丢失费用与盈亏证据。

## Content

- `rule`: 报告指标必须区分缺失与零；交易次数必须按已实现交易口径计算并单列成交记录数；若规范化明细表未覆盖全部审计字段，应从不可变原始结果按顺序校验后恢复证据，不能用默认值伪补。
- `context`: 适用于回测报告、绩效面板、交易归因以及任何从运行明细投影到展示 DTO 的链路。
- `abstraction_note`: 去除具体指标数值和文件名，保留缺失值语义、事件口径与原始证据恢复三类稳定风险。

## Evidence

- `source`: stage-77-1-report-metric-integrity-fix
- `evidence`: 修复了 JavaScript Number(null)=0、成交条数回退、结果面板变量先用后定义，以及费用/已实现盈亏未进入窄表后在报告层丢失的问题；真实任务复算与五项专项回归通过。
- `timestamp`: 2026-07-26T21:30:00+08:00
- `confirm_count`: 1
- `retrieval_count`: 0

## Notes

- `notes`: verified_with_real_completed_runs | no_database_migration | local_staging_only