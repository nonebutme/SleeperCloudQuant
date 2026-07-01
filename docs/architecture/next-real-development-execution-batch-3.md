# 下一阶段真实开发第三批执行记录

## 1. 架构判断

### 1.1 已确认

- 当前环境未安装 `FastAPI`。
- 根据项目规则，本轮未擅自引入新依赖。
- 因此本轮采用“应用核心与 Web 框架解耦，先落标准库 HTTP 适配层”的保守架构。

### 1.2 本轮架构选择

- 保留既有 `domain + app/services + app/api` 三层结构。
- 增加 `app/runtime` 作为传输适配层。
- 先使用 Python 标准库 `http.server` 提供可运行的本地 HTTP 壳层。
- 后续如引入 `FastAPI`，可在不推翻现有服务层与路由层的前提下新增框架适配器。

## 2. 本轮新增范围

### 2.1 API 合同与应用入口调整

- `app/api/contracts.py`
- `app/api/__init__.py`
- `app/api/market.py`
- `app/api/backtest.py`
- `app/api/reporting.py`
- `app/main.py`

### 2.2 Runtime 层

- `app/runtime/__init__.py`
- `app/runtime/http_adapter.py`
- `app/runtime/demo_registry.py`

### 2.3 验证与运行脚本

- `scripts/smoke_test_formal_http_adapter.py`
- `scripts/run_formal_http_demo.py`

## 3. 本轮达成的目标

- 让最小 API 壳层从“可调用的内存路由集合”推进到“可运行的标准库 HTTP 服务骨架”。
- 保持不新增第三方依赖。
- 为后续 `FastAPI` 适配保留清晰边界。

## 4. 已验证项

### 4.1 HTTP Adapter Smoke Test

执行：`python scripts/smoke_test_formal_http_adapter.py`

结果：

- `formal HTTP adapter smoke test passed`

### 4.2 API Smoke Test

执行：`python scripts/smoke_test_formal_api.py`

结果：

- `formal API smoke test passed`

### 4.3 Services Smoke Test

执行：`python scripts/smoke_test_formal_services.py`

结果：

- `formal services smoke test passed`

### 4.4 正式验证链回归

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

- `已确认`：当前项目已经具备“正式模块 + 服务层 + API 壳层 + 标准库 HTTP 适配层”的最小本地系统骨架。
- `已确认`：当前最优架构不是立刻强行引入框架依赖，而是在现有分层基础上继续补真实基础设施与持久化闭环。
- `待确认`：下一步是否继续进入“真实运行数据与任务持久化层”，或者单独授权引入 `FastAPI`。
