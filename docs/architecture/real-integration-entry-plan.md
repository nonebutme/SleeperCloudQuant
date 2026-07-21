# 真实接入准入规划

更新时间：2026-07-15

## 一、定位

- `已确认` 本文用于定义 Web MVP 验收基线之后，进入真实数据、真实回测 runtime、真实 LLM Provider 与许可证复核前必须满足的准入条件。
- `已确认` 阶段 15 已补充 `docs/architecture/source-reuse-inventory.md`，作为许可证与复用边界的当前审计基线。
- `已确认` 本文不直接触发真实接入实现，不写入密钥，不修改依赖，不变更部署或安全配置。
- `已确认` 当前 Web MVP 已可作为本地验收版本；下一阶段的重点不是继续扩 demo，而是把真实接入拆成可审批、可验证、可回退的执行批次。

## 二、总准入原则

1. `已确认` 真实接入必须先完成授权、账号、密钥、安全边界和验收样例确认。
2. `已确认` 任何真实数据、真实 LLM 或真实 runtime 接入都不得硬编码密钥、口令、令牌、证书或隐私数据。
3. `已确认` 所有真实接入都必须保留当前本地 demo/runtime 路径，作为回归和离线演示 fallback。
4. `已确认` 每条真实接入主线必须先有最小样例，再扩大范围；不得一次性接入全市场、全策略、全模型。
5. `已确认` 金融分析输出必须继续保留研究辅助定位，不得输出确定性投资建议或实盘承诺。

## 三、推荐进入顺序

| 顺序 | 主线 | 推荐原因 | 进入方式 |
| --- | --- | --- | --- |
| 1 | 许可证与复用边界复核 | 决定五仓库重构成果能否继续扩大复用 | 先做清单与风险分级，不改代码 |
| 2 | 真实行情源最小接入 | 是因子、回测、AI、报告的共同数据基础 | 只接 1-2 个标的、短日期区间 |
| 3 | 真实 rqalpha runtime 最小接入 | 验证回测结果是否能从 demo runtime 切换为真实引擎 | 只跑单策略、单标的、固定日期 |
| 4 | 真实 LLM Provider 最小接入 | AI 输出质量和成本风险最高，适合在数据/回测边界稳定后接入 | 只接单股摘要任务，保留人工复核 |
| 5 | 研究报告包正式化 | 将真实数据、真实回测、真实 AI 结果固化为可归档 package | 在前四项稳定后扩展导出格式 |

## 四、主线 A：许可证与复用边界复核

### 准入条件

- `已确认` 五个参考仓库的许可证类型、允许用途、二次分发边界和署名要求已形成当前工程复核表：`docs/architecture/source-reuse-inventory.md`。
- `已确认` 阶段 16A 已将完整逐文件扫描降级为按需触发；当前非商业用途下不阻塞后续真实行情源最小接入。
- `已确认` 用户同意暂缓完整逐文件复核；后续直接复制、扩大引用、对外分发或商业用途前再触发。

### 首批任务

1. 建立 `source_reuse_inventory` 清单：来源仓库、文件/功能、采纳方式、是否直接复制、是否改写、目标文件。
2. 按风险分级标记：`direct-copy`、`adapted`、`semantic-reference`、`frozen-reference`。
3. 对 direct-copy 和 adapted 项输出待处理建议：保留、重写、署名、隔离或移除。

### 验收样例

- `已确认` 输出一份许可证复核表：`docs/architecture/source-reuse-inventory.md`。
- `已确认` 每个核心功能域能说明来源是直接采纳、改造后采纳、语义参考还是冻结不用。
- `已确认` 未经复核的外部源码不继续扩大复用。

### 红线

- 不在许可证边界不清时继续复制外部仓库源码。
- 不移除原作者许可证或署名信息。
- 不把语义参考描述成“已合法直接复用”。

## 五、主线 B：真实行情源最小接入

### 准入条件

- `已确认` 阶段 17 先接入 `SleeperCloudQuant-old/SleeperCloudQuant/data/app_cache.db` 作为只读本地 SQLite 行情源；外部数据供应商、账号、API Key 和调用额度仍待确认。
- `待确认` A 股标识规范、复权口径、交易日历口径、停牌和缺失值处理规则。
- `待确认` 本地缓存路径、刷新策略、失败 fallback 和审计日志要求。

### 首批任务

1. 新增 provider 适配层，不替换当前 `FakeMarketDataRepository` 和本地 cache 路径。
2. 只接入 1-2 个标的，例如 `000001.XSHE` 与 `600000.XSHG`。
3. 只接入短区间日线 OHLCV 和交易日历。
4. 将真实数据源状态暴露到配置中心和数据中心。

### 验收样例

- `GET /api/market/price-history?symbol=000001.XSHE&start_date=2020-01-02&end_date=2020-01-10` 返回本地 SQLite 行情源 OHLCV 数据。
- 数据中心 K 线图可渲染真实 OHLCV。
- 本地旧 SQLite 可读、demo fallback、API 返回行数、外部 provider 401/成功/fallback source_trace 均有 smoke/API 验证。
- 统一验证增加真实 provider 的可选 smoke；无密钥环境下必须跳过而不是失败。

### 红线

- 不硬编码数据源密钥。
- 不在未授权情况下抓取或绕过供应商限制。
- 不把 demo 数据和真实数据混成不可区分的结果。

## 六、主线 C：真实 rqalpha runtime 最小接入

### 准入条件

- `已确认` 阶段 18 已先完成 rqalpha-compatible 本地 SQLite 行情驱动 runtime；真实 rqalpha 版本、依赖安装方式、运行隔离方式和输出文件位置仍待确认。
- `已确认` 阶段 18 最小样例使用单策略、单标的、固定日期、初始资金和简化手续费口径；真实 rqalpha 手续费/滑点口径仍待确认。
- `已确认` 阶段 18 已将 runtime 输出归一化为 metrics、trades、positions、accounts、yearly_returns，并进入现有报告字段。

### 首批任务

1. 在 `backtest_kernel` 增加真实 runtime adapter，与当前 fake/formal runtime 并存。
2. 只支持单次回测，不先扩批量扫描。
3. 将 rqalpha 输出归一化为当前 `PersistentBacktestService` 可写入的 run、metrics、logs、trades、positions、accounts、yearly_returns。
4. 报告中心复用现有 run detail 和 7 维评估报告，不新开报告体系。

