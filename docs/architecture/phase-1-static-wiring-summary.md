# phase-1-static-wiring-summary

## 1. 文档定位

- 目标：汇总当前项目中已落地的 `phase1_*` 静态接线层。
- 范围：仅覆盖当前已经新增的 phase-1 实现层、边界、限制与后续收束方向。
- 状态：`已确认（静态接线汇总层）`

## 2. 当前总体结论

在当前 helper 不稳定、无法可靠更新既有文件与执行本地命令的约束下，项目已经形成了一套可持续推进的保守实现方式：

- 保留原始骨架文件不动
- 通过新增 `phase1_*` 文件承载第一阶段真实实现层
- 先把四块主模块的“静态接线”做出来
- 等 helper 稳定后，再统一回收合并到正式骨架

这意味着当前代码库里已经同时存在两层：

- `骨架层`：早期新增的最小占位文件
- `phase1_* 实现层`：当前真正承载第一阶段推进成果的静态接线文件

## 3. 已落地模块汇总

### 3.1 config_center

#### 当前已落地

- `config_center/providers/ricequant_config.py`
- `config_center/effective_settings_provider.py`
- `config_center/unified_config_manager.py`
- `config_center/models/runtime_settings.py`
- `config_center/profiles/backtest_profiles.json`

#### 当前能力

- 读取 Ricequant 凭据配置
- 支持 env / env-file 读取方式
- 提供最小有效配置合并入口
- 提供 phase-1 的静态 backtest profile

#### 当前限制

- 尚未进入 DB 型配置中心
- 尚未统一更多 provider 配置

### 3.2 data_platform

#### 当前骨架层

- `data_platform/repository/contracts.py`
- `data_platform/repository/cached_market_repository.py`
- `data_platform/storage/sqlite_metadata_store.py`
- `data_platform/providers/ricequant_repository.py`

#### 当前 phase1_* 实现层

- `data_platform/phase1.py`
- `data_platform/repository/phase1_contracts.py`
- `data_platform/repository/phase1_cached_market_repository.py`
- `data_platform/storage/phase1_sqlite_metadata_store.py`
- `data_platform/providers/phase1_ricequant_repository.py`
- `data_platform/providers/phase1_ricequant_support.py`
- `data_platform/providers/phase1_connected_ricequant_repository.py`

#### 当前能力

- 已定义旧项目风格的 phase-1 市场数据仓储协议
- 已落地 cache-first 仓储包装层
- 已落地仅含 `market_data_cache` 的 SQLite 存储实现
- 已定义 Ricequant client 协议
- 已定义数据归一化函数
- 已定义可注入 client 的 repository

#### 当前限制

- 未接真实 Ricequant SDK
- 未做 provider 运行验证
- 骨架层与实现层尚未合并

### 3.3 backtest_kernel

#### 当前骨架层

- `backtest_kernel/gateway/contracts.py`
- `backtest_kernel/adapters/rqalpha_ricequant_gateway.py`
- `backtest_kernel/use_cases/run_single_backtest.py`

#### 当前 phase1_* 实现层

- `backtest_kernel/phase1.py`
- `backtest_kernel/gateway/phase1_contracts.py`
- `backtest_kernel/adapters/phase1_rqalpha_support.py`
- `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`
- `backtest_kernel/use_cases/phase1_run_single_backtest.py`

#### 当前能力

- 已定义 phase-1 backtest request / result / gateway 协议
- 已定义 runtime payload 构建逻辑
- 已定义 runtime 结果归一化逻辑
- 已定义可注入 runtime 的 gateway
- 已定义单次回测用例接线层

#### 当前限制

- 未接真实 rqalpha runtime
- 未做执行验证
- 未接结果落库

### 3.4 reporting

#### 当前骨架层

- `reporting/run_results_reader.py`
- `reporting/replay_service.py`
- `reporting/batch_comparison_service.py`

#### 当前 phase1_* 实现层

- `reporting/phase1.py`
- `reporting/phase1_store_protocols.py`
- `reporting/phase1_run_results_reader.py`
- `reporting/phase1_replay_service.py`
- `reporting/phase1_batch_comparison_service.py`

#### 当前能力

- 已定义 reporting 所需最小 store 协议
- 已定义单次 run detail 聚合逻辑
- 已定义 account / trade / position / yearly-return 图表数据构造
- 已定义 replay 读侧接线
- 已定义 batch comparison 读侧接线

#### 当前限制

- 未接真实结果存储实现
- 未做读侧验证
- 未暴露 API 或页面层

## 4. 当前目录策略说明

当前实际采用的是“双层共存”策略：

- 第一层：保留骨架，占住未来正式落位路径
- 第二层：通过 `phase1_*` 文件继续推进真实静态实现

这样做的原因不是偏好，而是当前 helper 的客观限制：

- `新增文件` 相对稳定
- `更新已有文件` 高概率失败
- `执行本地命令` 也不稳定

因此这是一个风险最小、可持续推进的工程折中方案。

## 5. 当前可视为“已完成静态接线”的部分

以下事项可以视为本轮已完成：

- 四块主模块的第一阶段结构都已落盘
- 四块主模块都已有对应 `phase1_*` 接线层
- `config_center -> data_platform -> backtest_kernel -> reporting` 的静态边界已基本成型
- `reporting` 作为只读侧消费层的边界已保持清晰

## 6. 当前仍不能表述为“已验证通过”的部分

以下事项当前不能表述为已验证通过：

- SQLite 缓存脚本实际运行结果
- Ricequant provider 外部连接
- rqalpha runtime 执行链路
- reporting 对真实 backtest 结果表的读取效果

原因不是设计未完成，而是运行环境/helper 不稳定，无法可靠执行本地命令或回写更新。

## 7. 后续收束建议

### 7.1 若 helper 恢复稳定

建议按以下顺序收束：

1. 先执行本地最小验证脚本
2. 再把 `phase1_*` 实现合并回正式骨架文件
3. 再删除重复壳子或改为兼容导出
4. 最后补统一入口与测试

### 7.2 若 helper 继续不稳定

建议继续保持当前策略：

1. 不更新既有文件
2. 只新增 `phase1_*` 实现文件
3. 只做静态接线、fake store、fake runtime、文档收束

## 8. 下一步建议

基于当前状态，下一步有两条安全路线：

### 8.1 保守路线

- 补 `fake runtime` 与 `fake reporting store` 的静态验证资产
- 不依赖外部环境，继续完善本地可验证链路

### 8.2 收束路线

- 先停止铺新代码
- 做一份 `phase1_* -> 正式骨架` 的未来合并清单
- 等 helper 稳定后再统一回收

## 9. 关联文档

- `docs/architecture/phase-1-batch-2-helper-fallback-note.md`
- `docs/architecture/phase-1-ricequant-wiring-note.md`
- `docs/architecture/phase-1-backtest-kernel-wiring-note.md`
- `docs/architecture/phase-1-reporting-wiring-note.md`
- `docs/verification/phase-1-batch-2-verification-note.md`
