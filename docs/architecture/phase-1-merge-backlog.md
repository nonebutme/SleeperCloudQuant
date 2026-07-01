# phase-1-merge-backlog

## 1. 文档定位

- 目标：列出当前 `phase1_*` 实现层未来如何合并回正式骨架文件。
- 范围：只定义合并目标、顺序、风险和完成判断，不执行实际合并。
- 状态：`已确认（未来合并清单层）`

## 2. 背景说明

当前项目在 helper 不稳定的约束下，采用了“双层共存”策略：

- 正式骨架文件保留不动
- 第一阶段真实推进内容通过 `phase1_*` 文件落地

因此，后续一旦 helper 恢复稳定，需要把这些 `phase1_*` 文件逐步回收进正式骨架，避免长期并行维护两套结构。

## 3. 合并总原则

- 先验证，再合并
- 先低风险模块，再高耦合模块
- 先合并“协议与纯函数”，再合并“运行时接线”
- 合并完成后，应尽量减少重复出口和重复文件

## 4. 建议合并顺序

建议按以下顺序回收：

1. `config_center`
2. `data_platform`
3. `backtest_kernel`
4. `reporting`

原因：

- `config_center` 依赖最少，最容易稳定
- `data_platform` 是后两块的下游基础
- `backtest_kernel` 依赖配置与数据平台
- `reporting` 依赖结果结构和 store 协议，适合最后收口

## 5. 模块级合并清单

### 5.1 config_center

#### 当前正式骨架

- `config_center/providers/ricequant_config.py`
- `config_center/effective_settings_provider.py`
- `config_center/unified_config_manager.py`
- `config_center/models/runtime_settings.py`

#### 当前需要回收的内容

- 这一块目前没有额外 `phase1_*` 重复文件
- 当前已可直接视为第一阶段正式实现起点

#### 后续动作

- 保持现状
- 仅在 helper 恢复后补测试与统一导出

#### 合并判断

- `config_center` 当前可视为“已天然收束”

### 5.2 data_platform

#### 当前正式骨架

- `data_platform/repository/contracts.py`
- `data_platform/repository/cached_market_repository.py`
- `data_platform/storage/sqlite_metadata_store.py`
- `data_platform/providers/ricequant_repository.py`

#### 当前 phase1_* 实现层

- `data_platform/repository/phase1_contracts.py`
- `data_platform/repository/phase1_cached_market_repository.py`
- `data_platform/storage/phase1_sqlite_metadata_store.py`
- `data_platform/providers/phase1_ricequant_repository.py`
- `data_platform/providers/phase1_ricequant_support.py`
- `data_platform/providers/phase1_connected_ricequant_repository.py`
- `data_platform/phase1.py`

#### 未来合并目标

- `phase1_contracts.py` -> `repository/contracts.py`
- `phase1_cached_market_repository.py` -> `repository/cached_market_repository.py`
- `phase1_sqlite_metadata_store.py` -> `storage/sqlite_metadata_store.py`
- `phase1_ricequant_support.py` -> `providers/ricequant_repository.py` 或 `providers/ricequant_support.py`
- `phase1_connected_ricequant_repository.py` -> `providers/ricequant_repository.py`
- `phase1_ricequant_repository.py` 若仍仅为占位，可删除或并入兼容导出
- `phase1.py` -> 可改为兼容层或删除

#### 合并前置条件

- fake 或本地最小验证至少完成一轮
- SQLite cache 验证至少完成一轮

#### 合并风险

- `sqlite_metadata_store.py` 合并时最容易把“纯缓存职责”和“未来结果存储职责”混回一起
- `ricequant_repository.py` 合并时最容易出现 client 协议与正式实现重复

#### 合并完成判断

- 正式骨架文件已承载全部 phase-1 数据平台逻辑
- `phase1_*` 文件不再是主入口

### 5.3 backtest_kernel

#### 当前正式骨架

- `backtest_kernel/gateway/contracts.py`
- `backtest_kernel/adapters/rqalpha_ricequant_gateway.py`
- `backtest_kernel/use_cases/run_single_backtest.py`

#### 当前 phase1_* 实现层

- `backtest_kernel/gateway/phase1_contracts.py`
- `backtest_kernel/adapters/phase1_rqalpha_support.py`
- `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`
- `backtest_kernel/adapters/phase1_fake_runtime.py`
- `backtest_kernel/use_cases/phase1_run_single_backtest.py`
- `backtest_kernel/use_cases/phase1_fake_runtime_demo.py`
- `backtest_kernel/phase1.py`