### 验收样例

- 单策略、单标的、固定日期回测可通过本地 SQLite 行情驱动 runtime 跑通。
- `reporting_run_detail` 能读取本地 SQLite runtime 落库结果。
- 7 维报告能基于真实指标刷新。
- fake/formal runtime 回归仍然通过。

### 红线

- 不在真实 runtime 未稳定前替换现有 demo runtime。
- 不把真实回测样例结果解释成实盘收益承诺。
- 不引入不可复现的隐式本地环境依赖。

## 七、主线 D：真实 LLM Provider 最小接入

### 准入条件

- `已确认` 阶段 19 已新增 OpenAI-compatible 外部 LLM Provider 网关；Provider、模型、调用区域、密钥管理、预算、日志留存和输出合规策略仍待用户确认后启用。
- `待确认` 是否允许将行情、策略、报告摘要发送给外部模型；当前未配置环境变量时不发送外部请求。
- `待确认` 人工复核状态、免责声明和敏感信息过滤规则。

### 首批任务

1. 在配置中心新增真实 LLM profile，但不保存密钥明文。
2. AI workflow 只开放单股分析任务，不先开放复杂多任务编排。
3. 保留当前 local-demo-tradingagents-style Provider 作为 fallback。
4. 将模型输入、输出、风险提示和 Provider mode 写入 workflow trace。

### 验收样例

- 单股 AI workflow 可切换到外部 Provider profile，并在未配置密钥时记录 fallback trace。
- workflow trace 显示 provider profile、模型模式、fallback/调用状态、输入摘要、输出摘要和风险提示。
- 无密钥环境下自动回退 local demo 或明确返回配置缺失状态。
- 报告中心 AI 联动复盘能显示真实 Provider 产生的 trace。

### 红线

- 不硬编码 LLM 密钥。
- 不发送未获授权的敏感数据。
- 不输出确定性交易建议。
- 不隐藏模型失败、超时、限流或 fallback 状态。

## 八、主线 E：研究报告包正式化

### 准入条件

- `已确认` 当前已有研究报告包、AI workflow 绑定、报告快照、manifest 和 HTML/JSON/PDF/Word-compatible 导出。
- `已确认` 阶段 20 已将本地 SQLite 行情源、local SQLite runtime、LLM Provider trace、验证命令和边界说明固化到报告包 manifest。
- `已确认` 阶段 21 已完成最小 PDF 与 Word-compatible `.doc` 导出；阶段 22 已完成结构化多页 PDF 版式 smoke；`待确认` 是否需要真 `.docx`、签章、审阅状态或正式报告编号。
- `待确认` 是否需要不可变归档路径和外部审计日志。

### 首批任务

1. `已完成` 先增强 HTML 导出模板，并补最小 PDF/Word-compatible 导出。
2. `已完成` 增加报告包 manifest：数据源、runtime、LLM provider、生成时间、绑定模式、验证命令。
3. `已完成` 阶段 21 最小导出 smoke；高级模板、字体、分页、渲染验证和文件存储策略仍待后续评估。

### 验收样例

- 一个 report package 可以追溯到 run、AI workflow、snapshot 和导出文件。
- HTML 导出包含关键指标、AI 风险意见、组合经理动作和数据质量说明。
- JSON 导出可被重新导入或用于审计比对。
- PDF 导出返回最小有效 PDF，包含 package、run、manifest、runtime、LLM provider 和非投资建议边界。
- Word-compatible 导出返回 `.doc` HTML，可由 Word/WPS 打开并保留完整报告内容。

### 红线

- 不在未完成视觉 QA 前承诺正式报告排版质量。
- 不把导出文件作为法律或投资建议文件。
- 不跳过数据来源与模型来源记录。

## 九、统一验证策略

### 必须保留

- `python scripts/run_formal_verifications.py`
- Web Demo 启动：`python scripts/run_formal_web_demo.py`
- 当前 local demo/fake runtime 回归路径

### 新增验证原则

- 真实 provider smoke 必须可选：无密钥或无授权时跳过并说明原因。
- 每个真实接入主线必须新增最小端到端 probe。
- 每个真实接入主线必须新增 fallback 测试，确认 demo/runtime 路径仍可用。
- 验证报告必须继续输出：已验证项、未验证项、阻塞原因、潜在风险、发布判断。

## 十、阶段 17 发布判断

- `已确认` 阶段 17 已执行本地旧 SQLite 行情源最小接入；外部 provider 接入仍保持准入规划状态。
- `已确认` 已先完成许可证与复用边界工程复核，再接入真实行情源。
- `已确认` 用户已批准阶段 16A 轻量复用门禁，完整文件级相似度/复用扫描按需触发。
- `已确认` 阶段 17 已完成本地旧 SQLite 行情源最小接入；外部真实 provider 授权与密钥管理方案仍待确认。

## 十一、阶段 20 发布判断

- `已确认` 阶段 20 已完成研究报告包 manifest 正式化增强。
- `已确认` 报告包详情、JSON 导出和 HTML 导出均可追踪数据源、runtime、LLM Provider、验证命令与边界。
- `待确认` 下一阶段是否进入 PDF/Word 正式报告导出，或优先推进真实 rqalpha 包/外部行情 provider。


## 十二、阶段 21 发布判断

- 已确认 阶段 21 已完成报告包 PDF 与 Word-compatible 最小导出。
- 已确认 python scripts\\smoke_test_report_package_exports.py 验证 HTML/JSON/PDF/Word 四种导出格式。
- 待确认 后续若要求正式排版质量，应进入高级 PDF/Docx 模板、分页、字体和截图级 QA 阶段。


## 十三、阶段 22 发布判断

- 已确认 阶段 22 已将 PDF 从单页审计摘要升级为 4 页结构化正式报告版式。
- 已确认 已新增 python scripts\\smoke_test_report_package_layout.py，验证页数结构、分区标题、页脚、manifest 和本地样例 PDF。
- 未验证 当前环境缺少 Poppler/PyMuPDF，尚未完成 PNG 渲染级视觉 QA；样例文件已输出到 output/pdf/stage22-report-package-layout-smoke.pdf 供人工打开复核。
- 待确认 是否进入阶段 23：安装/配置渲染工具并做截图级视觉 QA，或转向真实 rqalpha/外部行情 provider。


