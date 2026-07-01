# Phase 1 第八批正式回收：Reporting 实际下线候选清单

## 1. 评估目标

- 仅针对 `reporting phase1` 子图，形成第三批可执行的实际下线候选清单。
- 本轮不删除文件，只输出删除前确认单。

## 2. 评估范围

- `reporting/phase1_store_protocols.py`
- `reporting/phase1_run_results_reader.py`
- `reporting/phase1_replay_service.py`
- `reporting/phase1_batch_comparison_service.py`

## 3. 已确认事实

- `已确认`：`reporting/phase1.py` 当前只保留 9 个兼容别名：
  - `Phase1BacktestReplayDetail`
  - `Phase1BacktestRunDetail`
  - `Phase1BatchComparisonService`
  - `Phase1BatchExperimentRow`
  - `Phase1BatchExperimentSummary`
  - `Phase1ReplayRepository`
  - `Phase1ReplayService`
  - `Phase1ReportingStore`
  - `Phase1RunResultsReader`
- `已确认`：兼容入口导入检查通过，结果为 `reporting-phase1-compat-surface-ok`。
- `已确认`：代码区交叉检查未发现正式主路径继续引用本批 4 个深层文件。
- `已确认`：这 4 个文件当前剩余引用只存在于 `reporting phase1` 子图内部。
- `基于当前上下文推断`：如果没有仓外脚本直接导入这些深层文件，则它们已经具备进入整组删除评估的条件。

## 4. 逐文件候选判断

| 文件 | 当前角色 | 剩余引用情况 | 本轮判断 | 说明 |
| --- | --- | --- | --- | --- |
| `reporting/phase1_store_protocols.py` | phase1 子图基础协议 | 被 `phase1_run_results_reader.py`、`phase1_batch_comparison_service.py` 引用 | `需联动删除` | 不能单删，应和整个 reporting phase1 子图一起处理 |
| `reporting/phase1_run_results_reader.py` | phase1 reader 入口 | 被 `phase1_replay_service.py` 引用 | `需联动删除` | 建议与 store protocol、replay 一起处理 |
| `reporting/phase1_replay_service.py` | phase1 replay 入口 | 依赖 `phase1_run_results_reader.py` | `本轮可删除候选` | 正式 replay 服务已稳定 |
| `reporting/phase1_batch_comparison_service.py` | phase1 batch comparison 入口 | 依赖 `phase1_store_protocols.py` | `本轮可删除候选` | 正式 batch comparison 已稳定 |

## 5. 第一批建议删除分组

建议把 4 个文件作为同一组删除候选处理：

- `reporting/phase1_store_protocols.py`
- `reporting/phase1_run_results_reader.py`
- `reporting/phase1_replay_service.py`
- `reporting/phase1_batch_comparison_service.py`

原因：四者形成一个完整小闭环，整组删比单文件删更稳。

## 6. 本轮代码收束判断

- `已确认`：`reporting/phase1.py` 当前没有额外多余兼容别名，本轮无需再收紧。
- `已确认`：未发现需要额外改写到正式模块的残余活代码引用。
- `已确认`：因此本轮不需要再做代码修改，直接进入删除前确认阶段即可。

## 7. 删除前确认单

若进入真正删除，建议按以下顺序人工确认：

1. 是否同意把这 4 个文件整组删除，而不是单文件删除。
2. 是否接受删除后保留 `reporting/phase1.py` 兼容入口不变。
3. 是否接受 fake/demo 资产继续保留：
   - `reporting/phase1_fake_store.py`
   - `reporting/phase1_fake_store_demo.py`

## 8. 建议结论

- `已确认`：`reporting phase1` 子图已经具备进入第三批实际删除的条件。
- `待确认`：你是否批准执行这 4 个文件的真正删除动作。
