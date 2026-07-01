# phase-1-candidate-to-target-module-mapping

## 1. 文档定位

- 目标：把第一阶段已确认的候选文件，映射到新项目的目标模块与落位方式。
- 依据：
  - `docs/architecture/phase-1-file-candidate-confirmation-round-1-data-platform.md`
  - `docs/architecture/phase-1-file-candidate-confirmation-round-1-backtest-kernel.md`
  - `docs/architecture/phase-1-file-candidate-confirmation-round-1-config-center.md`
  - `docs/architecture/phase-1-file-candidate-confirmation-round-1-reporting.md`
- 范围：本文件只定义“应该落到哪里、以什么方式落”，不执行实际代码拼接。

## 2. 目标模块总览

基于当前保守型路线，第一阶段建议收束为以下目标模块：

- `config-center`
- `data-platform`
- `backtest-kernel`
- `reporting`

建议保持的关系如下：

- `config-center`：负责配置读取、默认值、优先级与最小校验
- `data-platform`：负责行情/元数据仓储、缓存、提供器接缝
- `backtest-kernel`：负责单次回测执行抽象与引擎适配
- `reporting`：负责回测结果读侧、图表数据与扩展查询

## 3. 映射原则

- `直接采纳候选`：优先整体吸收结构，只做命名、导入路径和边界适配
- `修改后采纳候选`：保留职责骨架，拆出旧项目耦合点后再重组
- `参考保留`：只提炼接口、字段、流程或排序逻辑，不直接迁入
- `第一阶段排除`：不进入当前第一阶段拼接蓝图

## 4. 候选文件到目标模块映射

### 4.1 config-center

| 来源文件 | 归类 | 目标模块 | 建议落位 | 处理方式 |
| --- | --- | --- | --- | --- |
| `SleeperCloudQuant-old/data/ricequant/config.py` | 直接采纳候选 | `config-center` | `config-center/providers/ricequant_config` | 保留 env / env-file / 别名键 / 缺失报错结构 |
| `SleeperCloudQuant-old/config/backtest_profiles.json` | 直接采纳候选 | `config-center` | `config-center/profiles/backtest_profiles` | 先作为静态 profile 样本保留 |
| `TradingAgents-CN-main/app/services/config_provider.py` | 修改后采纳候选 | `config-center` | `config-center/effective_settings_provider` | 抽取“优先级合并 + TTL 缓存 + 失效”模式，去掉 DB 强依赖 |
| `TradingAgents-CN-main/app/models/config.py` | 修改后采纳候选 | `config-center` | `config-center/models/runtime_settings` | 只提炼 data-source / runtime 的最小模型字段 |
| `TradingAgents-CN-main/app/core/unified_config.py` | 修改后采纳候选 | `config-center` | `config-center/unified_config_manager` | 只吸收统一入口、文件缓存、兼容映射骨架 |
| `SleeperCloudQuant-old/cbx_config.json` | 第一阶段排除 | - | - | 不纳入业务配置中心 |

### 4.2 data-platform

| 来源文件 | 归类 | 目标模块 | 建议落位 | 处理方式 |
| --- | --- | --- | --- | --- |
| `SleeperCloudQuant-old/core/repository.py` | 直接采纳候选 | `data-platform` | `data-platform/repository/contracts` | 作为仓储抽象主入口保留 |
| `SleeperCloudQuant-old/data/cache/cached_market_data_repository.py` | 直接采纳候选 | `data-platform` | `data-platform/repository/cached_market_repository` | 保留缓存包装层骨架 |
| `SleeperCloudQuant-old/data/cache/sqlite_cache.py` | 修改后采纳候选 | `data-platform` | `data-platform/storage/sqlite_metadata_store` | 拆掉混合 backtest 结果表职责，只保留数据平台所需部分 |
| `SleeperCloudQuant-old/data/ricequant/ricequant_repository.py` | 修改后采纳候选 | `data-platform` | `data-platform/providers/ricequant_repository` | 保留 provider 仓储实现，重做依赖注入与边界适配 |
| `TradingAgents-CN-main/tradingagents/dataflows/providers/base_provider.py` | 参考保留 | `data-platform` | `data-platform/provider_contracts_reference` | 仅参考 provider 抽象层级 |
| `TradingAgents-CN-main/app/services/data_sources/base.py` | 参考保留 | `data-platform` | `data-platform/provider_adapter_reference` | 仅参考 adapter 接口组织 |
| `TradingAgents-CN-main/app/services/data_sources/manager.py` | 参考保留 | `data-platform` | `data-platform/provider_priority_reference` | 仅参考优先级和切换逻辑 |
| `TradingAgents-CN-main/tradingagents/dataflows/data_source_manager.py` | 参考保留 | `data-platform` | `data-platform/orchestration_reference` | 仅参考更重的 manager 形态 |

### 4.3 backtest-kernel

