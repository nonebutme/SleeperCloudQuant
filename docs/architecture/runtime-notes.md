# 运行时说明

## R2 指标运行时（2026-09-14）

统一 Web 装配 `IndicatorService` 与 `/api/indicators`；数据浏览、数据集注册和策略导入均在正式首页。指标值按需读取当前规范行情全历史前缀，复权和数据批次须匹配，缓存命中仍验证真实输入。旁库自动建表，不做外部同步；用户生成因子后仍须显式启动分析并明确选用制品。详见 [R2 使用流程](../workflows/r2-indicators.md)。

## R1 维护候选（2026-09-13）

新增主库旁的维护缓存、更新互斥和研究读锁数据库；成功更新自动生效，无需手动设置默认。缓存保留、锁等待及未验证项见 [R1 运行边界](r1-data-maintenance-simplification.md)。本轮未启动正式数据更新。

## 本地环境

- 当前已验证 Python：3.14.5。
- 项目虚拟环境：`.venv/`。
- 默认运行平台：Windows，本地单机。
- Web 静态资源：`web/`。
- 主服务与装配：`app/`、`app/runtime/`。

## 启动入口

用户统一入口：双击项目根目录 `启动系统.cmd`；停止使用 `停止系统.cmd`。

内部调用链：`启动系统.cmd` → `scripts/start_sleepercloudquant.ps1` → `scripts/run_formal_web_demo.py`。PC Web 与 API 共用一个服务，无需分别启动。

- 默认监听：`http://127.0.0.1:8010`
- `-Port` / `SCQ_WEB_PORT` 仅用于开发诊断，日常固定使用默认入口。
- `/api/system/health` 确认主服务完成装配；启动器同时检查页面、健康状态和进程身份。
- `/api/*` 进入路由和服务层，其余路径从 `web/` 提供静态文件。主服务访问 `/strategy-studio.html` 会跳回正式策略页 `/?page=backtest`。

开发专用入口（显式启用；不属于日常启动）：

```powershell
.\.venv\Scripts\python.exe scripts\run_formal_http_demo.py --developer-mode
.\.venv\Scripts\python.exe scripts\run_strategy_studio_web_demo.py --developer-mode
```

- 分别监听 8000（纯 API 调试）、8020（策略工作室候选）。未传开发参数时退出，不装配服务或初始化数据。
- 候选工作室独有数据集产品目录与策略清单接口（`/api/datasets`、`/api/strategy-studio/manifests`），未因入口统一自动提升为正式功能。正式策略编辑、数据集和三种回测继续从 8010 导航访问。

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

## 阶段 87 运行说明（2026-08-12）

- 运行库：var/runtime/factor_research.sqlite3；初始化幂等，启动时把遗留 running/stop_requested 任务恢复为 interrupted。
- 市场库：var/market/a_share_market.sqlite3，只读打开；真实预检前后文件长度和最后写入时间保持不变。
- 默认版本政策：自动选择最新 published；显式 published/superseded ID 仅用于复现，不读取 superseded 默认指针。
- 当前真实预检：版本 scq-20260810-29d6940cd8820c57，请求 2026-07-01—07-16、5 日前瞻的有效因子区间为 07-01—07-09。
- 当前指数能力：factor_index_component_intervals 无正式事实，返回 index_component_facts_unavailable。
- 专项验证：python scripts/smoke_test_stage87_factor_research_core.py、smoke_test_stage87_factor_research_api.py、smoke_test_stage87_factor_research_ui.py。
- 统一验证当前仍受真实数据门禁阻塞：hfq 到 2026-07-30，raw/qfq 到 2026-08-10。
## 阶段 88 运行说明（2026-08-13）

- 全局默认与最新发布版本：`scq-20260810-27cd5406fa3a12a9`；质量报告 `stage782-20260810-2e42c465479e` 及 9 个版本成员均为 `passed`。
- raw/qfq/hfq 均覆盖到 `2026-08-10`；全市场质量验证覆盖率均为 `99.9819%`，重复键为 0，raw OHLCV 有效。
- 因子研究、策略数据集与三类回测在任务创建时统一冻结显式版本或全局默认版本；声明因子依赖时同时冻结不可变因子制品。
- 数据中心 `index_component_intervals` 是指数成分唯一写入权威；外部同步必须提供显式授权确认与授权引用，当前正式指数池因事实未导入返回 `index_component_facts_unavailable`。
- 本地 Web 服务运行在 `127.0.0.1:8010`；新增指数覆盖和因子制品路由已完成 HTTP 验证。
- `scripts/run_formal_verifications.py` 最终退出码 0，输出 `[formal] all verifications passed`；人工浏览器业务验收与模拟盘/实盘有效性验证尚未执行。

## 阶段 91.0—91.3 运行说明（2026-08-13）

- 数据源连接测试默认只做契约探测；勾选真实探测时仍只读，并先执行 `allowed_hosts` 策略校验。
- 任务创建后，执行器从持久化冻结配置恢复限频、并发、重试和退避，不读取后续修改的源配置。
- 纠错覆盖发布为新版本但不自动切换全局默认版本；问题保持隔离，直到定向复检通过；标准行情读取只合并默认版本所属覆盖。
- `python scripts/run_formal_verifications.py` 已通过；人工浏览器业务验收待执行，91.4 未启动。

## 隔离统一正式验证运行说明（2026-08-25）

- `scripts/run_formal_verifications.py` 在 allowlist 源码快照内执行，并为每个脚本重建隔离的 `var/market`、`var/runtime`、`tmp/system-temp` 与 `output`；普通失败继续收集其余结果，存储守卫、正式源身份或保护区指纹异常则立即停止。
- 只有 `smoke_test_a_share_source_database.py` 与 `smoke_test_a_share_full_market_quality.py` 能读取正式规范行情库，连接固定为 SQLite immutable/query-only；其余脚本和两个 Node 静态门禁均拿不到正式源路径。
- 运行 `formal-20260825T091211-e8ea8607` 完成 109 项，107 项通过；两项真实数据门禁因 raw/qfq/hfq 仍截止 `2026-08-17` 而失败。统一验证整体未通过，不能把工程回归通过与数据新鲜度通过混为一谈。
- 持久报告：`tmp/formal-verification-reports/formal-20260825T091211-e8ea8607/formal-verification-report.json`。保护区证据是抽样内容指纹加文件元数据，不是整库完整哈希或 OS 沙箱。
- 本次验证未写正式数据库、未发布或切换数据版本、未重启服务。日常更新继续只运行分钟级快速门禁；完整统一验证用于代码、结构或配置发布前的工程回归。
