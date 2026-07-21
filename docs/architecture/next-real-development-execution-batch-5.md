# 下一阶段真实开发第五批执行记录

## 1. 架构判断

### 1.1 已确认

- 项目已经具备单次回测执行、运行时 SQLite 持久化与 reporting 读回的最小闭环。
- 上一批仍缺少“批量研究任务编排”的正式应用层入口。
- 当前最稳妥的推进方式不是引入任务队列，而是在现有同步服务层上补最小批量编排能力。

### 1.2 本轮架构选择

- 新增 `BatchResearchService` 作为应用层批量研究编排入口。
- 继续复用共享 `SqliteRuntimeStore` 作为实验摘要持久化与 reporting 读侧数据源。
- 在 `app/api/backtest.py` 新增 `POST /api/backtest/run-batch`。
- 将 API smoke、HTTP adapter smoke、services smoke、runtime persistence smoke 全部切到共享 SQLite 链路。
- 保持不新增第三方依赖，不引入异步队列。

## 2. 本轮新增与调整范围

### 2.1 新增文件

- `app/services/batch_research_service.py`

### 2.2 调整文件

- `domain/backtest/models.py`
- `domain/backtest/__init__.py`
- `app/services/__init__.py`
- `app/schemas/backtest.py`
- `app/api/backtest.py`
- `app/main.py`
- `app/runtime/demo_registry.py`
- `scripts/smoke_test_runtime_persistence.py`
- `scripts/smoke_test_formal_services.py`
- `scripts/smoke_test_formal_api.py`
- `scripts/smoke_test_formal_http_adapter.py`

## 3. 本轮达成的目标

- 补齐“批量研究任务编排 -> research_run 持久化 -> reporting 汇总读回”的最小正式链路。
- 让 API 壳层和 HTTP demo 同时具备批量研究提交能力。
- 去除这一能力对假 reporting store 的依赖，统一改为共享 SQLite 运行时库。

## 4. 已验证项

### 4.1 导入检查

执行：`python -c "..."`

结果：

- `batch-imports-ok`

### 4.2 运行时持久化烟测

执行：`python scripts/smoke_test_runtime_persistence.py`

结果：

- `runtime persistence smoke test passed`

### 4.3 Services Smoke Test

执行：`python scripts/smoke_test_formal_services.py`

结果：

- `formal services smoke test passed`

### 4.4 API Smoke Test

执行：`python scripts/smoke_test_formal_api.py`

结果：

- `formal API smoke test passed`

### 4.5 HTTP Adapter Smoke Test

执行：`python scripts/smoke_test_formal_http_adapter.py`

结果：

- `formal HTTP adapter smoke test passed`

### 4.6 正式验证链回归

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

- `已确认`：项目现已具备最小批量研究任务编排能力。
- `已确认`：批量研究提交、实验摘要持久化和 reporting 汇总读回已在同一 SQLite 运行时库上闭环。
- `待确认`：下一步是否继续补失败样本归档细化、逐笔日志/持仓/账户快照真实落盘，或进入更高层的研究工作流封装。
