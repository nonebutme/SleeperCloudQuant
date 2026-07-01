# phase-1-fake-assets-note

## 1. 本轮新增内容

- `backtest_kernel/adapters/phase1_fake_runtime.py`
- `backtest_kernel/use_cases/phase1_fake_runtime_demo.py`
- `reporting/phase1_fake_store.py`
- `reporting/phase1_fake_store_demo.py`

## 2. 作用

- 为当前不稳定的 helper 环境提供“无外部依赖”的本地假实现资产
- 让 phase-1 的静态接线层具备更接近可验证的演示入口

## 3. 当前价值

- `Phase1ConnectedRqalphaGateway` 已可通过 fake runtime 进入完整 request -> payload -> result 归一化链路
- `Phase1RunResultsReader` 与 `Phase1BatchComparisonService` 已可通过 fake store 进入只读聚合链路

## 4. 当前限制

- 本轮仍未实际执行这些 demo 资产
- 因此当前只能表述为“已落地可演示资产”，不能表述为“已验证通过”

## 5. 后续建议

- 若 helper 恢复：
  - 优先执行 fake 资产验证
  - 再执行 sqlite cache 验证
- 若 helper 继续不稳：
  - 继续以新增文件方式完善 fake 资产与未来合并清单
