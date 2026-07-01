# phase-1-execution-batch-plan

## 1. 文档定位

- 目标：把第一阶段最小拼接蓝图拆成可顺序执行的最小批次。
- 依据：
  - `docs/architecture/phase-1-candidate-to-target-module-mapping.md`
  - `docs/architecture/phase-1-stitching-plan.md`
  - `docs/architecture/backtest-kernel-minimum-spec.md`
  - `docs/architecture/data-platform-minimum-spec.md`
  - `docs/architecture/config-center-minimum-spec.md`
  - `docs/architecture/reporting-minimum-spec.md`
- 范围：本文件只定义实现批次、边界、依赖与验证目标，不直接执行代码修改。

## 2. 批次设计原则

- 每个批次都应形成可检查的中间状态
- 优先解决下游模块的阻塞依赖
- 尽量避免一个批次同时改动过多模块
- 第一阶段先做“能跑通的最小闭环”，不追求一次到位

## 3. 推荐执行批次

建议拆成 4 个主批次。

### Batch 1：配置与基础骨架落位

#### 目标

- 建立第一阶段四个目标模块的最小目录骨架
- 先落 `config-center` 的最小配置读取能力
- 为后续仓储、回测和 reporting 提供统一配置入口

#### 主要内容

- 建立目标模块骨架：
  - `config-center`
  - `data-platform`
  - `backtest-kernel`
  - `reporting`
- 引入并整理：
  - `ricequant_config`
  - `backtest_profiles`
- 定义最小配置模型或读取接口：
  - 数据源配置
  - 回测 profile 配置
  - 本地默认值与 env 覆盖关系

#### 主要来源

- `SleeperCloudQuant-old/data/ricequant/config.py`
- `SleeperCloudQuant-old/config/backtest_profiles.json`
- `TradingAgents-CN-main/app/services/config_provider.py`
- `TradingAgents-CN-main/app/core/unified_config.py`

#### 交付结果

- 新项目存在可调用的最小配置读取入口
- 能稳定读取本地回测 profile
- 能稳定读取 Ricequant 凭据配置

#### 已验证项

- 模块骨架已建立
- 配置入口已能加载静态 profile
- 配置入口已能识别 env / env-file

#### 未验证项

- 实际外部凭据可用性
- 后续 DB 型配置是否兼容

#### 风险

- 若一开始就引入完整 unified config，会把范围拉大
- 配置模型定义过重，会拖慢后续批次

### Batch 2：数据平台最小仓储闭环

#### 目标

- 建立最小 `data-platform`
- 形成“仓储抽象 + provider 实现 + 缓存存储”的最小闭环

#### 主要内容

- 落 `repository` 抽象
- 落 `cached_market_repository`
- 从 `sqlite_cache.py` 中裁剪出数据平台所需的 SQLite 能力
- 落 `ricequant_repository`
- 明确缓存层与 provider 层边界

#### 主要来源

- `SleeperCloudQuant-old/core/repository.py`
- `SleeperCloudQuant-old/data/cache/cached_market_data_repository.py`
- `SleeperCloudQuant-old/data/cache/sqlite_cache.py`
- `SleeperCloudQuant-old/data/ricequant/ricequant_repository.py`

#### 交付结果

- 新项目拥有最小仓储协议
- 可通过统一仓储接口读取或缓存行情/元数据
- provider 与缓存之间的职责边界清晰

#### 已验证项

- 仓储接口结构已落地
- SQLite 裁剪版元数据存储可初始化
- provider 实现能接入统一仓储抽象

#### 未验证项

- 全量历史数据质量
- 多 provider 切换逻辑

#### 风险

- `sqlite_cache.py` 混合职责较重，若裁剪不干净，会污染 reporting 和 backtest-kernel 边界
- provider 依赖旧项目路径时，容易出现隐性耦合

### Batch 3：单次回测执行最小闭环

#### 目标

- 建立 `backtest-kernel` 的最小单次回测执行闭环
- 能从配置与数据平台接缝进入回测网关

#### 主要内容

- 落 `BacktestRequest / BacktestResult / BacktestGateway`
- 落 `rqalpha / ricequant` 适配器骨架
- 从 `strategy_backtest_service.py` 中提炼单次回测用例
- 明确：
  - 请求校验
  - 网关实例化
  - 回测执行
  - 结果归档接缝