## 十四、阶段 23 发布判断

- 已确认 阶段 23 已新增真实 rqalpha 包探测 runtime：检测到包时记录版本，未安装或未批准真实执行时回退本地 SQLite runtime。
- 已确认 阶段 23 已新增外部行情 HTTP Provider 网关：仅在 SCQ_MARKET_PROVIDER_BASE_URL 与 SCQ_MARKET_PROVIDER_API_KEY 同时配置时调用，否则回退本地旧 SQLite/demo。
- 已确认 配置中心展示 market_provider_status 与 qalpha_runtime_status，不暴露密钥。
- 待确认 下一阶段是否提供真实 provider endpoint/密钥与 rqalpha 运行环境，以执行真实外部调用和真实 rqalpha 策略包。


## 十五、阶段 24 发布判断

- 已确认 配置中心前端已增强：可配置外部行情 Provider 的非密钥项，包括启用意图、Provider Name、Base URL 与 Timeout。
- 已确认 API Key 仍采用环境变量 SCQ_MARKET_PROVIDER_API_KEY，前端草稿与配置 API 均不保存明文密钥。
- 已确认 rqalpha 先做本地功能闭环：包探测、策略库/参数、本地 SQLite 回测、报告落库、fallback trace；真实能力包括数据 bundle、策略文件执行、手续费滑点模型、benchmark 对齐和外部 provider e2e，待后续环境确认。
- 待确认 下一阶段是否配置真实 provider key 或安装 rqalpha 包，进入真实调用验证。


## 十六、阶段 25 发布判断

- 已确认 rqalpha 本地替身层已增强：支持策略模板 trace、参数映射、手续费率、印花税率、最小佣金、滑点率和 benchmark 对齐。
- 已确认 本地 runtime 输出 qalpha_local、strategy_template、enchmark_alignment、enchmark_return 和 excess_return，报告中心可读取年度 benchmark/excess。
- 已确认 Web 回测表单已新增 rqalpha 本地配置控件，并随 run-once / 参数扫描传递到 extra_config.rqalpha_local。
- 待确认 真实 rqalpha 包安装、数据 bundle、策略文件执行、手续费/滑点与真实引擎一致性基线。


## 十七、阶段 26 发布判断

- 已确认 已新增外部行情 Provider 端到端 mock smoke：本地 HTTP provider、配置中心草稿、环境变量 API Key、市场 API、回测、AI workflow、报告包 manifest 全链路通过。
- 已确认 外部 Provider 非空返回时优先于本地 fallback；未配置 API Key 或外部失败时仍 fallback 到本地旧 SQLite/demo。
- 已确认 报告包 manifest 已记录 external_market_provider 状态，且不保存 API Key。
- 待确认 真实第三方行情 endpoint、认证协议、错误码、限流、字段映射和增量同步策略。


## 十八、阶段 27 发布判断

- 已确认 阶段 27 已完成外部行情 Provider 错误观测与 fallback source_trace：HTTP 错误、网络错误、超时、空响应、cache_hit、upstream_refresh、primary/fallback 选择原因均可追踪。
- 已确认 数据中心行情响应已返回 source_trace，前端状态卡展示选用来源、切换原因、外部 Provider 状态、外部请求状态与行数对比。
- 已确认 缓存层已透传 upstream trace，避免缓存命中时丢失数据来源上下文。
- 已确认 新增 python scripts\smoke_test_external_market_observability.py，并纳入 python scripts\run_formal_verifications.py；API Key 不进入配置草稿、报告或 source_trace。
- 待确认 下一阶段是否进入真实第三方 endpoint 字段映射、分页/限流/重试策略与增量同步任务。

## 十九、阶段 28 发布判断

- 已确认 阶段 28 已完成真实行情 endpoint 适配前置层：外部 Provider 支持 endpoint path、响应 rows path、OHLCV 字段映射、交易日历 path、分页参数、最大页数与重试次数。
- 已确认 配置中心前端可编辑外部行情 endpoint spec 的非密钥项；API Key 仍仅从 SCQ_MARKET_PROVIDER_API_KEY 环境变量读取。
- 已确认 显式同步接口 /api/market/sync-price-history 已返回 source_trace，可追踪 cache/upstream/primary/fallback 与 provider 分页调用状态。
- 已确认 新增 python scripts\smoke_test_market_endpoint_mapping.py，并纳入 python scripts\run_formal_verifications.py；分页 mock、字段映射、同步 trace 与密钥不泄露均已验证。
- 待确认 下一阶段是否进入 Provider 预检/连通性测试按钮、真实 endpoint 样例接入，或进入增量同步任务队列与定时刷新策略。

## 二十、阶段 29 发布判断

- 已确认 阶段 29 已完成配置中心外部行情 Provider 预检入口：POST /api/config/market-provider/preflight。
- 已确认 预检不写缓存、不落库，仅使用当前运行时草稿和环境变量 API Key 发起一次小范围行情请求。
- 已确认 预检结果返回 row_count、sample_rows、field_coverage、provider_status、endpoint_spec、base_url/api_key/provider_call/rows/required_fields/secret_leak 检查项。
- 已确认 Web 配置中心新增“预检 Provider”按钮与结果输出区，可在配置 endpoint spec 后直接验证字段映射与认证状态。
- 已确认 新增 python scripts\smoke_test_market_provider_preflight.py，并纳入 python scripts\run_formal_verifications.py；本地 mock provider 预检、字段覆盖、分页 trace 与密钥不泄露均已验证。
- 待确认 下一阶段是否进入增量同步任务队列、定时刷新策略，或接入用户提供的真实第三方 provider 样例。

## 二十一、阶段 30 发布判断

