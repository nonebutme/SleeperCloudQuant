# phase-1-batch-2-helper-fallback-note

## 1. 说明

- 当前本地 helper 在“更新已存在文件”时持续出现 `helper_unknown_error: setup refresh had errors`。
- 为避免破坏已落骨架，`Batch 2` 第一段实现暂采用“新增 `phase1_*` 实现文件”的保守兜底方案。

## 2. 当前新增的真实实现文件

- `data_platform/phase1.py`
- `data_platform/repository/phase1_contracts.py`
- `data_platform/repository/phase1_cached_market_repository.py`
- `data_platform/storage/phase1_sqlite_metadata_store.py`
- `data_platform/providers/phase1_ricequant_repository.py`

## 3. 当前能力边界

- 已落地：
  - phase-1 市场数据仓储接口
  - cache-first 包装层
  - 仅含 `market_data_cache` 的 SQLite 存储实现
- 未落地：
  - Ricequant 实际 provider 调用
  - 旧骨架文件与 `phase1_*` 文件的统一合并
  - backtest 结果表相关能力

## 4. 后续建议

- 等 helper 恢复稳定后，再把 `phase1_*` 实现收束回正式骨架文件。
- 在此之前，优先继续以新增文件方式推进，不对既有文件做高频更新。