| 来源文件 | 归类 | 目标模块 | 建议落位 | 处理方式 |
| --- | --- | --- | --- | --- |
| `SleeperCloudQuant-old/core/backtest_gateway.py` | 直接采纳候选 | `backtest-kernel` | `backtest-kernel/gateway/contracts` | 保留 request / result / gateway 三元抽象 |
| `SleeperCloudQuant-old/data/ricequant/ricequant_backtest_adapter.py` | 修改后采纳候选 | `backtest-kernel` | `backtest-kernel/adapters/rqalpha_ricequant_gateway` | 保留网关实现骨架，拆出运行时强耦合逻辑 |
| `SleeperCloudQuant-old/core/services/strategy_backtest_service.py` | 修改后采纳候选 | `backtest-kernel` | `backtest-kernel/use_cases/run_single_backtest` | 提炼单次回测 orchestrate 流程，不整体迁入 |
| `SleeperCloudQuant-old/core/services/backtest_results_service.py` | 参考保留 | `reporting` | `reporting/run_results_reader` | 从内核中移出，交给 reporting |
| `SleeperCloudQuant-old/core/services/backtest_replay_service.py` | 参考保留 | `reporting` | `reporting/replay_service` | 作为 reporting 扩展，不放入 kernel |
| `SleeperCloudQuant-old/core/services/batch_backtest_analysis_service.py` | 参考保留 | `reporting` | `reporting/batch_comparison_service` | 作为 reporting 扩展，不放入 kernel |
| `SleeperCloudQuant-old/core/services/stage_a_backtest_service.py` | 第一阶段排除 | - | - | 页面聚合层，不进最小内核 |
| `SleeperCloudQuant-old/core/services/batch_backtest_service.py` | 第一阶段排除 | - | - | 属于上层批量编排器 |
| `SleeperCloudQuant-old/core/services/single_security_backtest_service.py` | 第一阶段排除 | - | - | 属于上层聚合编排器 |

### 4.4 reporting

| 来源文件 | 归类 | 目标模块 | 建议落位 | 处理方式 |
| --- | --- | --- | --- | --- |
| `SleeperCloudQuant-old/core/services/backtest_results_service.py` | 直接采纳候选 | `reporting` | `reporting/run_results_reader` | 作为单次回测结果读侧核心服务 |
| `SleeperCloudQuant-old/core/services/backtest_replay_service.py` | 修改后采纳候选 | `reporting` | `reporting/replay_service` | 作为结果回放扩展服务 |
| `SleeperCloudQuant-old/core/services/batch_backtest_analysis_service.py` | 修改后采纳候选 | `reporting` | `reporting/batch_comparison_service` | 作为批量实验对比扩展服务 |
| `SleeperCloudQuant-old/core/services/stage_a_backtest_service.py` | 参考保留 | `reporting` | `reporting/dashboard_summary_reference` | 仅参考 dashboard summary 组织方式 |
| `TradingAgents-CN-main/app/utils/report_exporter.py` | 参考保留 | `reporting` | `reporting/export_reference` | 仅参考导出机制，不进入第一阶段主链路 |
| `TradingAgents-CN-main/app/routers/reports.py` | 参考保留 | `reporting` | `reporting/api_reference` | 仅参考列表/详情 API 结构 |

## 5. 模块间拼接顺序建议

建议第一阶段按以下顺序推进：

1. `config-center`
2. `data-platform`
3. `backtest-kernel`
4. `reporting`

排序理由：

- `config-center` 先行，能先稳定配置读取和默认值来源
- `data-platform` 其次，能先建立仓储与缓存接缝
- `backtest-kernel` 依赖前两者才能形成最小执行闭环
- `reporting` 最后接入，避免先做读侧而主链路未稳

## 6. 第一阶段最小落地包

若严格控制范围，第一阶段建议只纳入以下“最小落地包”：

### 6.1 必选

- `config-center/providers/ricequant_config`
- `config-center/profiles/backtest_profiles`
- `data-platform/repository/contracts`
- `data-platform/repository/cached_market_repository`
- `data-platform/storage/sqlite_metadata_store`（裁剪版）
- `data-platform/providers/ricequant_repository`
- `backtest-kernel/gateway/contracts`
- `backtest-kernel/adapters/rqalpha_ricequant_gateway`
- `backtest-kernel/use_cases/run_single_backtest`
- `reporting/run_results_reader`

### 6.2 可后置扩展

- `config-center/effective_settings_provider`
- `config-center/unified_config_manager`
- `reporting/replay_service`
- `reporting/batch_comparison_service`

### 6.3 当前不进入第一阶段

- dashboard view-model
- batch orchestrator
- single-security aggregate orchestrator
- 富文本导出系统
- reports Web API

## 7. 风险与注意点

- `sqlite_cache.py` 当前是混合职责文件，不能原样迁入，必须拆分。
- `strategy_backtest_service.py` 当前是重应用服务，若不拆分会把内核与外围编排耦合。
- `TradingAgents-CN-main` 的配置体系明显偏大，第一阶段只能借鉴模式，不能整包拼接。
- `reporting` 与 `backtest-kernel` 的边界要持续保持清晰，避免结果读侧重新回流到执行内核。

## 8. 下一步建议

基于当前映射表，下一步建议进入以下其一：

### 8.1 保守优先

- 产出 `phase-1 module skeleton plan`
- 把四个目标模块再细化成“文件级骨架清单”

### 8.2 稍进一步

- 产出 `phase-1 dependency cut plan`
- 明确哪些旧项目耦合点必须先拆

### 8.3 真正进入实现前最后一步

- 产出 `phase-1 execution batch plan`
- 把实现顺序拆成 3 到 5 个最小可提交批次

## 9. 状态标记

- 状态：`已确认（映射层）`
- 未确认项：
  - 新项目最终物理目录命名
  - SQLite 元数据与回测结果表是否同库存放
  - reporting 是否在第一阶段就暴露 API