- 已确认 阶段 30 新增外部行情 Provider 本地同步任务机制：创建任务、列出任务、查询任务、手动运行和失败重试。
- 已确认 同步任务支持 symbols 列表、日期窗口、运行期增量游标、retry_count、run_count、last_run_at、last_error、row_count、sample_rows、provider_status 和 checks。
- 已确认 成功拉取行情时才推进 cursor_by_symbol；无 API Key、provider 跳过、空响应或失败时不推进游标。
- 已确认 配置中心前端新增“行情同步任务”面板，可创建任务、运行、重试并查看最近同步状态。
- 已确认 阶段 30 不引入 Redis/Celery/外部调度服务；固定间隔先以 next_run_hint 和本地运行期任务状态表达，后续可接入真实调度器。
- 待确认 下一阶段是否进入本地行情数据正式落库、查询 API 与数据质量缺口修复。
## 二十二、阶段 31 发布判断

- 已确认 阶段 31 新增本地规范化行情表 market_price_bars，按 symbol/date 主键保存 OHLCV、source 与 synced_at。
- 已确认 显式同步 /api/market/sync-price-history 会在原有 cache snapshot 之外写入 market_price_bars。
- 已确认 阶段 30 外部行情同步任务成功运行时也会写入同一张本地行情表；无 API Key 或失败不写入有效 rows。
- 已确认 新增 /api/market/local-price-bars 与 /api/market/local-price-bars/status，可按 symbol、日期窗口和 limit 查询本地存储行情与覆盖状态。
- 已确认 数据中心前端展示本地行情存储状态和本地 bars JSON，便于人工确认同步是否落入本地表。
- 已确认 新增 scripts/smoke_test_local_market_bar_storage.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入数据质量检查、缺口修复与重复/异常价格检测。
## 二十三、阶段 32 发布判断

- 已确认 阶段 32 新增本地行情质量检查能力：按 symbol/date window 检查 expected_count、stored_count、missing_dates、duplicate_count、invalid_rows 与 field_coverage。
- 已确认 OHLCV 异常检测覆盖 negative_price、negative_volume、high_below_low、high_below_open_or_close、low_above_open_or_close 和 non_numeric_ohlcv。
- 已确认 新增 /api/market/local-price-bars/quality，可返回本地数据质量报告和 repair_plan。
- 已确认 新增 /api/market/local-price-bars/repair-gaps，可按 repair_plan 复用现有 sync_price_history 补拉缺口区间。
- 已确认 数据中心前端新增质量状态、缺口数、异常数、质量报告 JSON 和“修复缺口”按钮。
- 已确认 新增 scripts/smoke_test_market_data_quality.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入数据浏览器与行情可视化增强，或先补交易日历驱动的缺口检测。
## 二十四、阶段 33 发布判断

- 已确认 阶段 33 新增本地数据浏览器聚合能力：symbols 覆盖摘要、当前 symbol 本地 bars、质量报告和同步历史。
- 已确认 新增 /api/market/data-browser，支持 symbol、start_date、end_date、limit 查询参数。
- 已确认 数据中心前端新增“本地数据浏览器”面板，展示本地 symbol 覆盖、K 线、表格、质量摘要和同步历史 JSON。
- 已确认 新增 scripts/smoke_test_market_data_browser.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入策略研究基础模型，或先补交易日历驱动的数据质量规则。
## 二十五、阶段 34 发布判断

- 已确认 阶段 34 新增策略研究任务模型：task_id、strategy_id、strategy_version、symbols、date_window、benchmark、frequency、parameters、parameter_schema、indicator_plan、signal_rules、signal_preview、research_outputs 与 risk_notes。
- 已确认 新增 /api/backtest/research-tasks 列表/创建接口，以及 /api/backtest/research-tasks/{task_id} 详情接口。
- 已确认 研究任务使用 var/runtime/strategy_research_tasks.json 本地持久化，不改变既有 run-once、parameter-scan 和 run-batch 行为。
- 已确认 Web 策略回测页新增策略研究任务面板，可基于当前策略和回测表单创建任务并展示信号预览。
- 已确认 新增 scripts/smoke_test_strategy_research_tasks.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入回测引擎 MVP 与研究任务消费链路。
## 二十六、阶段 35 发布判断

- 已确认 阶段 35 新增研究任务执行入口：POST /api/backtest/research-tasks/{task_id}/run。
- 已确认 研究任务可按 symbols 生成一个或多个 BacktestRunRequest，并复用现有 PersistentBacktestService 写入回测 run、metrics、logs、trades、positions、accounts 与 yearly_returns。
- 已确认 执行结果写回研究任务 last_execution，包含 run_ids、metrics、failures、research_binding 和 trade_artifacts 追踪信息。
- 已确认 Web 策略研究任务面板新增“执行回测”按钮，并展示执行结果 JSON。
- 已确认 新增 scripts/smoke_test_research_task_backtest_run.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入回测结果页与指标面板增强。## 二十七、阶段 36 发布判断

- 已确认 阶段 36 新增回测结果面板读取入口：GET /api/backtest/results/{run_id}/panel。
- 已确认 结果面板聚合 run summary、metrics、trades、positions、accounts、yearly_returns、logs 与 parameter_snapshot，复用本地 SQLite runtime 已持久化的回测产物。
- 已确认 Web 策略回测页新增“回测结果面板”，提交回测或执行研究任务回测后自动加载最新 run 结果。
- 已确认 新增 scripts/smoke_test_backtest_result_panel.py，并纳入 scripts/run_formal_verifications.py。
- 已确认 Python 编译、node --check、阶段 36 smoke、完整正式验证和 HTTP 新接口探测均通过。
- 待确认 下一阶段是否进入组合级回测聚合、权益曲线图和交易归因分析。

## 二十八、阶段 37 发布判断

- 已确认 阶段 37 新增单 run 派生曲线：equity_curve 与 drawdown_curve，基于本地持久化 accounts 快照计算。
- 已确认 新增组合级回测结果入口：GET /api/backtest/results/{run_id_prefix}/portfolio-panel。
- 已确认 组合面板按 run_id_prefix 聚合多个 run，返回 summary、rows、聚合 metrics、equity_curve 与 drawdown_curve。
- 已确认 研究任务执行结果返回 run_id_prefix，Web 多 run 研究任务执行后会加载组合面板。
- 已确认 Web 回测结果面板新增单 run 权益/回撤曲线和组合权益曲线展示。
- 已确认 新增 scripts/smoke_test_backtest_portfolio_panel.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入交易归因、风险指标扩展和结果分页/导出。

## 二十九、阶段 38 发布判断

