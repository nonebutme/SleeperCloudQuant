# phase-1-backtest-kernel-merge-patch-plan

## 1. 文档定位

- 目标：把 `backtest_kernel` 第一批正式回收所需的逐文件 patch 计划写清楚。
- 范围：只覆盖 `backtest_kernel` 正式骨架回收。
- 状态：`已确认（逐文件 patch 计划层）`

## 2. 本计划对应的正式目标文件

- `backtest_kernel/gateway/contracts.py`
- `backtest_kernel/adapters/rqalpha_ricequant_gateway.py`
- `backtest_kernel/use_cases/run_single_backtest.py`

## 3. 本计划对应的来源文件

- `backtest_kernel/gateway/phase1_contracts.py`
- `backtest_kernel/adapters/phase1_rqalpha_support.py`
- `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`
- `backtest_kernel/use_cases/phase1_run_single_backtest.py`

## 4. 文件级 patch 计划

### 4.1 `gateway/contracts.py`

#### 当前目标

- 用 phase-1 已验证协议替换当前较早期的最小骨架版本。

#### 应替换内容

- 保留三类核心对象：
  - `BacktestRequest`
  - `BacktestResult`
  - `BacktestGateway`

- 对齐字段结构：
  - `run_id`
  - `strategy_name`
  - `start_date`
  - `end_date`
  - `benchmark`
  - `initial_cash`
  - `frequency`
  - `strategy_callbacks`
  - `parameters`
  - `extra_config`
  - `progress_callback`

- `BacktestResult` 保持：
  - `metrics`
  - `raw_result`

#### 合并来源

- `backtest_kernel/gateway/phase1_contracts.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- 静态导入 `BacktestRequest / BacktestResult / BacktestGateway`

### 4.2 `adapters/rqalpha_ricequant_gateway.py`

#### 当前目标

- 让正式 gateway 文件具备 phase-1 的最小 injectable runtime 接线能力。

#### 应替换/新增内容

- 引入 `RicequantConfig`
- 引入 runtime 协议定义或等价支撑结构
- 引入：
  - payload 构建函数
  - runtime 结果归一化函数
  - `_require_runtime()`

- 正式 gateway 需支持：
  - `runtime: ... | None = None`
  - 在未注入 runtime 时给出明确 `NotImplementedError`

#### 当前阶段不引入

- 真实 rqalpha / ricequant runtime 构造
- 外部登录逻辑
- 真实回测引擎初始化参数细节

#### 合并来源

- `backtest_kernel/adapters/phase1_rqalpha_support.py`
- `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- fake runtime 链路仍通过

### 4.3 `use_cases/run_single_backtest.py`

#### 当前目标

- 让正式单次回测用例文件与 phase-1 已验证用例对齐。

#### 应替换内容

- 保留或对齐：
  - `RunSingleBacktestRequest`
  - `RunSingleBacktest`

- 让 `execute()`：
  - 构造正式 `BacktestRequest`
  - 注入 `symbol` 到 `parameters`
  - 调用正式 gateway

#### 当前阶段不引入

- 真实结果落库
- 复杂状态机
- 额外日志系统

#### 合并来源

- `backtest_kernel/use_cases/phase1_run_single_backtest.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- fake runtime demo 仍通过

## 5. 推荐执行顺序

建议执行顺序固定为：

1. `gateway/contracts.py`
2. `adapters/rqalpha_ricequant_gateway.py`
3. `use_cases/run_single_backtest.py`

原因：

- 先统一协议
- 再统一 gateway 接线
- 最后统一上层用例

## 6. 每一步执行后的检查点

每更新一个正式文件后，都应立即检查：

1. 该文件是否可被导入
2. `scripts/run_phase1_verifications.py` 是否仍通过
3. 当前更新是否要求同步修改 `reporting`

若第 3 条发生，则不应继续推进 `reporting`，应先停下重新确认边界。

## 7. 本轮不应一起处理的内容

以下内容本轮不应掺入：

- fake runtime 迁移
- `phase1.py` 聚合导出清理
- reporting 正式回收
- 真实 rqalpha runtime 接线
- 结果落库

## 8. 合并后的预期状态

当本轮完成后，应达到：

- 正式 `gateway/contracts.py` 已承载 phase-1 协议
- 正式 `rqalpha_ricequant_gateway.py` 已承载最小 runtime 注入接线
- 正式 `run_single_backtest.py` 已承载最小单次回测用例
- fake runtime 验证仍通过

## 9. 本计划执行后的下一步

完成 `backtest_kernel` 正式回收后，下一步再进入：

- `reporting` 逐文件 patch 计划

不建议在 `backtest_kernel` 未完成回收时直接跨到 `reporting` 真正修改正式骨架。
