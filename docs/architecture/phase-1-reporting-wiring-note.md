# phase-1-reporting-wiring-note

## 1. 本轮推进内容

- 未直接修改已有 `reporting` 骨架文件
- 采用新增文件方式补齐 phase-1 真实读侧接线骨架：
  - `reporting/phase1.py`
  - `reporting/phase1_store_protocols.py`
  - `reporting/phase1_run_results_reader.py`
  - `reporting/phase1_replay_service.py`
  - `reporting/phase1_batch_comparison_service.py`

## 2. 当前已具备的静态接线能力

- 已定义 reporting 依赖的最小 store 协议
- 已定义单次 run detail 聚合逻辑
- 已定义 account / trade / position / yearly-return 图表数据构造逻辑
- 已定义 replay 读侧接线
- 已定义 batch comparison 读侧接线

## 3. 当前仍未进入的范围

- 未接真实 backtest 结果存储实现
- 未做本地读侧验证
- 未暴露 API 或页面层

## 4. 当前价值

- 一旦 `reporting store` 落地，`Phase1RunResultsReader` / `Phase1ReplayService` / `Phase1BatchComparisonService` 就能直接接入
- reporting 与 backtest-kernel 的边界已保持为“只读侧消费”

## 5. 下一步建议

- 若继续不依赖运行环境：
  - 做一份 `phase1_*` 汇总入口文档或收束清单
- 若运行环境恢复：
  - 先补 fake store 验证 run-results-reader 链路
  - 再考虑把 store 实现与真实 SQLite/backtest 结果表接起来