- 已确认 阶段 38 新增单 run 交易归因 trade_attribution，包含买卖次数、成交额、净现金流、估算胜率、估算成本与计算口径。
- 已确认 新增单 run 风险指标 risk_metrics，基于 equity_curve/drawdown_curve 计算最大回撤、当前回撤、区间波动、最好/最差区间收益与修复状态。
- 已确认 新增持仓暴露 exposure_summary，返回最新持仓数、总市值、单票最大权重、快照时间与持仓标的。
- 已确认 组合面板聚合 trade_attribution，并基于组合权益曲线返回 risk_metrics。
- 已确认 Web 回测结果面板新增交易归因、风险指标和持仓暴露摘要卡。
- 已确认 新增 scripts/smoke_test_backtest_trade_risk_attribution.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入结果分页/导出、交易归因图表或策略参数实验管理。

## 三十、阶段 39 发布判断

- 已确认 阶段 39 新增回测结果明细分页/导出入口：GET /api/backtest/results/{run_id}/table。
- 已确认 明细接口支持 table、offset、limit、export_format 查询参数，覆盖 trades、positions、accounts、yearly_returns 与 logs。
- 已确认 CSV 导出以 JSON 响应内 content/content_type 返回，避免引入新的文件写入和下载状态。
- 已确认 新增实验分组入口：GET /api/backtest/experiments/{run_id_prefix}/panel，按 run_id_prefix 返回 run 列表、指标、参数和组合面板路径。
- 已确认 Web 回测结果面板新增交易明细分页、上一页/下一页、JSON/CSV 导出和实验分组 JSON 输出。
- 已确认 新增 scripts/smoke_test_backtest_result_pagination_exports.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入策略实验管理的持久化索引、结果筛选 UI 或报告联动导出。

## 三十一、阶段 40 发布判断

- 已确认 阶段 40 新增本地实验索引入口：GET /api/backtest/experiments、POST /api/backtest/experiments 与 GET /api/backtest/experiments/index/{experiment_id}。
- 已确认 研究任务执行成功后会按 run_id_prefix 自动登记实验索引，记录 name、description、tags、task_id、primary_run_id、status 与更新时间。
- 已确认 实验索引返回 report_links，可关联实验分组面板、组合面板、交易 CSV 导出、报告中心 run 详情与策略评价入口。
- 已确认 Web 策略回测页新增“实验索引”面板，可登记当前实验并查看索引 JSON。
- 已确认 新增 scripts/smoke_test_backtest_experiment_index.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入报告包联动导出、实验复盘视图、实验筛选/标签管理或浏览器文件下载流。

## 三十二、阶段 41 发布判断

- 已确认 阶段 41 新增实验级复盘入口：POST /api/reporting/experiments/{experiment_id}/review-package。
- 已确认 复盘入口会读取阶段 40 实验索引，定位 primary_run_id，并聚合 run_detail、strategy_evaluation、report_package、report_packages、review_links 与 export_links。
- 已确认 create_package=true 时会复用既有报告包能力，为实验主 run 生成可审计研究报告包，并返回 HTML/JSON/PDF/Word 导出链接。
- 已确认 Web 实验索引卡片新增“生成复盘”按钮，复盘结果输出到独立区域，便于从策略回测页直接进入实验复盘。
- 已确认 新增 scripts/smoke_test_experiment_review_package.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入实验筛选、标签、对比管理，或先把实验索引迁移到 SQLite。

## 三十三、阶段 42 发布判断

- 已确认 阶段 42 新增实验索引筛选能力：GET /api/backtest/experiments 支持 search、tag、status、include_archived 查询参数。
- 已确认 新增实验元数据更新入口：POST /api/backtest/experiments/index/{experiment_id}/update，可更新 name、description、tags、status、archived 与 review_note。
- 已确认 新增实验对比入口：POST /api/backtest/experiments/compare，可按 experiment_ids 聚合主 run 指标、风险摘要、交易数与复盘入口。
- 已确认 Web 实验索引面板新增搜索、标签、状态、归档筛选、刷新、选中对比、标记复盘和归档操作。
- 已确认 新增 scripts/smoke_test_experiment_filter_compare.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入策略评价指标体系增强，或优先把实验索引迁移到 SQLite。

## 三十四、阶段 43 发布判断

- 已确认 阶段 43 增强策略评价响应：StrategyEvaluationReportPayload 新增 diagnostics、score_breakdown 与 decision_flags。
- 已确认 /api/reporting/strategy-evaluation/{run_id} 的 7 维评分改为基于本地回测明细、账户曲线、交易活动、持仓暴露、成本参数和数据覆盖诊断生成。
- 已确认 报告包创建与 JSON 导出会固化阶段 43 诊断字段和 formula_version=stage43-diagnostic-score-v1。
- 已确认 Web 报告中心新增策略诊断摘要、决策旗标和评分明细输出区，保留原 7 维雷达图和维度卡片。
- 已确认 新增 scripts/smoke_test_strategy_evaluation_diagnostics.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入参数实验矩阵与批量回测，或先补更专业的图表化诊断视图。

## 三十五、阶段 44 发布判断

- 已确认 阶段 44 新增参数矩阵任务接口：GET/POST /api/backtest/parameter-matrix-tasks、GET /api/backtest/parameter-matrix-tasks/{task_id} 与 POST /api/backtest/parameter-matrix-tasks/{task_id}/run。
- 已确认 参数矩阵任务支持 base_parameters、parameter_grid、max_runs、planned_combinations、执行状态、最佳 run、最佳参数、失败列表和 ranked rows。
- 已确认 参数矩阵执行逐组合调用本地回测服务，按 score 排名，并将最佳 run 作为实验索引 primary_run_id 登记。
- 已确认 Web 策略编辑区新增“创建参数矩阵”和“执行参数矩阵”入口，执行后会加载最佳 run 面板、组合面板和实验索引。
- 已确认 新增 scripts/smoke_test_parameter_matrix_tasks.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入本地数据资产治理增强，或先补参数矩阵的图表化对比视图和失败重试 UI。

## 三十六、阶段 45 发布判断

