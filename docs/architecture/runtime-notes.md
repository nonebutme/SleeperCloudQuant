# 运行时说明

## 本地环境

- 当前已验证 Python：3.14.5。
- 项目虚拟环境：`.venv/`。
- 默认运行平台：Windows，本地单机。
- Web 静态资源：`web/`。
- 主服务与装配：`app/`、`app/runtime/`。

## 启动入口

PC Web 与 API 同源服务：

```powershell
.\.venv\Scripts\python.exe scripts\run_formal_web_demo.py
```

- 默认监听：`http://127.0.0.1:8010`
- 可通过 `SCQ_WEB_PORT` 修改端口。
- `/api/*` 进入自定义路由和服务层，其余路径从 `web/` 提供静态文件。

仅 API 服务：

```powershell
.\.venv\Scripts\python.exe scripts\run_formal_http_demo.py
```

- 默认监听：`http://127.0.0.1:8000`

## 关键数据路径

- 规范 A 股库：`var/market/a_share_market.sqlite3`
- 历史分类库：`var/runtime/a_share_classification_history.sqlite3`
- 策略库：`var/runtime/strategy_library.sqlite3`
- 单股任务：`var/runtime/single_backtest_tasks.sqlite3`
- 独立账户批量回测任务：`var/runtime/independent_screening.sqlite3`
- 投资组合回测任务：`var/runtime/shared_portfolio.sqlite3`
- Web Demo 运行结果：`tmp/formal_http_demo.sqlite3`
- 运行草稿与索引：`var/runtime/*.json`

## 环境变量

- `SCQ_WEB_PORT`：Web/API 同源服务端口。
- `SCQ_A_SHARE_CANONICAL_DB_PATH`：覆盖规范 A 股库路径。
- `SCQ_A_SHARE_DB_PATH`：覆盖旧 A 股源库路径。
- `SCQ_LEGACY_MARKET_DB_PATH`：覆盖旧项目市场缓存库路径。

敏感 Provider 配置不得写入代码；配置中心只保存明确允许的本地草稿。

## 运行边界

- 服务只监听回环地址，不视为生产部署。
- 多个 SQLite 文件按职责拆分；不支持多机并发写。
- 单股任务是不可分割的小任务，不伪造暂停/取消。
- 独立账户批量回测支持受控并发、暂停、恢复和取消；全市场任务必须经用户明确授权。
- 投资组合回测保持单账户、多持仓语义。
- 删除采用软删除，保留审计字段。

## 验证与已知阻塞

统一验证：

```powershell
.\.venv\Scripts\python.exe scripts\run_formal_verifications.py
```

2026-07-25 阶段 77.0 复核结果：

- `verify_formal_fake_runtime.py`：通过。
- `verify_formal_reporting.py`：通过。
- `verify_formal_sqlite_cache.py`：通过。
- `smoke_test_legacy_sqlite_market_data.py`：通过。
- `smoke_test_a_share_source_database.py`：因 `raw quality is not passed` 中止。

当前规范行情最新日期为 2026-07-17。恢复数据新鲜度并重跑完整验证前，不宣称全系统可发布。
