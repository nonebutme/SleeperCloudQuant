# phase-1-file-candidate-confirmation-round-1-backtest-kernel

## 1. 文档定位

- 目标：对 `backtest-kernel` 在第一阶段最小拼接范围内的候选文件做逐文件确认。
- 依据：
  - `docs/architecture/backtest-kernel-minimum-spec.md`
  - `docs/architecture/phase-1-stitching-plan.md`
  - `docs/architecture/phase-1-file-candidate-confirmation-plan.md`
- 范围：本轮只做候选确认，不做代码复制、拆解落库或目录级拼接执行。

## 2. 本轮检查来源

### 2.1 已检查仓库

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old`

### 2.2 本轮聚焦文件

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\backtest_gateway.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\data\ricequant\ricequant_backtest_adapter.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\strategy_backtest_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\backtest_results_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\stage_a_backtest_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\batch_backtest_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\single_security_backtest_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\backtest_replay_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\batch_backtest_analysis_service.py`

## 3. 最小能力回看

按当前已确认边界，`backtest-kernel` 第一阶段最小能力仅要求：

- 定义统一回测执行抽象
- 承接单次回测请求与结果对象
- 提供一个可替换的引擎适配层入口
- 为后续结果归档预留接缝

本阶段不要求直接纳入：

- 批量回测编排
- 单策略多标的聚合编排
- 回测结果分析大屏
- 回放展示层
- UI 页面视图模型

## 4. 逐文件确认结论

### 4.1 直接采纳候选

#### 4.1.1 `core/backtest_gateway.py`

- 结论：`直接采纳候选`
- 判断依据：
  - 已包含 `BacktestRequest`、`BacktestResult`、`BacktestGateway` 三个最小核心抽象。
  - 结构清晰，职责集中，基本不掺杂 UI、批量编排或读侧聚合逻辑。
  - 与当前 `backtest-kernel` 最小规格高度一致，可作为新项目统一回测入口协议。
- 采纳方式建议：
  - 优先整体吸收接口结构与数据对象定义。
  - 落地时只做命名、导入路径和模块边界适配，不先做语义扩写。

### 4.2 修改后采纳候选

#### 4.2.1 `data/ricequant/ricequant_backtest_adapter.py`

- 结论：`修改后采纳候选`
- 判断依据：
  - 该文件已经是 `BacktestGateway` 的具体实现，具备明显的适配层价值。
  - 但实现与 `RicequantClient`、特定配置结构、运行时回调和指标抽取强耦合。
  - 若直接搬入，会把外部运行时假设与旧项目依赖结构一并带入。
- 采纳方式建议：
  - 保留其“网关实现 + 配置拼装 + 结果提取”的骨架。
  - 拆出与具体运行时相关的配置转换、客户端调用、指标归一化逻辑。
  - 作为第一阶段 `rqalpha / ricequant` 兼容适配器的原型来源，而不是原样拼接。

#### 4.2.2 `core/services/strategy_backtest_service.py`

- 结论：`修改后采纳候选`
- 判断依据：
  - 该文件承接了单次策略回测的应用服务编排，是最接近“最小执行用例”的旧项目实现。
  - 但职责偏重，混合了参数校验、运行状态管理、仓储拼装、网关构造、策略装载与日志处理。
  - 若整体直接采纳，容易把第一阶段核心内核与应用层耦合在一起。
- 采纳方式建议：
  - 提炼其“单次回测 orchestrate 流程”作为用例参考。
  - 将请求校验、策略定位、运行记录写入、网关实例化拆为独立接缝。
  - 不建议原文件整体迁入新内核目录。

### 4.3 参考保留，不进入第一阶段最小内核

#### 4.3.1 `core/services/backtest_results_service.py`

- 结论：`参考保留`
- 判断依据：
  - 主要职责是读取已归档结果并组装指标、交易、持仓、账户、年度收益等读侧数据。
  - 更接近 `reporting` 或回测结果查询层，而非执行内核。
  - 可为后续结果查询接口设计提供字段参考，但不应并入最小回测执行主链路。

#### 4.3.2 `core/services/backtest_replay_service.py`

- 结论：`参考保留`
- 判断依据：
  - 该文件基于回测明细和行情历史构造回放数据集，属于结果消费层扩展能力。
  - 依赖 `MarketDataRepository` 与结果明细模型，不是回测执行的最小必要组成。
  - 可在后续 `reporting / replay` 子域再单独评估。

#### 4.3.3 `core/services/batch_backtest_analysis_service.py`

- 结论：`参考保留`
- 判断依据：
  - 面向批量实验的汇总、排序、年度收益对比，属于批量研究读侧。
  - 依赖结果表结构和研究实验元数据，超出第一阶段最小内核。
  - 适合作为后续实验分析层参考。

### 4.4 第一阶段排除候选

#### 4.4.1 `core/services/stage_a_backtest_service.py`

- 结论：`第一阶段排除`
- 判断依据：
  - 该文件偏向页面/阶段视图聚合服务。
  - 与最小执行内核直接关联度低，且容易把展示层概念提前带入。

#### 4.4.2 `core/services/batch_backtest_service.py`

- 结论：`第一阶段排除`
- 判断依据：
  - 该文件负责批量实验配置读取、实验计划展开、实验级元数据归档和循环执行。
  - 它依赖单次策略回测服务，属于“上层编排器”，不是最小内核本体。
  - 应在单次回测主链路稳定后再进入第二轮确认。

#### 4.4.3 `core/services/single_security_backtest_service.py`

- 结论：`第一阶段排除`
- 判断依据：
  - 该文件本质是“一个策略对多个标的”的聚合编排器。
  - 依赖结果汇总、聚合 run_id、研究运行元数据等附加机制。
  - 超出 `backtest-kernel` 第一阶段“单次回测最小闭环”的边界。

## 5. 当前归类汇总

### 5.1 直接采纳候选

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\backtest_gateway.py`

### 5.2 修改后采纳候选

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\data\ricequant\ricequant_backtest_adapter.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\strategy_backtest_service.py`

### 5.3 参考保留

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\backtest_results_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\backtest_replay_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\batch_backtest_analysis_service.py`

### 5.4 第一阶段排除

- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\stage_a_backtest_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\batch_backtest_service.py`
- `D:\Dev-AI\Dev\projects\SleeperCloudQuant-old\SleeperCloudQuant\core\services\single_security_backtest_service.py`

## 6. 与外部仓库的关系说明

- 本轮 `backtest-kernel` 候选确认暂未把 `backtrader-master`、`rqalpha-master` 作为直接拼接来源。
- 当前判断是：
  - `SleeperCloudQuant-old` 更适合提供“项目内现成抽象、接缝与应用服务骨架”。
  - `rqalpha-master` 更适合作为运行时行为与配置兼容的对照参考。
  - `backtrader-master` 更适合作为另一类回测引擎的设计参考，而不是第一阶段最小拼接源。

## 7. 下一步建议

- 下一轮优先进入 `config-center` 或 `reporting` 的逐文件候选确认。
- 若继续深化 `backtest-kernel`，建议下一步改做：
  - `candidate -> target module` 映射表
  - 单次回测最小调用链草图
  - 需要从 `strategy_backtest_service.py` 中拆出的最小职责清单

## 8. 状态标记

- 状态：`已确认（本轮候选归类层）`
- 未确认项：
  - 新项目最终模块命名
  - 结果归档表结构是否沿用旧项目 SQLite 设计
  - `rqalpha / ricequant` 适配器最终保留到何种抽象层级