- 已确认 阶段 45 新增本地行情数据资产治理入口：GET /api/market/local-price-bars/assets。
- 已确认 资产治理入口按 symbol 聚合 row_count、start_date、end_date、latest_synced_at、source_counts、quality_status、missing_count、invalid_count、duplicate_count 与 latest_sync_run。
- 已确认 每个资产返回 data_version，基于 symbol、日期范围、行数、最近同步、来源计数和质量状态生成稳定短指纹，便于后续回测报告追溯数据版本。
- 已确认 响应包含 manifest，声明 local_price_bars 范围、存储来源、版本规则、只读边界和验证命令。
- 已确认 Web 数据中心新增“本地数据资产”面板，展示资产卡和 manifest JSON。
- 已确认 新增 scripts/smoke_test_market_data_assets.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入回测数据版本绑定与报告级数据资产溯源，或先补本地数据库表结构治理。

## 三十七、阶段 46 发布判断

- 已确认 阶段 46 将阶段 45 的本地行情资产 data_version 绑定到回测 run。
- 已确认 PersistentBacktestService 支持注入 MarketDataService，回测完成后读取 /api/market/local-price-bars/assets 等价服务能力，并将 data_asset_trace 写入 run.extra_config。
- 已确认 回测结果面板新增 data_asset_trace，summary 暴露 data_asset_status 与 data_version，便于前端和下游报告读取。
- 已确认 报告包 manifest 新增 data_assets 字段，固化 status、symbol、data_version、quality_status、coverage_status、row_count、source_counts 与 trace_manifest。
- 已确认 报告包 data_quality_notes 增加 data_asset_trace/data_version 固化说明，且敏感密钥不落包。
- 已确认 新增 scripts/smoke_test_backtest_data_asset_trace.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入本地数据库表结构治理与资产目录持久化，或先补回测/报告页面的数据版本可视化。

## 三十八、阶段 47 发布判断

- 已确认 阶段 47 新增本地 SQLite 资产目录表 local_data_assets 与回测输入快照表 backtest_input_snapshots。
- 已确认 回测完成后会将 data_asset_trace 同步写入 backtest_input_snapshots，并刷新 local_data_assets 资产目录。
- 已确认 结果面板新增 input_snapshot 与 summary.input_snapshot_id，保留阶段 46 的 extra_config.data_asset_trace 兼容。
- 已确认 新增只读查询入口：GET /api/backtest/results/{run_id}/input-snapshot 与 GET /api/backtest/data-assets。
- 已确认 新增 scripts/smoke_test_backtest_input_snapshot_directory.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入 Web 数据版本可视化，或继续补实验级输入快照聚合与批量回测资产一致性检查。

## 三十九、阶段 48 发布判断

- 已确认 阶段 48 将回测结果面板的数据资产信息从 JSON 提升为 Web 可视化摘要：数据绑定状态、data_version、input_snapshot_id、质量状态、覆盖状态、行数和来源计数。
- 已确认 组合面板与实验面板新增 asset_consistency，支持 consistent、mixed、missing、empty 状态，并返回 run_count、missing_count、data_versions、data_version_count、snapshot_count 与 snapshot_ids。
- 已确认 组合 rows 与实验 rows 均暴露 data_version、input_snapshot_id 与 asset_key，便于批量回测和参数矩阵结果做输入一致性检查。
- 已确认 Web 回测结果区新增输入快照输出区与资产一致性摘要区，组合/实验面板刷新时同步展示一致性状态。
- 已确认 新增 scripts/smoke_test_asset_consistency_panels.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入历史资产目录批量迁移与筛选，或进入更完整的回测报告可视化分析。

## 四十、阶段 49 发布判断

- 已确认 阶段 49 扩展持久化回测资产目录查询，支持 symbol、dataset、data_version、quality_status、coverage_status 与 limit 筛选。
- 已确认 新增历史回测输入快照迁移诊断接口：POST /api/backtest/data-assets/migrate-input-snapshots，支持 dry_run 预检与显式执行。
- 已确认 迁移逻辑不会改写已有输入快照；已存在快照会返回 already_snapshotted，缺少 data_asset_trace 的历史 run 会返回 missing_trace。
- 已确认 Web 数据中心新增“回测资产目录”面板，支持筛选资产、查看 summary/JSON、执行迁移预检和迁移执行。
- 已确认 新增 scripts/smoke_test_data_asset_directory_filters_migration.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入回测报告可视化分析增强，或继续补资产目录的浏览器视觉回归与批量操作审计。

## 四十一、阶段 50 发布判断

- 已确认 阶段 50 扩展 StrategyEvaluationReportPayload，新增 analysis_summary 分析摘要层。
- 已确认 analysis_summary 汇总 verdict、headline、收益/风险/交易/成本/暴露/数据卡片、data_asset、warning_flags、watch_flags 与 action_items。
- 已确认 报告分析摘要会读取回测 extra_config.data_asset_trace，展示 data_version、quality_status、coverage_status、row_count 与 source_counts。
- 已确认 Web 报告中心新增“报告分析摘要”区域，展示分析 headline、摘要卡、数据资产溯源和行动项。
- 已确认 报告包与 JSON 导出会固化 stage50-report-analysis-v1。
- 已确认 新增 scripts/smoke_test_report_analysis_summary.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入报告视觉布局回归与图表打磨，或进入实验级报告对比视图。

## 四十二、阶段 51 发布判断

- 已确认 阶段 51 将报告分析摘要区域升级为专用视觉布局：report-analysis-panel、report-analysis-cards、report-asset-grid 与 report-action-list。
- 已确认 分析卡片、数据资产 chip 与行动项列表均增加响应式 CSS，避免长 data_version、source_counts 或行动项文本撑破布局。
- 已确认 当前环境未安装 Playwright，因此本阶段采用无新依赖的视觉契约验证，覆盖 HTML 节点、CSS 类、JS 渲染函数和报告分析 payload 可渲染性。
- 已确认 新增 scripts/smoke_test_report_visual_contract.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否安装浏览器验证依赖并做截图回归，或进入实验级报告对比视图。

## 四十三、阶段 52 发布判断

