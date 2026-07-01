# 下一阶段真实开发第四批执行记录

## 1. 架构判断

### 1.1 已确认

- 当前项目已经具备 `domain + app/services + app/api + app/runtime` 的最小正式骨架。
- 前三批仍缺少“真实运行数据与任务持久化层”，回测执行结果尚未形成正式的本地归档闭环。
- 本轮目标是优先补齐本地 SQLite 持久化，而不是继续扩展外部依赖或前端界面。

### 1.2 本轮架构选择

- 新增共享 SQLite 运行时存储 `app/runtime/sqlite_runtime_store.py`。
- 让同一个存储同时承担两类职责：
  - 运行时任务/回测执行归档
  - reporting 读侧查询数据源
- 新增 `PersistentBacktestService`，在执行回测时同步写入任务状态与结果指标。
- 将 `app/runtime/demo_registry.py` 从“假 reporting store”切换为“共享 SQLite 运行时库 + 持久化回测服务”。
- 为避免新链路引入循环依赖，将 `app/runtime/__init__.py` 改为惰性导出。

## 2. 本轮新增与调整范围

### 2.1 新增文件

- `app/runtime/sqlite_runtime_store.py`
- `app/services/persistent_backtest_service.py`
- `scripts/smoke_test_runtime_persistence.py`

### 2.2 调整文件

- `app/services/__init__.py`
- `app/runtime/__init__.py`
- `app/runtime/demo_registry.py`

## 3. 本轮达成的目标

- 补齐“真实回测执行 -> 本地 SQLite 落盘 -> reporting 读回”的最小闭环。
- 让 demo HTTP 壳层不再依赖纯内存假 reporting store。
- 保持不新增第三方依赖，继续沿用标准库与既有正式模块。

## 4. 已验证项

### 4.1 运行时持久化烟测

执行：`python scripts/smoke_test_runtime_persistence.py`

结果：

- `runtime persistence smoke test passed`

### 4.2 HTTP Adapter Smoke Test

执行：`python scripts/smoke_test_formal_http_adapter.py`

结果：

- `formal HTTP adapter smoke test passed`

### 4.3 API Smoke Test

执行：`python scripts/smoke_test_formal_api.py`

结果：

- `formal API smoke test passed`

### 4.4 Services Smoke Test

执行：`python scripts/smoke_test_formal_services.py`

结果：

- `formal services smoke test passed`

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

- `已确认`：项目现已具备最小“真实运行数据与任务持久化层”。
- `已确认`：demo HTTP 壳层已能通过共享 SQLite 库承接真实回测任务持久化与 reporting 查询。
- `待确认`：下一步是否继续把批量研究任务编排、运行日志明细和更完整的成交/持仓快照接入同一持久化层。
