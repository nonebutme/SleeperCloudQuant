# Phase 1 第二批正式回收后的 `phase1_*` 待下线清单

## 1. 目的

- 记录当前仍保留的 `phase1_*` 资产。
- 区分哪些已降级为兼容层，哪些仍是验证专用资产，哪些后续可以进入删除评估。
- 本清单只做状态标记，本轮不删除、不移动任何文件。

## 2. 当前判断口径

- `已确认`：正式模块已可直接导入，且本地验证主路径已切到正式入口。
- `待确认`：是否在下一轮删除或迁移，仍需人工确认。
- `基于当前上下文推断`：当前项目尚未形成正式 `tests/` 目录，因此 fake/demo 资产暂继续原位保留。

## 3. 分类清单

### 3.1 兼容保留

这些文件不再承载主实现，已改为兼容转发层，用于降低旧引用的切换成本。

- `data_platform/phase1.py`
- `backtest_kernel/phase1.py`
- `reporting/phase1.py`

### 3.2 验证专用

这些文件仍为本地最小验证链提供 fake/demo 支撑，但验证主路径已转到正式模块。

- `backtest_kernel/adapters/phase1_fake_runtime.py`
- `backtest_kernel/use_cases/phase1_fake_runtime_demo.py`
- `reporting/phase1_fake_store.py`
- `reporting/phase1_fake_store_demo.py`
- `scripts/verify_phase1_fake_runtime.py`
- `scripts/verify_phase1_fake_reporting.py`
- `scripts/verify_phase1_sqlite_cache.py`
- `scripts/run_phase1_verifications.py`

### 3.3 后续可下线评估

这些文件对应的正式实现已经回收到正式入口，当前继续保留仅用于兼容观察期或人工对照。

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

## 4. 下一轮建议

- 先做一次面向兼容入口的导入回归，确认旧调用不会立刻断裂。
- 再按模块分批评估 `3.3` 清单中的文件是否可以停止维护。
- 若要真正删除，应先补一份删除影响说明并单独人工确认。