- 已确认 阶段 52 新增实验级报告对比接口：GET /api/reporting/experiments/{run_id_prefix}/comparison。
- 已确认 对比接口按 run 前缀聚合同组回测的 StrategyEvaluationReport，返回评分排名、verdict、收益风险、数据版本、质量状态和覆盖状态。
- 已确认 对比 summary 返回 best_run_id、worst_run_id、best_score、worst_score、data_version_count、missing_data_version_count 与 asset_consistency_status。
- 已确认 Web 报告中心新增“实验报告对比”区域，展示 summary、排名表和 JSON 明细。
- 已确认 新增 scripts/smoke_test_experiment_report_comparison.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入实验对比图表增强，或补报告包级实验对比导出。

## 四十四、阶段 53 发布判断

- 已确认 阶段 53 在实验报告对比视图中新增图表容器 report-experiment-comparison-charts。
- 已确认 Web 前端新增 renderExperimentComparisonCharts 与 renderComparisonBarSvg，展示评分排名、年化收益、最大回撤和数据版本一致性条。
- 已确认 新增 experiment-comparison-charts、comparison-chart 与 version-strip 样式，支持响应式单列降级。
- 已确认 新增 scripts/smoke_test_experiment_report_comparison_charts.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入报告包级实验对比导出，或补 Playwright 浏览器截图验证。

## 四十五、阶段 54 发布判断

- 已确认 阶段 54 新增实验对比报告包创建入口：POST /api/reporting/experiments/{run_id_prefix}/comparison-package。
- 已确认 报告包以 run_id_prefix 绑定同组实验对比，binding_mode 为 run_id_prefix_comparison，并固化 stage54-experiment-comparison-package-v1 manifest。
- 已确认 报告包 payload 固化 experiment_report_comparison、chart_source、manifest 与 data_quality_notes，chart_source 覆盖评分、年化收益、最大回撤和数据版本一致性图表源数据。
- 已确认 报告包导出复用既有 /api/reporting/report-packages/{package_id}/export，支持 JSON 与专用 HTML 模板展示实验对比摘要、排名表、图表源数据和数据质量边界。
- 已确认 Web 报告中心“实验报告对比”区新增“创建实验对比包”按钮，创建后可在报告包详情中查看并沿用现有导出按钮。
- 已确认 新增 scripts/smoke_test_experiment_report_comparison_package.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入实验对比包的批量导出/归档索引，或继续补 Playwright 浏览器截图验证。

## 四十六、阶段 55 发布判断

- 已确认 阶段 55 新增报告包归档目录入口：GET /api/reporting/report-packages，支持 run_id、package_type 与 limit 查询。
- 已确认 目录可统一展示普通研究报告包与实验对比报告包，返回 package_id、run_id、title、created_at、package_type、binding_mode、manifest_version、snapshot_id、workflow_id 与 export_links。
- 已确认 目录 summary 返回 package_count、type_counts、run_counts 与 filters，便于前端做归档浏览和筛选反馈。
- 已确认 Web 报告中心新增“报告包归档目录”面板，支持按 Run/实验前缀、包类型、数量刷新，并可点击目录项读取详情、设置当前导出包。
- 已确认 报告中心刷新时会同步当前 run_id 到归档目录输入，并自动加载当前 run 的报告包目录。
- 已确认 新增 scripts/smoke_test_report_package_directory.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入报告包批量归档/删除策略，或进入 Playwright 浏览器截图验证。

## 四十七、阶段 56 发布判断

- 已确认 阶段 56 新增报告包生命周期治理入口：POST /api/reporting/report-packages/{package_id}/lifecycle。
- 已确认 生命周期更新为非破坏性操作，只写入报告包 payload.lifecycle，不删除、不覆盖原始报告内容。
- 已确认 lifecycle 支持 status、retention_policy、protected、reason、updated_by、updated_at 与 audit_log，audit_log 记录最近 50 条生命周期变更。
- 已确认 报告包归档目录 GET /api/reporting/report-packages 支持 lifecycle_status 筛选，并在目录项返回 lifecycle_status、retention_policy、protected、lifecycle_updated_at 与 lifecycle_audit_count。
- 已确认 Web 报告中心归档目录新增生命周期筛选，以及恢复 active、标记 archived、标记 protected 三个非破坏性操作按钮。
- 已确认 新增 scripts/smoke_test_report_package_lifecycle.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入批量导出清单/离线报告包索引，或进入 Playwright 浏览器截图验证。

## 四十八、阶段 57 发布判断

- 已确认 阶段 57 新增报告包批量导出清单入口：GET /api/reporting/report-packages/export-manifest。
- 已确认 export manifest 复用报告包目录筛选，支持 run_id、package_type、lifecycle_status、formats 与 limit。
- 已确认 manifest 返回 manifest_id、stage57-report-package-export-manifest-v1、filters、formats、package_count、type_counts、lifecycle_counts、packages 与 offline_boundary。
- 已确认 packages 中包含 package_id、run_id、title、package_type、lifecycle_status、retention_policy、protected、manifest_version、binding_mode、snapshot_id、created_at 与按格式生成的 export_links。
- 已确认 offline_boundary 明确 manifest_only、no_files_written、no_package_deleted，阶段 57 不写压缩包、不删除报告包。
- 已确认 Web 报告中心归档目录新增“生成导出清单”按钮、导出格式输入和 manifest 输出区。
- 已确认 新增 scripts/smoke_test_report_package_export_manifest.py，并纳入 scripts/run_formal_verifications.py。
- 待确认 下一阶段是否进入真实离线文件包生成，或进入 Playwright 浏览器截图验证。

## 阶段 58：A 股真实源库只读接入

- 已接入旧项目 stockmarket.db 的 stock_list、stock_hist、stock_hist_qfq、stock_hist_hfq。
- 所有源库连接强制只读，Web/API 不修改旧库。
- 已暴露全库覆盖、复权状态、重复数量、更新时间与历史代码目录。
- 当前质量状态为 needs_attention：数据最晚为 2026-03-31，复权表更早，且存在重复。
- 下一准入门槛是规范化迁移、AKShare 增量补齐、最近完整交易日校验和用户人工抽检。


## 阶段 59：A 股规范库迁移与全市场增量同步

- 已完成旧库只读迁移、唯一键去重和三复权规范化存储。
- 已完成 AKShare 沪深北全市场增量同步至 2026-07-17。
- 已完成当前目录替换、断点目标清单、并发同步和结果 JSONL 审计。
- 已完成最新日覆盖率质量门槛与 raw OHLCV 全表检查。
- 已完成 689009 CDR 特殊证券数据路径。
- 当前发布状态为工程验收通过、用户人工数据验收待确认。
- 用户确认 A 股数据前，不进入策略编辑、保存和全股票并行回测。


