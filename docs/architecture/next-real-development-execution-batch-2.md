# 下一阶段真实开发第二批执行记录

## 1. 本轮新增范围

### 1.1 API 层

- `app/api/__init__.py`
- `app/api/market.py`
- `app/api/backtest.py`
- `app/api/reporting.py`

### 1.2 应用入口

- `app/main.py`

### 1.3 Schema 补充

- `app/schemas/market.py` 增补交易日历请求/响应
- `app/schemas/__init__.py` 同步导出

### 1.4 API 级验证脚本

- `scripts/smoke_test_formal_api.py`

## 2. 本轮达成的目标

- 为当前正式模块和服务层补齐了最小 API 壳层。
- 在未引入 FastAPI 依赖的情况下，先建立了可升级的 fallback app 结构。
- 明确了 5 条最小路由：
  - `/api/market/price-history`
  - `/api/market/trading-calendar`
  - `/api/backtest/run-once`
  - `/api/reporting/run-detail/{run_id}`
  - `/api/reporting/batch-summary/{experiment_id}`

## 3. 已验证项

### 3.1 API Smoke Test

执行：`python scripts/smoke_test_formal_api.py`

结果：

- `formal API smoke test passed`

### 3.2 服务级 Smoke Test

执行：`python scripts/smoke_test_formal_services.py`

结果：

- `formal services smoke test passed`

### 3.3 正式验证链回归

执行：`python scripts/run_formal_verifications.py`

结果：

- `[formal] running verify_formal_fake_runtime.py`
- `formal fake runtime verification passed`
- `[formal] running verify_formal_reporting.py`
- `formal reporting verification passed`
- `[formal] running verify_formal_sqlite_cache.py`
- `formal sqlite cache verification passed`
- `[formal] all verifications passed`

### 3.4 导入检查

结果：

- `api-shell-imports-ok`

## 4. 当前判断

- `已确认`：项目已经从“正式模块库 + 服务层”推进到“正式模块库 + 服务层 + 最小 API 壳层”。
- `已确认`：当前 API 层仍为无依赖 fallback 结构，适合在不改依赖的前提下继续推进。
- `待确认`：下一步是否继续进入真正的 Web/API 运行层，例如正式引入 FastAPI 或补一层 HTTP 适配实现。
