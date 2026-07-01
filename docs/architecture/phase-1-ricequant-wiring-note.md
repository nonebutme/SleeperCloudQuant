# phase-1-ricequant-wiring-note

## 1. 本轮推进内容

- 未直接修改已有 `Phase1RicequantMarketDataRepository`
- 采用新增文件方式补齐其最小接线周边：
  - `data_platform/providers/phase1_ricequant_support.py`
  - `data_platform/providers/phase1_connected_ricequant_repository.py`

## 2. 当前已具备的静态接线能力

- 已定义最小 `Phase1RicequantClient` 协议
- 已定义 price-history / financial-indicator / trading-calendar 的归一化函数
- 已定义一个可注入 client 的 `Phase1ConnectedRicequantRepository`

## 3. 当前仍未进入的范围

- 未接真实 Ricequant SDK
- 未做外部连接验证
- 未把新接线文件合并回旧骨架文件

## 4. 当前价值

- 后续一旦运行环境稳定，只需要提供一个满足协议的 client 实现
- `Phase1ConnectedRicequantRepository` 就能直接进入真实调用链

## 5. 下一步建议

- 若继续不依赖运行环境：
  - 继续推进 `backtest_kernel` 的 phase-1 实现骨架
- 若运行环境恢复：
  - 先补一个最小 fake client 验证归一化链路
  - 再考虑真实 Ricequant 接线