## 阶段 59 用户验收门槛关闭

- 已确认：用户于 2026-07-18 完成 A 股数据人工验收。
- 已确认：阶段 59 状态为 completed。
- 已确认：下一主线切换为策略可编辑、可保存和全股票并行执行。
- 待规划：策略定义模型、版本管理、执行编排、并发资源边界和结果持久化。

## 阶段 60 版本化策略执行与双模式边界

- 自定义策略采用 `target-weights-v1` 契约，源码经 AST 校验后在独立子进程执行。
- 策略定义与不可变版本进入 SQLite，回测绑定 strategy_id、version、source_sha256。
- 阶段 60 完成单股票真实策略执行；阶段 61 建设全范围独立资金并发回测；阶段 62 建设共享资金池组合回测；阶段 63 建设双模式报告分析。
- 两种模式共享策略和数据快照，但账户语义、统计口径与报告结构严格区分。
## 阶段 61 独立选股全范围并发完成

- 已建立独立选股任务服务、SQLite 任务/逐股状态、后台线程与受控并发池。
- 已确认全 A股冻结范围为 5,528 只当前股票，来源为阶段 59 规范库。
- 建仓以有效 BUY 成交判定，绩效仅统计建仓标的，同时保留完整处理漏斗和失败原因。
- 真实三股并发与完整正式验证通过；Web Demo 8014 可创建、运行、轮询和浏览建仓结果。
- 下一阶段进入共享资金池、多股持仓和统一净值曲线，不复用独立资金汇总冒充组合结果。
## 阶段 62：共享资金池组合回测完成

- 已建立单一账户、多股共享现金、统一交易日和组合净值曲线。
- 已实现 T+1、100 股整手、先卖后买、现金约束、持仓上限、停牌估值和涨跌停近似约束。
- 已复用阶段 60 不可变策略版本和阶段 59 规范 A 股库，组合结果不由阶段 61 独立单股结果拼接。
- 组合成交、持仓、账户、指标和年度收益写入标准回测结果库，可由报告中心直接读取。
- 新增组合任务 API、Web 控制台及 `scripts/smoke_test_shared_portfolio_backtest.py`，完整正式验证通过。
- 下一阶段为阶段 63：分别强化独立选股汇总报告与共享资金池组合报告。
## 阶段 63：双模式专业分析报告完成

- 共享资金池组合报告复用当前 7 维策略评估模板，保持单一账户和组合净值语义。
- 独立选股报告仅统计实际建仓股票，新增正态性、置信区间、bootstrap、偏度/峰度、分位数、VaR/CVaR、盈亏比和收益直方图。
- 新增市场、首次建仓月份、历史行业、历史概念分组比较及分类覆盖率。
- 分类按首次建仓日 as-of 匹配有效期区间；禁止使用当前快照回填历史报告。
- AKShare/CNInfo 历史行业同步已验证；概念只接受带有效期和证据的数据导入，当前真实概念覆盖为 0%。
- 双模式报告 API、Web 报告中心、专用 smoke 和完整正式验证均已通过。
## 阶段 64｜历史分类批量同步与离线审计增强

- 新增可恢复的 A 股历史行业批量同步脚本与 `classification_sync_state` 状态表。
- 支持任务初始化、标的去重、重试、失败队列恢复和同步摘要。
- 默认串行抓取以规避 AKShare/`py_mini_racer` 的多线程运行时限制；外部 SSL 失败保留在任务状态中。
- 仅更新历史分类库，不写离线包、不删除数据。
- 全市场长耗时同步留待单独启动，不作为本阶段自动执行项。

## 阶段 65｜直接 CNInfo 并发与全市场自动恢复

- 历史行业获取已从 AKShare/py_mini_racer 切换为直接 CNInfo AES 签名 HTTP 客户端。
- 新增2工作线程、全局请求间隔和指数退避；支持一次启动处理全部剩余状态队列。
- 真实节流样本成功率8/10，完整正式验证全部通过。
- 全市场 pending 恢复任务正在运行，结束后再对 failed 队列执行低速回收。

## 阶段 65｜最终全市场验收

- 当前 A 股标的总数：5528。
- 成功取得历史行业数据：5292，数据覆盖率 95.73%。
- CNInfo 明确返回空记录：145，占比 2.62%。
- 成功或明确空记录合计：5437，已解析率 98.35%。
- 最终外部接口失败：91，占比 1.65%，全部为 CNInfo SSL EOF。
- 分类库实际保存行业区间：51410；最早生效日 1990-01-29，最新生效日 2026-07-16。
- 任务状态无 pending；最终失败保留在 classification_sync_state 中供后续增量回收。
- 阶段65发布判断：通过。残余1.65%属于已审计外部接口可用性边界，不阻塞本地回测与报告能力。
## 阶段 66｜双模式回测任务中心

- 新增 GET /api/backtest/mode-tasks，统一检索独立选股与共享资金池任务。
- 支持模式、状态、策略 ID、关键词和数量过滤，并输出统一策略绑定、日期窗口、进度及操作链接。
- Web 策略回测页新增统一任务中心，可筛选、选择、启动/恢复任务并跳转阶段 63 专业报告。
- 统一目录仅作为编排层，保留两种回测模式各自的资金与统计语义。
- 阶段 66 专用 smoke、阶段 63 报告 smoke 和完整正式验证全部通过。
## 阶段 67｜全市场回测性能与资源调度

- 独立选股任务改为有界动态批次，不再一次提交全部股票 Future。
- 股票上限默认 0 表示全部 A 股；并发 0 表示自动选择，最大支持 32。
- 每批结果使用 SQLite 批量事务，任务返回有效并发、批次、吞吐率、耗时和 ETA。
- 新增 pause、resume、cancel 控制，进程重启可恢复控制状态。
- 调度层合成基准：100/1000/5528 项分别耗时 0.0815/0.6632/3.1683 秒；该结果不代表真实策略吞吐。
- 阶段 61、66、67 smoke 与完整正式验证全部通过。
- 下一执行阶段为阶段 68B，之后为阶段 68A、阶段 68。