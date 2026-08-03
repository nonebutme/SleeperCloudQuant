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

## M4 市场全景运行说明（2026-07-30）

- 独立全景库：`var/runtime/market_panorama.sqlite3`
- 全景只读接口：`GET /api/market/panorama?trade_date=YYYY-MM-DD&symbol=...&asset_type=stock|index`
- M2 数据集：`industry_board`、`concept_board`、`industry_flow`、`concept_flow`、`events`、`panorama_all`、`industry_classification_repair`。
- 独立任务入口：`python scripts/run_market_panorama_sync_job.py --job-id <任务号>`。
- `SCQ_PANORAMA_WORKERS`：全景同步并发，默认 4，最大 8。
- 虚拟环境当前没有 `Crypto`；行业分类失败修复沿用系统 Python 已安装的 PyCryptodome，不修改项目依赖或锁文件。

当前真实覆盖：规范 A 股 `qfq` 日线完整到 2026-07-28，六个指数到 2026-07-29；正式已发布版本截止仍以治理库记录为准，较新观察不自动视为正式发布。
## M4 市场全景 P0—P3 执行结果（2026-07-30）

- P0：本地行业全景、`GET /api/market/panorama` 与 M4 K 线交易日下钻已接通；请求 `2026-07-28` 时行业热度 90 行。
- P1：行业/概念板块历史已分别落库 90/374 个板块；概念资金流已落库 15 个板块、591 行历史记录。行业资金流免费上游当前全部失败，接口明确返回 `unavailable`，不生成模拟值。
- P2：`000001` 在 `2026-07-28` 已落库 2 条可追溯新闻；公告源当日无返回时保持空，不用新闻伪装公告。
- P3：行业分类失败项经两轮修复后仍有 24 项受免费上游失败影响；A 股目标日 9 个缺口已由停牌接口逐项核验，调度器按目标日保存停牌状态并允许证据充分的 0 行完成。任务 `a-share-sync-20260728-0952b4b524` 最终 5533/5533 完成、0 隔离，发布版本 `scq-20260728-033fc57a7de87fe4`。
- 验证：市场全景、M4、数据中心、VTable、停牌调度器聚焦回归全部通过；M4、数据中心、全局 VTable 浏览器验收通过。完整正式验证仍在既有 raw/hfq 新鲜度门禁处中止，原因是两种口径最新日仍为 `2026-07-17`。