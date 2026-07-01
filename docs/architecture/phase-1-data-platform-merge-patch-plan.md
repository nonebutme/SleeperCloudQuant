# phase-1-data-platform-merge-patch-plan

## 1. 文档定位

- 目标：把 `data_platform` 第一批正式回收所需的逐文件 patch 计划写清楚。
- 范围：只覆盖 `data_platform` 第一批正式骨架回收。
- 状态：`已确认（逐文件 patch 计划层）`

## 2. 本计划对应的正式目标文件

- `data_platform/repository/contracts.py`
- `data_platform/repository/cached_market_repository.py`
- `data_platform/storage/sqlite_metadata_store.py`
- `data_platform/providers/ricequant_repository.py`

## 3. 本计划对应的来源文件

- `data_platform/repository/phase1_contracts.py`
- `data_platform/repository/phase1_cached_market_repository.py`
- `data_platform/storage/phase1_sqlite_metadata_store.py`
- `data_platform/providers/phase1_ricequant_support.py`
- `data_platform/providers/phase1_connected_ricequant_repository.py`

## 4. 文件级 patch 计划

### 4.1 `repository/contracts.py`

#### 当前目标

- 用 phase-1 已验证接口替换当前较早期的最小占位接口。

#### 应替换内容

- `fetch_price_history` 签名从：
  - 必填 `start_date` / `end_date`
- 调整为：
  - `start_date: str | None = None`
  - `end_date: str | None = None`

- 删除：
  - `fetch_instrument`
  - `search_instruments`

- 新增：
  - `fetch_index_components`
  - `fetch_financial_indicators`
  - `fetch_trading_calendar`

#### 合并来源

- `data_platform/repository/phase1_contracts.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`

### 4.2 `repository/cached_market_repository.py`

#### 当前目标

- 让正式缓存包装层与 phase-1 已验证逻辑一致。

#### 应替换内容

- 保留 cache-first 行为
- 使用：
  - `_build_price_cache_key`
  - `fetch_market_data_cache`
  - `upsert_market_data_cache`

- 透传以下接口到 upstream：
  - `fetch_index_components`
  - `fetch_financial_indicators`
  - `fetch_trading_calendar`

- 删除当前不再匹配 phase-1 主链路的：
  - `fetch_instrument`
  - `search_instruments`

#### 合并来源

- `data_platform/repository/phase1_cached_market_repository.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- 导入 `CachedMarketDataRepository` 不报错

### 4.3 `storage/sqlite_metadata_store.py`

#### 当前目标

- 让正式 SQLite store 至少具备当前已验证的 `market_data_cache` 能力。

#### 应替换内容

- 引入：
  - `json`
  - `sqlite3`
  - `contextmanager`

- 正式落入以下方法：
  - `ensure_schema`
  - `fetch_market_data_cache`
  - `upsert_market_data_cache`
  - `_connect`
  - `_dump_rows`

- 当前阶段仍不引入：
  - backtest 结果表
  - research_run 表
  - instrument_cache 表

说明：

- 第一批只把“已经验证通过的纯 market cache”回收进去。
- 不要在这一批把更大的 SQLite 职责一起带回正式文件。

#### 合并来源

- `data_platform/storage/phase1_sqlite_metadata_store.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- `verify_phase1_sqlite_cache.py` 间接通过

### 4.4 `providers/ricequant_repository.py`

#### 当前目标

- 让正式 provider 文件具备最小可注入 client 的静态接线能力。

#### 应替换/新增内容

- 引入最小 client 协议定义
- 引入以下归一化函数：
  - `normalize_price_history_rows`
  - `normalize_financial_indicator_rows`
  - `normalize_trading_calendar`

- 引入正式 repository 实现，支持：
  - `client: Phase1RicequantClient | None = None`
  - `_require_client()`

- 正式支持接口：
  - `fetch_price_history`
  - `fetch_index_components`
  - `fetch_financial_indicators`
  - `fetch_trading_calendar`

- 当前阶段仍不引入：
  - 真实 SDK 构造
  - 外部登录逻辑

#### 合并来源

- `data_platform/providers/phase1_ricequant_support.py`
- `data_platform/providers/phase1_connected_ricequant_repository.py`

#### 合并后验证

- `scripts/run_phase1_verifications.py`
- 静态导入不报错

## 5. 推荐执行顺序

建议执行顺序固定为：

1. `repository/contracts.py`
2. `repository/cached_market_repository.py`
3. `storage/sqlite_metadata_store.py`
4. `providers/ricequant_repository.py`

原因：

- 先统一协议
- 再统一包装层
- 再统一存储层
- 最后统一 provider 接线

## 6. 每一步执行后的检查点

每更新一个正式文件后，都应立即检查：

1. 文件能否被正常导入
2. `scripts/run_phase1_verifications.py` 是否仍通过
3. 当前更新是否迫使修改下游模块

若第 3 条发生，则本轮应先停下，不继续推进后续文件。

## 7. 不应在本轮一起处理的内容

以下内容本轮不应掺入：

- `phase1.py` 聚合导出文件清理
- fake runtime / fake store 迁移
- `backtest_kernel` 正式回收
- `reporting` 正式回收
- `__init__.py` 风格统一

## 8. 本计划执行后的下一步

如果 `data_platform` 第一批正式回收成功，下一步才建议进入：

- `backtest_kernel` 逐文件 patch 计划
- 再之后是 `reporting`
