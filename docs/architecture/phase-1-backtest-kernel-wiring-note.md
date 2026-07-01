# phase-1-backtest-kernel-wiring-note

## 1. 本轮推进内容

- 未直接修改已有 `backtest_kernel` 骨架文件
- 采用新增文件方式补齐 phase-1 真实接线骨架：
  - `backtest_kernel/phase1.py`
  - `backtest_kernel/gateway/phase1_contracts.py`
  - `backtest_kernel/adapters/phase1_rqalpha_support.py`
  - `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`
  - `backtest_kernel/use_cases/phase1_run_single_backtest.py`

## 2. 当前已具备的静态接线能力

- 已定义 phase-1 backtest request / result / gateway 协议
- 已定义 runtime payload 构建与结果归一化逻辑
- 已定义一个可注入 runtime 的 `Phase1ConnectedRqalphaGateway`
- 已定义最小单次回测用例 `Phase1RunSingleBacktest`

## 3. 当前仍未进入的范围

- 未接真实 rqalpha / ricequant runtime
- 未做外部运行验证
- 未接回测结果落库

## 4. 当前价值

- 后续一旦运行环境稳定，只需提供一个满足 `Phase1RqalphaRuntime` 协议的 runtime
- 单次回测用例与 gateway 之间的调用链即可进入真实执行

## 5. 下一步建议

- 若继续不依赖运行环境：
  - 继续推进 `reporting` 的 phase-1 真实读侧接线骨架
- 若运行环境恢复：
  - 先补一个 fake runtime 验证 request -> payload -> result 归一化链路
  - 再考虑真实 rqalpha 接线
