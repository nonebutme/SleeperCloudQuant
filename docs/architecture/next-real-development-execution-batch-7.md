# 下一阶段真实开发第七批执行记录

## 1. 架构判断

### 1.1 已确认

- 共享 SQLite 元数据库已经具备 `market_data_cache`，但此前只覆盖价格历史读取缓存，没有显式同步入口，也没有交易日历缓存与同步记录。
- 数据中心 MVP 需要一个“可触发、可验证、可留痕”的真实同步入口，优先级高于继续扩前端表现层。
- 当前最稳妥的推进方式不是一次性引入完整数据中心工作流，而是在现有 `CachedMarketDataRepository + MarketDataService + market API` 上补最小同步闭环。

### 1.2 本轮架构选择

- 在 `CachedMarketDataRepository` 中新增显式 `sync_price_history / sync_trading_calendar`，同步时强制走上游并刷新 SQLite 缓存。
- 在 `SqliteMetadataStore` 中补齐 `trading_calendar_cache` 与 `market_sync_runs`，让同步动作既能落缓存，也能留下执行记录。
- 在 `MarketDataService`、`app/schemas/market.py`、`app/api/market.py` 增加最小同步请求/响应与 `POST` 路由。
- 保持同步目标只覆盖 `price_history` 与 `trading_calendar`，不扩到财务指标、指数成分和前端页面。

## 2. 本轮新增与调整范围

### 2.1 新增文件

- `docs/architecture/next-real-development-execution-batch-7.md`

### 2.2 调整文件

- `domain/market/models.py`
- `domain/market/__init__.py`
- `app/schemas/market.py`
- `app/services/market_data_service.py`
- `app/api/market.py`
- `data_platform/storage/sqlite_metadata_store.py`
- `data_platform/repository/cached_market_repository.py`
- `app/runtime/demo_registry.py`
- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`
- `scripts/verify_formal_sqlite_cache.py`

## 3. 本轮达成的目标

- 补齐“数据中心真实同步入口”的最小正式能力，支持价格历史与交易日历显式同步。
- 让交易日历首次纳入 SQLite 缓存体系，避免同步后仍只能依赖内存/上游即时读取。
- 给后续数据中心状态页预留同步执行记录基础。

## 4. 已验证项

### 4.1 Services Smoke Test

执行：`python scripts/smoke_test_formal_services.py`

结果：

- `formal services smoke test passed`

### 4.2 API Smoke Test

执行：`python scripts/smoke_test_formal_api.py`

结果：

- `formal API smoke test passed`

### 4.3 HTTP Adapter Smoke Test

执行：`python scripts/smoke_test_formal_http_adapter.py`

结果：

- `formal HTTP adapter smoke test passed`

### 4.4 SQLite Cache Verification

执行：`python scripts/verify_formal_sqlite_cache.py`

结果：

- `formal sqlite cache verification passed`

### 4.5 正式验证链回归

执行：`python scripts/run_formal_verifications.py`

结果：

- `[formal] running verify_formal_fake_runtime.py`
- `formal fake runtime verification passed`
- `[formal] running verify_formal_reporting.py`
- `formal reporting verification passed`
- `[formal] running verify_formal_sqlite_cache.py`
- `formal sqlite cache verification passed`
- `[formal] all verifications passed`

## 5. 当前判断

- `已确认`：项目现已具备价格历史与交易日历的显式同步入口，且同步结果会真实刷新 SQLite 缓存并记录同步执行摘要。
- `已确认`：市场数据查询、同步、回测、reporting 几条正式 smoke 链仍保持可通过状态。
- `待确认`：下一步是否继续补“数据中心同步状态查询/最新同步记录读接口”，还是转入 factor_lab 最小骨架。