#### 未来合并目标

- `phase1_contracts.py` -> `gateway/contracts.py`
- `phase1_rqalpha_support.py` -> `adapters/rqalpha_ricequant_gateway.py` 或 `adapters/rqalpha_support.py`
- `phase1_connected_rqalpha_gateway.py` -> `adapters/rqalpha_ricequant_gateway.py`
- `phase1_run_single_backtest.py` -> `use_cases/run_single_backtest.py`
- `phase1_fake_runtime.py` -> `tests/fakes/` 或 `scripts/demo/` 风格目录
- `phase1_fake_runtime_demo.py` -> `scripts/` 或 `tests/`
- `phase1.py` -> 兼容层或删除

#### 合并前置条件

- fake runtime 验证脚本至少执行一轮
- request -> payload -> result 链路确认可用

#### 合并风险

- gateway 合并时容易把“协议”和“具体 runtime 接线”重新耦合
- fake runtime 若留在正式适配目录，会让生产代码与演示资产混杂

#### 合并完成判断

- 正式 gateway 与用例文件已覆盖 phase-1 静态接线能力
- fake runtime 已迁到验证资产位置

### 5.4 reporting

#### 当前正式骨架

- `reporting/run_results_reader.py`
- `reporting/replay_service.py`
- `reporting/batch_comparison_service.py`

#### 当前 phase1_* 实现层

- `reporting/phase1_store_protocols.py`
- `reporting/phase1_run_results_reader.py`
- `reporting/phase1_replay_service.py`
- `reporting/phase1_batch_comparison_service.py`
- `reporting/phase1_fake_store.py`
- `reporting/phase1_fake_store_demo.py`
- `reporting/phase1.py`

#### 未来合并目标

- `phase1_store_protocols.py` -> `reporting/store_protocols.py` 或并入正式 reader 文件
- `phase1_run_results_reader.py` -> `run_results_reader.py`
- `phase1_replay_service.py` -> `replay_service.py`
- `phase1_batch_comparison_service.py` -> `batch_comparison_service.py`
- `phase1_fake_store.py` -> `tests/fakes/` 或 `scripts/demo/`
- `phase1_fake_store_demo.py` -> `scripts/` 或 `tests/`
- `phase1.py` -> 兼容层或删除

#### 合并前置条件

- fake reporting 验证脚本至少执行一轮
- run detail / chart / batch summary 至少完成一轮本地读侧验证

#### 合并风险

- reporting 合并时容易把 fake store 错留在正式模块目录
- store protocol 最终落位如果不明确，后续真实 store 接线会反复改动

#### 合并完成判断

- 正式 reporting 文件已承载 phase-1 读侧能力
- fake store 已迁到验证资产位置

## 6. 验证资产的未来去向

以下文件建议未来统一迁到“验证资产”区域，而不是保留在正式实现目录：

- `backtest_kernel/adapters/phase1_fake_runtime.py`
- `backtest_kernel/use_cases/phase1_fake_runtime_demo.py`
- `reporting/phase1_fake_store.py`
- `reporting/phase1_fake_store_demo.py`
- `scripts/verify_phase1_sqlite_cache.py`
- `scripts/verify_phase1_fake_runtime.py`
- `scripts/verify_phase1_fake_reporting.py`

建议未来落位方向：

- `tests/fakes/`
- `tests/integration/`
- 或 `scripts/demo/`

## 7. 合并后的清理清单

当正式骨架已完成回收后，应进行以下清理：

1. 删除不再需要的 `phase1.py` 聚合导出文件
2. 删除重复的 `phase1_*` 实现文件
3. 保留 fake 资产，但迁到测试/演示区域
4. 更新文档，把“helper fallback”状态改为历史记录

## 8. 建议的执行时机

只有在满足以下条件时，才建议真正执行合并：

- helper 能稳定更新既有文件
- 至少能稳定运行本地 Python 验证脚本
- 当前工作区没有与这些模块直接冲突的外部改动

## 9. 关联文档

- `docs/architecture/phase-1-static-wiring-summary.md`
- `docs/architecture/phase-1-batch-2-helper-fallback-note.md`
- `docs/architecture/phase-1-ricequant-wiring-note.md`
- `docs/architecture/phase-1-backtest-kernel-wiring-note.md`
- `docs/architecture/phase-1-reporting-wiring-note.md`
- `docs/architecture/phase-1-fake-assets-note.md`
- `docs/verification/phase-1-batch-2-verification-note.md`
- `docs/verification/phase-1-fake-assets-verification-note.md`
