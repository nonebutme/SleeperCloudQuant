# Memory Entry

## Basic

- `id`: mem-staging-sleepercloudquant-pitfall-governance-drift-001
- `type`: Pitfall
- `scope`: project:SleeperCloudQuant
- `status`: staging
- `summary`: 功能阶段持续推进而项目阶段、技术画像、数据模型和验证基线未同步，会导致调度、角色记录和发布判断失真。

## Content

- `rule`: 每个重要功能阶段收口时，必须同步核对 Manifest、项目画像、技术边界、数据模型、运行时说明、验证基线和阶段验收；发现漂移时应先完成治理对齐，再进入下一阶段实现。
- `context`: 项目功能已推进至统一回测工作台后，治理文档仍保留启动阶段和大量待确认模板，角色与记忆审计无法准确反映实际工程状态。
- `abstraction_note`: 保留项目范围，移除了具体文件行号、端口、提交号和一次性任务描述。

## Evidence

- `source`: stage-77.0-governance-audit
- `evidence`: 2026-07-25 对 Manifest、README、项目画像、架构文档、任务日志和当前代码的交叉核对。
- `timestamp`: 2026-07-25T09:30:00+08:00
- `confirm_count`: 1
- `retrieval_count`: 0

## Notes

- `notes`: stage77_governance_baseline_candidate | synced_to_root_staging | local_reference_only
