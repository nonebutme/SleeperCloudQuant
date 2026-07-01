# Phase 1 第三批正式回收评估表

## 1. 评估范围

本次只评估以下深层 `phase1_*` 副本文件：

- `data_platform/repository/phase1_contracts.py`
- `data_platform/repository/phase1_cached_market_repository.py`
- `data_platform/storage/phase1_sqlite_metadata_store.py`
- `data_platform/providers/phase1_ricequant_repository.py`
- `data_platform/providers/phase1_ricequant_support.py`
- `data_platform/providers/phase1_connected_ricequant_repository.py`
- `backtest_kernel/gateway/phase1_contracts.py`
- `backtest_kernel/adapters/phase1_rqalpha_support.py`
- `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`
- `backtest_kernel/use_cases/phase1_run_single_backtest.py`
- `reporting/phase1_store_protocols.py`
- `reporting/phase1_run_results_reader.py`
- `reporting/phase1_replay_service.py`
- `reporting/phase1_batch_comparison_service.py`

## 2. 评估方法

- `已确认`：正式模块、正式包导出、`phase1.py` 兼容入口均已完成导入验证。
- `已确认`：本轮对 `data_platform / backtest_kernel / reporting / scripts` 四个代码区做了文本交叉引用检查，并排除了 `__pycache__` 影响。
- `已确认`：剩余深层 `phase1_*` 引用只存在于这些文件彼此之间，未发现正式主路径对它们的直接引用。
- `已确认`：14 个深层 `phase1_*` 模块仍可直接导入，说明它们目前是“自洽副本”，不是“主路径依赖”。
- `基于当前上下文推断`：后续人工或外部脚本是否会直接导入这些深层文件，当前仓内无法完全证明为零，因此删除动作仍建议单独确认。

## 3. 逐文件评估

| 文件 | 正式替代物 | 当前代码引用情况 | 状态标签 | 建议动作 | 风险说明 |
| --- | --- | --- | --- | --- | --- |
| `data_platform/repository/phase1_contracts.py` | `data_platform/repository/contracts.py` | 仅被 `phase1_cached_market_repository.py`、`phase1_ricequant_repository.py`、`phase1_connected_ricequant_repository.py` 引用 | `可直接停维护` | 不再继续更新；进入删除候选 | 删除前需同时处理依赖它的 phase1 数据平台副本 |
| `data_platform/repository/phase1_cached_market_repository.py` | `data_platform/repository/cached_market_repository.py` | 未被正式主路径引用；仅自带对 phase1 contract/store 的依赖 | `需兼容观察` | 保留观察一轮；后续可与其依赖一起整组下线 | 它是数据平台 phase1 子图的入口之一 |
| `data_platform/storage/phase1_sqlite_metadata_store.py` | `data_platform/storage/sqlite_metadata_store.py` | 未被正式验证脚本继续使用；仅被 `phase1_cached_market_repository.py` 引用 | `可直接停维护` | 不再维护；进入删除候选 | 删除需同步处理 phase1 cache wrapper |
| `data_platform/providers/phase1_ricequant_repository.py` | `data_platform/providers/ricequant_repository.py` | 无正式引用；自身仍是占位实现 | `可直接停维护` | 优先列为删除候选 | 本体仍是 `NotImplemented`，保留价值最低 |
| `data_platform/providers/phase1_ricequant_support.py` | `data_platform/providers/ricequant_repository.py` 内正式支持函数 | 仅被 `phase1_connected_ricequant_repository.py` 引用 | `可直接停维护` | 不再维护；作为整组删除候选 | 删除需同步处理其 phase1 connected repository |
| `data_platform/providers/phase1_connected_ricequant_repository.py` | `data_platform/providers/ricequant_repository.py` | 无正式引用；仅依赖 phase1 contract/support | `需兼容观察` | 保留观察一轮；后续整组下线 | 它是数据平台 phase1 provider 子图入口 |
| `backtest_kernel/gateway/phase1_contracts.py` | `backtest_kernel/gateway/contracts.py` | 仅被 `phase1_rqalpha_support.py`、`phase1_connected_rqalpha_gateway.py`、`phase1_run_single_backtest.py` 引用 | `可直接停维护` | 不再维护；进入删除候选 | 删除前需联动 phase1 backtest 子图 |
| `backtest_kernel/adapters/phase1_rqalpha_support.py` | `backtest_kernel/adapters/rqalpha_ricequant_gateway.py` | 仅被 `phase1_connected_rqalpha_gateway.py` 引用 | `可直接停维护` | 不再维护；进入删除候选 | 删除需联动 phase1 connected gateway |
| `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py` | `backtest_kernel/adapters/rqalpha_ricequant_gateway.py` | 无正式引用；仅依赖 phase1 contracts/support | `需兼容观察` | 保留观察一轮；后续整组下线 | 它是 backtest phase1 子图入口 |
| `backtest_kernel/use_cases/phase1_run_single_backtest.py` | `backtest_kernel/use_cases/run_single_backtest.py` | 无正式引用；仅依赖 phase1 contracts | `需兼容观察` | 保留观察一轮；后续整组下线 | 仍可能被人工直接当旧入口使用 |
| `reporting/phase1_store_protocols.py` | `reporting/store_protocols.py` | 仅被 `phase1_run_results_reader.py`、`phase1_batch_comparison_service.py` 引用 | `可直接停维护` | 不再维护；进入删除候选 | 删除前需联动 reporting phase1 子图 |
| `reporting/phase1_run_results_reader.py` | `reporting/run_results_reader.py` | 仅被 `phase1_replay_service.py` 引用 | `需兼容观察` | 保留观察一轮；后续整组下线 | 它是 reporting phase1 子图核心入口 |
| `reporting/phase1_replay_service.py` | `reporting/replay_service.py` | 无正式引用；仅依赖 `phase1_run_results_reader.py` | `可直接停维护` | 不再维护；进入删除候选 | 可与 reporting phase1 子图一起清退 |
| `reporting/phase1_batch_comparison_service.py` | `reporting/batch_comparison_service.py` | 无正式引用；仅依赖 `phase1_store_protocols.py` | `可直接停维护` | 不再维护；进入删除候选 | 可与 reporting phase1 子图一起清退 |

## 4. 汇总结论

### 4.1 已确认

- 当前仓内未发现正式主路径继续引用上述 14 个深层 `phase1_*` 文件。
- 它们当前的剩余依赖关系，已经缩成 3 个历史子图：
  - `data_platform phase1 子图`
  - `backtest_kernel phase1 子图`
  - `reporting phase1 子图`
- 这些文件现在更像“可独立导入的历史副本”，而不是“项目仍在使用的主实现层”。

### 4.2 状态统计

- `可直接停维护`：9 个
- `需兼容观察`：5 个
- `仍有间接引用风险`：0 个

### 4.3 建议的下一步顺序

1. 先继续保留文件，但明确停止对 `可直接停维护` 文件做任何同步更新。
2. 下一轮如果你同意，可以先从 `data_platform` 子图开始做第一批实际下线评估。
3. 真正删除时，建议按“子图整组删除”而不是“单文件零散删除”执行。

## 5. 发布判断

- `已确认`：第三批评估工作已完成。
- `待确认`：是否进入第四批，开始第一组 `phase1_*` 深层文件的实际下线候选处理。