#### 主要来源

- `SleeperCloudQuant-old/core/backtest_gateway.py`
- `SleeperCloudQuant-old/data/ricequant/ricequant_backtest_adapter.py`
- `SleeperCloudQuant-old/core/services/strategy_backtest_service.py`

#### 交付结果

- 新项目可表达标准化单次回测请求
- 新项目拥有统一回测网关抽象
- 单次回测主链路具备最小可执行形态

#### 已验证项

- request/result/gateway 协议已落地
- 单次回测用例已能串联配置和仓储接缝
- 适配器能输出标准化结果对象

#### 未验证项

- 真实回测引擎运行稳定性
- 全部指标归档完整性

#### 风险

- `strategy_backtest_service.py` 若不拆细，会把太多外围职责直接带入
- 适配器层若与运行时耦合过重，后续切换引擎成本会升高

### Batch 4：结果读侧与基础 reporting 接入

#### 目标

- 建立 `reporting` 的单次回测结果读侧
- 让第一阶段最小闭环具备“执行后可读”的能力

#### 主要内容

- 落 `run_results_reader`
- 提供：
  - 回测详情读取
  - metrics 聚合
  - trades / positions / accounts / yearly_returns 读取
  - 基础图表数据结构
- 视情况后置：
  - replay
  - batch comparison

#### 主要来源

- `SleeperCloudQuant-old/core/services/backtest_results_service.py`
- `SleeperCloudQuant-old/core/services/backtest_replay_service.py`
- `SleeperCloudQuant-old/core/services/batch_backtest_analysis_service.py`

#### 交付结果

- 回测结果可被统一读取
- 基础图表数据结构可稳定输出
- 第一阶段最小闭环形成“可执行 + 可查询”

#### 已验证项

- 单次 run detail 可读取
- 图表数据结构已能输出
- reporting 与 backtest-kernel 边界保持清晰

#### 未验证项

- replay 是否立即进入第一阶段
- batch comparison 是否立即进入第一阶段

#### 风险

- 若过早加入 replay / batch comparison，会把第四批次范围拉大
- 若结果表结构仍混在数据平台层，读侧边界会再次模糊

## 4. 批次之间的依赖关系

### 4.1 依赖链

1. `Batch 1 -> Batch 2`
2. `Batch 2 -> Batch 3`
3. `Batch 3 -> Batch 4`

### 4.2 不建议并行的部分

- `Batch 2` 与 `Batch 4`
  - 因为都会牵涉 `sqlite` 存储边界，容易发生职责回流
- `Batch 1` 与 `Batch 3`
  - 因为回测执行入口应基于稳定配置定义，而不是反向推动配置模型

## 5. 每批次完成判断

### Batch 1 完成判断

- 已有稳定的配置入口
- profile 与 ricequant 配置读取已落位
- 不再依赖旧项目原始配置路径

### Batch 2 完成判断

- 已有统一仓储抽象
- provider 与缓存存储接缝已落位
- SQLite 裁剪边界已明确

### Batch 3 完成判断

- 已有单次回测请求与结果协议
- 已有统一网关入口
- 已有最小单次回测用例

### Batch 4 完成判断

- 已能读取单次回测结果详情
- 已能构造基础图表数据
- reporting 未重新侵入执行内核

## 6. 建议的实现节奏

推荐节奏如下：

1. 先完成 `Batch 1`
2. 完成后人工确认模块骨架与配置边界
3. 再进入 `Batch 2`
4. `Batch 2` 完成后再次做一次交叉一致性检查
5. 然后进入 `Batch 3`
6. 最后再接 `Batch 4`

## 7. 当前建议的启动批次

如果你现在确认进入真实实现，建议从 `Batch 1` 开始，而不是直接碰回测执行代码。

原因很简单：

- 这是最低风险入口
- 能最快形成可审查的结构性成果
- 一旦 `config-center` 和模块骨架稳定，后面三批都会顺很多

## 8. 状态标记

- 状态：`已确认（执行批次规划层）`
- 未确认项：
  - 物理目录是否按本文命名直接创建
  - replay 与 batch comparison 是否纳入第一阶段末尾
  - 每批次完成后是否都要求人工确认再进入下一批
