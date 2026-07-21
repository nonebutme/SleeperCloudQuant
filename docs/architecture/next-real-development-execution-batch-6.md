# 下一阶段真实开发第六批执行记录

## 1. 架构判断

### 1.1 已确认

- 共享 SQLite 运行时库已经具备 `backtest_logs / backtest_trades / backtest_positions / backtest_accounts / backtest_yearly_returns` 表结构。
- 上一批正式链路虽然完成了批量研究编排，但单次回测完成后仍统一写入空明细行，尚未形成“真实运行结果 -> 明细落盘 -> reporting 图表读回”的闭环。
- 当前最稳妥的推进方式不是扩前端或 AI，而是在现有同步回测链路上补最小明细透传与归档。

### 1.2 本轮架构选择

- 在 `BacktestService` 增加 `run_once_with_raw_result`，保留对现有 `run_once` 摘要接口的兼容。
- 在 `PersistentBacktestService` 中从 runtime `raw_result` 提取日志、成交、持仓、账户、逐年收益，并写入共享 SQLite。
- 采用保守型字段发现策略，优先识别 `logs / trades / positions / accounts / yearly_returns` 及少量兼容别名，不引入新的领域对象层扩张。
- 仅增强 demo runtime 与 smoke test，让公开 reporting 图表能够验证真实明细已被读回。

## 2. 本轮新增与调整范围

### 2.1 新增文件

- `docs/architecture/next-real-development-execution-batch-6.md`

### 2.2 调整文件

- `app/services/backtest_service.py`
- `app/services/persistent_backtest_service.py`
- `app/runtime/demo_registry.py`
- `scripts/smoke_test_runtime_persistence.py`
- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

## 3. 本轮达成的目标

- 补齐“runtime 原始结果 -> SQLite 明细表 -> reporting 图表”最小正式闭环。
- 保持现有 `PersistentBacktestService.run_once`、批量研究服务和 API 壳层不做结构性扩张。
- 让运行时持久化、services、API、HTTP adapter 四条 smoke 链都验证到真实明细读回。

## 4. 已验证项

### 4.1 运行时持久化烟测

执行：`python scripts/smoke_test_runtime_persistence.py`

结果：

- `runtime persistence smoke test passed`

### 4.2 Services Smoke Test

执行：`python scripts/smoke_test_formal_services.py`

结果：

- `formal services smoke test passed`

### 4.3 API Smoke Test

执行：`python scripts/smoke_test_formal_api.py`

结果：

- `formal API smoke test passed`

### 4.4 HTTP Adapter Smoke Test

执行：`python scripts/smoke_test_formal_http_adapter.py`

结果：

- `formal HTTP adapter smoke test passed`

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

- `已确认`：单次回测完成后，运行时日志、成交、持仓、账户、逐年收益已可从 `raw_result` 真实写入共享 SQLite。
- `已确认`：reporting 对外公开的账户净值、成交活跃度、持仓暴露、逐年收益图表已可读取这批真实明细。
- `待确认`：下一步是否继续推进“数据中心真实同步入口”，以及真实 runtime 输出字段是否还需要补更多兼容别名。
