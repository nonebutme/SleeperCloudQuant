# Web MVP 验收报告

更新时间：2026-07-15

## 验收结论

- `已确认` 当前版本已从早期 Web Demo 升级为覆盖最初需求主功能域的 Web MVP。
- `已确认` Web MVP 已包含：总览、数据中心、因子分析、策略回测、AI 分析、报告中心、配置中心、重构溯源。
- `已确认` 当前 Web Demo 启动路由数为 37，包含市场、因子、回测、报告、AI、配置六类 API。
- `已确认` 当前可作为“本地化量化分析系统 Web MVP 验收基线”。
- `已确认` 阶段 17 已接入 `SleeperCloudQuant-old` 本地 SQLite 行情源；外部真实 provider 仍待确认。
- `已确认` 阶段 20 已完成研究报告包 manifest，报告详情与 HTML/JSON 导出可追踪数据源、runtime、LLM Provider 和验证命令。
- `已确认` 阶段 21 已完成报告包 PDF 与 Word-compatible `.doc` 最小导出。
- `已确认` 阶段 22 已完成报告包 4 页结构化 PDF 版式 smoke，并输出本地样例 PDF。
- `已确认` 阶段 23 已接入真实 rqalpha 包探测门禁与外部行情 HTTP Provider 门禁，未配置/未安装时安全 fallback。
- `已确认` 阶段 24 配置中心前端已支持外部行情 Provider 非密钥配置与 rqalpha runtime 本地/真实能力展示。
- `已确认` 阶段 25 rqalpha 本地替身层已支持策略模板、成本/滑点、benchmark 对齐和超额收益指标。
- `已确认` 阶段 26 外部行情 Provider mock 端到端已跑通，并在报告包 manifest 记录 external provider trace。
- `已确认` 阶段 27 外部行情 Provider 错误观测与 fallback source_trace 已完成，数据中心可展示 cache/upstream/primary/fallback 选择原因。
- `已确认` 阶段 28 真实行情 endpoint 字段映射、分页策略、重试配置和显式同步 trace 已完成。
- `已确认` 阶段 29 Provider 预检入口已完成，配置中心可执行非持久化连通性和字段映射验证。

## 页面验收矩阵

| 页面 | 当前覆盖 | 验收状态 | 仍为 demo / 待接入边界 |
| --- | --- | --- | --- |
| 总览 | 核心指标、研究闭环、五仓库覆盖、MVP 验收状态 | `已确认` 可验收 | 指标来自本地 demo/runtime 数据 |
| 数据中心 | K 线图、OHLC 表、交易日历、同步状态、外部 Provider/fallback source_trace、endpoint 字段映射与同步 trace | `已确认` 可验收 | 外部行情 HTTP Provider mock e2e、错误观测、字段映射和分页同步已通过；真实 endpoint/密钥与生产增量调度待确认 |
| 因子分析 | 因子定义、股票池、截面摘要、Top N 排名 | `已确认` 可验收 | 真实因子库、行业/财务因子扩展待接入 |
| 策略回测 | 策略库、策略编辑、版本历史、参数表单、参数扫描、rqalpha 本地配置、回测提交 | `已确认` 可验收 | 阶段 25 已完成本地 rqalpha 替身层；真实策略包执行待确认 |
| AI 分析 | TradingAgents 风格 workflow、分析师、研究辩论、风险委员会、组合经理、历史留痕 | `已确认` 可验收 | 阶段 19 已接入外部 LLM Provider 网关；未配置环境变量时 fallback 到本地 demo |
| 报告中心 | three2 风格 7 维报告、报告快照、参数扫描对比、AI 联动复盘、研究报告包、manifest、HTML/JSON/PDF/Word 导出 | `已确认` 可验收 | 严格 session/task 编排、真 docx 与 PNG 渲染级视觉 QA 待后续实现 |
| 配置中心 | 数据源、外部行情 Provider、Provider 预检、rqalpha Runtime、LLM、Agent、缓存、Profiles、运行时配置草稿 | `已确认` 可验收 | 不保存真实密钥；API Key 仍走环境变量，生产级密钥管理待确认 |
| 重构溯源 | 五仓库来源矩阵、采纳方式、新项目落点、验收页映射 | `已确认` 可验收 | 逐文件许可证法律复核待确认 |

## 已验证项

- `已确认` 需求基线已补齐：`project-scope.md`、`function-breakdown.md`、`business-flow.md`、`interaction-confirmation.md`。
- `已确认` 五仓库比较与复用整合方案已补齐：`repo-comparison.md`、`reuse-integration-plan.md`。
- `已确认` 数据中心趋势图已由普通趋势展示升级为 K 线图。
- `已确认` 策略回测已包含策略库、策略编辑、策略版本、参数 schema 表单和参数扫描。
- `已确认` AI 分析已尽量还原 TradingAgents-CN-main 的 analyst / debate / risk / portfolio manager 流程，并支持配置中心驱动。
- `已确认` 报告中心已参考 SleeperCloudQuant-old `three2.html` 形成 7 维策略评估报告，并支持快照、AI 联动、研究报告包、manifest 和 HTML/JSON/PDF/Word 导出。
- `已确认` 配置中心已按 TradingAgents-CN-main 风格展示数据源、LLM、Agent、缓存、Profiles 与运行时草稿。
- `已确认` Web 首页新增 MVP 验收状态面板，打开首屏即可判断各功能域覆盖情况。
- `已确认` 后端统一验证通过：`python scripts/run_formal_verifications.py`。
- `已确认` Web demo 可启动：`python scripts/run_formal_web_demo.py`。
- `已确认` 外部行情 Provider 401/成功/fallback source_trace 验证通过：`python scripts/smoke_test_external_market_observability.py`。
- `已确认` 外部行情 endpoint 字段映射、分页和同步 trace 验证通过：`python scripts/smoke_test_market_endpoint_mapping.py`。
- `已确认` 外部行情 Provider 预检验证通过：`python scripts/smoke_test_market_provider_preflight.py`。
- `已确认` 当前 Web Demo 入口：`http://127.0.0.1:8010`。

## 未验证项

- `未验证` 尚未进行浏览器截图级视觉 QA、多分辨率截图验收与 PDF PNG 渲染级视觉 QA。
- `已确认` 已接入本地旧 SQLite 行情源作为阶段 17 最小真实本地数据源。
- `已确认` 已接入本地 SQLite 行情驱动 runtime，并可将结果写入报告中心；真实 rqalpha 包仍待接入。
- `已确认` 已接入真实/外部 LLM Provider 网关与 workflow trace；未配置 `SCQ_LLM_BASE_URL`、`SCQ_LLM_API_KEY`、`SCQ_LLM_MODEL` 时安全 fallback。
- `已确认` 阶段 20 报告包 manifest 已通过端到端 smoke，详情、JSON 导出和 HTML 导出均包含 manifest。
- `已确认` 阶段 21 报告包导出 smoke 已验证 `.pdf` 和 Word-compatible `.doc` 文件元数据、内容和 manifest。
- `已确认` 阶段 22 报告包版式 smoke 已验证 PDF 4 页结构、页眉页脚、分区标题和 manifest；样例位于 `output/pdf/stage22-report-package-layout-smoke.pdf`。
- `已确认` 已完成许可证与复用方式工程基线复核：`docs/architecture/source-reuse-inventory.md`。
- `已确认` 完整许可证逐文件法律复核和文件级相似度扫描已暂缓为按需触发，不阻塞当前非商业 MVP 后续开发。
- `未验证` 尚未做生产级安全、权限、密钥管理和审计闭环。

## 阻塞原因

- 外部真实数据源仍需要用户确认供应商、授权方式、账号密钥、安全边界和缓存策略；阶段 17 已先使用本地旧 SQLite 只读接入。
- 真实 rqalpha 包接入仍需要确认环境依赖、数据接口、运行隔离和结果一致性基线；阶段 18 已先完成 rqalpha-compatible 本地 runtime 最小闭环。
- 外部 LLM Provider 已有 OpenAI-compatible 网关入口；Provider、模型、密钥管理、预算、输出合规提示与人工复核流程仍需用户确认后才会真实调用。
- 阶段 16A 已确认完整相似度扫描暂缓；但直接复制外部源码、页面、样式、模板、对外分发或商业用途前仍需单独复核。

## 潜在风险

- 当前 Web MVP 已可用于功能验收，但仍不能被解释为真实投资分析系统已经完成。
- 当前 AI 分析是本地结构化 TradingAgents 风格 workflow，不代表真实 LLM 推理质量。
- 当前回测 runtime 是 rqalpha-compatible 本地 SQLite 最小实现，用于验证接口和报告链路，不代表真实 rqalpha 包结果。
- 当前数据优先读取本地旧 SQLite 行情源，覆盖范围、复权、停牌、行业分类或财务数据完整性仍待扩展验证。
- 当前配置中心不保存真实密钥，不承担生产级密钥管理职责。

## 发布判断

- `已确认` 当前版本可以作为“满足最初需求、五仓库重构映射、全功能 Web MVP 展示”的本地验收版本。
- `已确认` 当前版本可以进入用户人工验收和视觉 QA。
- `已确认` 阶段 29 Provider 预检/连通性测试已完成；`待确认` 下一步进入阶段 30：增量同步任务队列、定时刷新策略，或接入真实第三方 provider 样例。











## 阶段 30 验收补充：增量同步任务队列与定时刷新策略

### 已验证项

- 配置中心 API 新增本地行情同步任务创建、列表、查询、运行和重试接口。
- 同步任务返回任务状态、symbols、日期窗口、增量游标、最近运行时间、失败原因、重试次数、样例行和 Provider 状态。
- 成功同步时推进 cursor_by_symbol；无 API Key 或 Provider 不可用时返回 skipped/needs_attention，且不推进游标。
- 配置中心前端新增任务创建表单、任务列表、运行/重试按钮和 JSON 结果输出区。
- 新增 scripts/smoke_test_market_provider_sync_tasks.py，并纳入 scripts/run_formal_verifications.py。

### 未验证项

- 尚未把同步结果正式写入本地行情数据表；阶段 30 仅完成运行期任务队列和可观测同步状态。
- 固定间隔刷新尚未接入后台常驻调度器；当前以本地运行期 schedule/next_run_hint 和手动触发为 MVP。

### 阻塞原因

- 正式落库、缺口修复和数据质量检查属于后续本地行情数据存储阶段，应在阶段 31/32 承接。

### 潜在风险

- 任务状态当前随 Web 进程生命周期存在，不适合作为长期审计记录。
- 真实第三方 Provider 的限流、交易日边界和分页 cursor 语义仍需在真实样例接入后复核。

### 发布判断

- 阶段 30 可作为从手动预检进入可管理同步机制的 MVP 基线；允许进入本地行情数据正式落库与查询 API 阶段。
## 阶段 31 验收补充：本地行情数据存储与查询 API

### 已验证项

- 新增 market_price_bars 规范化本地行情表，支持 symbol/date 主键 upsert。
- /api/market/sync-price-history 显式同步后写入本地行情表。
- 配置中心同步任务运行成功后写入同一张本地行情表。
- /api/market/local-price-bars 支持按 symbol、start_date、end_date、limit 查询本地 bars。
- /api/market/local-price-bars/status 返回 row_count、min_date、max_date 与 last_synced_at。
- 数据中心前端新增本地行情存储状态和本地 bars 输出区。
- 新增 scripts/smoke_test_local_market_bar_storage.py，并纳入正式验证。

### 未验证项

- 尚未实现缺口检测、异常价格检测、重复来源冲突策略和自动修复。
- 尚未对真实第三方 Provider 的复权、停牌、交易日边界和分钟级频率做专门建模。

### 阻塞原因

- 数据质量与缺口修复属于阶段 32，应在本地存储查询稳定后承接。

### 潜在风险

- 当前 market_price_bars 以日线 OHLCV 为主，频率字段尚未进入主键；后续若接入分钟线，需要扩展 frequency 维度。
- 真实 provider 的字段授权和复权语义仍需人工确认。

### 发布判断

- 阶段 31 可作为本地行情数据层 MVP 基线；允许进入数据质量检查与缺口修复阶段。
## 阶段 32 验收补充：数据质量检查与缺口修复

### 已验证项

- /api/market/local-price-bars/quality 可检查本地行情表在指定 symbol/date window 内的缺口、字段覆盖率和 OHLCV 异常。
- /api/market/local-price-bars/repair-gaps 可根据 repair_plan 复用现有同步能力补拉缺口区间。
- 数据中心前端展示质量状态、缺口数、异常数，并提供修复缺口按钮。
- 新增 scripts/smoke_test_market_data_quality.py，覆盖缺口检测、缺口修复、异常 OHLCV 检测与密钥不泄露。
- 已纳入 scripts/run_formal_verifications.py。

### 未验证项

- 当前缺口检测使用自然日窗口，不区分真实交易日和节假日。
- 尚未实现复权语义、分钟级频率质量检查、跨 provider 冲突比对。

### 阻塞原因

- 真实交易日历驱动的缺口检测需要后续将本地交易日历存储与 symbol 市场归属规则更紧密绑定。

### 潜在风险

- 自然日缺口检测会把周末/节假日也标记为缺口，适合 MVP 暴露问题，但不适合作为最终金融数据质量规则。
- 修复缺口依赖当前 Provider 返回范围数据的能力；若 Provider 只返回部分日期，需要继续保留 needs_attention 状态。

### 发布判断

- 阶段 32 可作为本地数据质量 MVP 基线；允许进入数据浏览器与行情可视化增强阶段。
## 阶段 33 验收补充：数据浏览器与行情可视化

### 已验证项

- /api/market/data-browser 返回本地 symbol 覆盖摘要、当前 symbol bars、质量报告和同步历史。
- 数据中心前端新增本地数据浏览器面板，展示 symbol 覆盖、K 线、表格和质量/同步历史 JSON。
- 新增 scripts/smoke_test_market_data_browser.py，覆盖多 symbol 同步后浏览器查询、质量状态、同步历史和密钥不泄露。
- 已纳入 scripts/run_formal_verifications.py。

### 未验证项

- 尚未实现可交互的 symbol 点击切换；当前随数据中心查询表单联动。
- 尚未实现分页、列排序、导出 CSV 和多频率切换。

### 阻塞原因

- 更完整的数据浏览器交互需要前端组件化拆分，适合后续产品打磨阶段处理。

### 潜在风险

- 当前 K 线仍使用轻量 SVG 渲染，适合 MVP 检查，不适合大规模分钟线高性能浏览。

### 发布判断

- 阶段 33 可作为本地行情可视化与数据检查入口；允许进入策略研究基础模型阶段。
## 阶段 34 验收补充：策略研究基础模型

### 已验证项

- /api/backtest/research-tasks 支持创建和列出本地策略研究任务。
- /api/backtest/research-tasks/{task_id} 支持读取研究任务详情。
- 研究任务包含策略绑定、参数 schema、指标计划、信号规则、信号预览、风险说明和 ready_for_backtest 标记。
- Web 策略回测页新增策略研究任务面板，可从当前策略/表单创建任务。
- 新增 scripts/smoke_test_strategy_research_tasks.py，并纳入正式验证。

### 未验证项

- 研究任务尚未直接驱动正式回测引擎执行。
- 信号预览当前为规则级样例，不是基于完整历史行情逐日计算出的真实信号序列。

### 阻塞原因

- 真实信号序列和回测消费链路属于阶段 35 回测引擎 MVP。

### 潜在风险

- 当前研究任务是本地 runtime 文件持久化，适合 MVP 追踪，不适合作为长期多用户任务系统。

### 发布判断

- 阶段 34 可作为策略研究任务与回测执行之间的基础契约；允许进入回测引擎 MVP 阶段。
## 阶段 35 验收补充：回测引擎 MVP

### 已验证项

- /api/backtest/research-tasks/{task_id}/run 可把研究任务转换为回测 run request 并执行。
- 执行结果返回 run_ids、metrics、failures、research_binding 和 trade_artifacts。
- 研究任务详情会写回 last_execution 与 backtest_completed 状态。
- Web 策略研究任务面板支持触发回测执行。
- 新增 scripts/smoke_test_research_task_backtest_run.py，并纳入正式验证。

### 未验证项

- 多 symbol 组合级绩效聚合尚未实现，目前每个 symbol 生成独立 run。
- 交易记录详情通过 runtime_store/reporting_run_id 追踪，尚未在研究任务响应中内嵌完整 trade rows。

### 阻塞原因

- 组合级回测、权益曲线合并和交易明细页属于阶段 36 回测结果页与指标面板增强。

### 潜在风险

- 当前执行仍依赖本地 SQLite runtime 与 fallback 数据，真实 rqalpha 包执行仍受环境门禁控制。

### 发布判断

- 阶段 35 可作为研究任务驱动回测执行的 MVP 基线；允许进入回测结果页与指标面板阶段。## 阶段 36 验收补充：回测结果页与指标面板

### 已验证项

- /api/backtest/results/{run_id}/panel 返回单次回测结果面板数据。
- 面板数据包含 summary、metrics、trades、positions、accounts、yearly_returns、logs 和 parameter_snapshot。
- Web 策略回测页新增结果面板，支持提交回测后自动展示指标、交易、持仓、账户、年度收益与参数快照。
- 研究任务执行回测后会加载第一条 run_id 对应的结果面板。
- 新增 scripts/smoke_test_backtest_result_panel.py，并纳入正式验证。

### 未验证项

- 尚未实现权益曲线交互图、交易点位图和组合级多 symbol 汇总。
- 尚未实现结果面板分页、导出和排序筛选。

### 阻塞原因

- 组合级聚合、权益曲线图和交易归因属于后续策略分析增强阶段。

### 潜在风险

- 当前表格直接渲染全部明细，适合 MVP 小样本；大规模分钟级回测需要分页或虚拟列表。

### 发布判断

- 阶段 36 可作为本地回测结果查看与指标确认的 MVP 基线；允许进入组合级回测聚合与策略评价增强阶段。

## 阶段 37 验收补充：组合级回测聚合与权益曲线增强

### 已验证项

- 单 run 结果面板返回 equity_curve 与 drawdown_curve。
- /api/backtest/results/{run_id_prefix}/portfolio-panel 返回组合级 summary、rows、metrics、equity_curve 和 drawdown_curve。
- 双标的研究任务执行后可按 run_id_prefix 聚合两个 run。
- Web 回测页新增单 run 曲线和组合面板输出区域。
- 新增 scripts/smoke_test_backtest_portfolio_panel.py，并纳入正式验证。

### 未验证项

- 组合聚合当前采用等权净值合成，尚未支持自定义权重、再平衡规则和组合级成交撮合。
- 曲线图为轻量 SVG 展示，尚未实现缩放、悬浮提示、分页或导出。

### 阻塞原因

- 真实组合级撮合、权重约束和交易归因需要更完整的组合模型与风险模型。

### 潜在风险

- 大规模分钟级或多标的回测明细仍需分页/采样，否则前端直接渲染可能变慢。

### 发布判断

- 阶段 37 可作为组合级回测结果观察与权益/回撤曲线 MVP；允许进入交易归因与风险指标增强阶段。

## 阶段 38 验收补充：交易归因与风险指标增强

### 已验证项

- 单 run 结果面板返回 trade_attribution、risk_metrics 和 exposure_summary。
- 组合面板返回聚合 trade_attribution 与组合级 risk_metrics。
- Web 回测页新增交易归因、风险指标和持仓暴露摘要展示。
- 新增 scripts/smoke_test_backtest_trade_risk_attribution.py，并纳入正式验证。
- HTTP 探测 /api/backtest/results/stage38-risk-001/panel 返回 completed、交易数和风险点数。

### 未验证项

- 当前胜率是基于平均成本与卖出价格的估算口径，不等价于完整逐笔税费后已实现盈亏。
- 当前成本影响使用配置费率估算，尚未接入真实成交回报中的逐笔费用字段。

### 阻塞原因

- 精确交易归因需要完整成交、费用、持仓批次和现金流水模型。

### 潜在风险

- 当前指标适合 MVP 诊断和可视化，不应用作正式投资绩效归因结论。

### 发布判断

- 阶段 38 可作为交易归因和风险指标 MVP；允许进入结果分页、导出与实验管理增强阶段。

## 阶段 39 验收补充：结果分页、导出与实验管理增强

### 已验证项

- /api/backtest/results/{run_id}/table 支持结果明细分页读取。
- /api/backtest/results/{run_id}/table 支持 CSV/JSON 内容导出。
- /api/backtest/experiments/{run_id_prefix}/panel 返回实验分组摘要、run rows 与组合面板路径。
- Web 回测页新增分页交易明细、上一页/下一页、JSON/CSV 导出和实验分组输出。
- 新增 scripts/smoke_test_backtest_result_pagination_exports.py，并纳入正式验证。
- HTTP 探测分页导出与实验分组接口通过。

### 未验证项

- 当前导出内容仍在 API JSON 内返回，尚未实现浏览器文件下载流。
- 实验分组按 run_id_prefix 读取，尚未建立独立实验元数据表和用户命名空间。

### 阻塞原因

- 完整实验管理需要新增实验索引、筛选条件持久化和报告联动策略。

### 潜在风险

- 大批量导出仍受单次 API 响应大小影响，后续需要服务端文件流或分片导出。

### 发布判断

- 阶段 39 可作为本地结果分页、轻量导出和实验分组 MVP；允许进入实验索引与报告联动增强阶段。

## 阶段 40 验收补充：实验索引与报告联动增强

### 已验证项

- /api/backtest/experiments 支持列出本地实验索引。
- /api/backtest/experiments 支持手动创建或更新实验索引。
- /api/backtest/experiments/index/{experiment_id} 支持按实验 ID 查询索引详情。
- 研究任务执行后可自动登记 run_id_prefix 对应实验索引，并绑定 primary_run_id。
- 实验索引返回 experiment_panel、portfolio_panel、trades_export_csv、reporting_run_detail 与 strategy_evaluation 等报告链接。
- Web 回测页新增实验索引面板和“登记当前实验”入口。
- 新增 scripts/smoke_test_backtest_experiment_index.py，并纳入正式验证。
- HTTP 探测实验索引创建与详情查询通过。

### 未验证项

- 实验索引仍使用本地 JSON 文件保存，尚未迁移到 SQLite 实验表。
- Web 面板目前展示索引 JSON 和简要列表，尚未实现筛选、标签编辑、排序和批量导出。

### 阻塞原因

- 完整实验复盘需要报告包导出、策略评价摘要和实验筛选视图进一步联动。

### 潜在风险

- 本地 JSON 索引适合 MVP 与个人本地使用；高并发或多用户写入场景需要数据库事务与权限模型。

### 发布判断

- 阶段 40 可作为实验索引与报告链接联动 MVP；允许进入报告包联动导出与实验复盘视图阶段。

## 阶段 41 验收补充：报告包联动导出与实验复盘视图

### 已验证项

- /api/reporting/experiments/{experiment_id}/review-package 支持从实验索引生成实验复盘响应。
- 复盘响应包含 experiment、primary_run_id、run_detail、strategy_evaluation、report_package、report_packages、review_links 与 export_links。
- create_package=true 时会创建主 run 研究报告包，并返回 HTML/JSON/PDF/Word 导出入口。
- Web 实验索引卡片新增“生成复盘”按钮，并将复盘 JSON 输出到独立区域。
- 新增 scripts/smoke_test_experiment_review_package.py，并纳入正式验证。
- HTTP 探测完整服务路径通过：创建研究任务、执行回测、生成实验索引、生成复盘报告包。

### 未验证项

- 当前实验复盘仍以 JSON 输出为主，尚未形成专门的图表化复盘视图。
- 实验复盘创建报告包时默认绑定 primary_run_id，尚未支持多 run 组合报告包的正式模板。

### 阻塞原因

- 多实验对比、标签筛选和组合级报告模板需要阶段 42 以后继续扩展。

### 潜在风险

- 复盘入口依赖本地实验索引中的 primary_run_id；如果索引缺失或主 run 被清理，会返回 needs_attention。

### 发布判断

- 阶段 41 可作为实验索引到报告包导出的复盘闭环 MVP；允许进入实验筛选、标签与对比管理阶段。

## 阶段 42 验收补充：实验筛选、标签与对比管理

### 已验证项

- /api/backtest/experiments 支持 search、tag、status 和 include_archived 筛选。
- /api/backtest/experiments/index/{experiment_id}/update 支持更新实验标签、状态、归档标记和复盘备注。
- /api/backtest/experiments/compare 支持多实验对比，返回排名、收益、回撤、Sharpe、交易数和复盘链接。
- Web 实验索引面板新增筛选控制、选中对比、标记复盘和归档操作。
- 新增 scripts/smoke_test_experiment_filter_compare.py，并纳入正式验证。
- HTTP 探测筛选、更新和对比接口通过。

### 未验证项

- 当前筛选和标签仍基于本地 JSON 实验索引，尚未迁移到 SQLite。
- 对比结果目前以 JSON 输出为主，尚未提供专门的对比图表和排序表格 UI。

### 阻塞原因

- 大规模实验查询、复杂标签管理和多维排序更适合在 SQLite 实验表落地后继续增强。

### 潜在风险

- JSON 索引适合个人本地 MVP；大量实验或并发写入时需要数据库事务和索引。

### 发布判断

- 阶段 42 可作为实验筛选、标签更新、归档和多实验对比 MVP；允许进入策略评价指标体系增强阶段。

## 阶段 43 验收补充：策略评价指标体系增强

### 已验证项

- /api/reporting/strategy-evaluation/{run_id} 返回 diagnostics、score_breakdown 和 decision_flags。
- diagnostics 覆盖 return、risk、stability、trade_quality、capacity_cost、exposure 与 data_quality。
- score_breakdown 返回 formula_version=stage43-diagnostic-score-v1 和 7 维分数。
- report package JSON 导出包含阶段 43 策略评价诊断字段。
- Web 报告中心新增策略诊断摘要、决策旗标和评分明细输出。
- 新增 scripts/smoke_test_strategy_evaluation_diagnostics.py，并纳入正式验证。
- HTTP 探测策略评价诊断字段通过。

### 未验证项

- 当前诊断仍以本地 MVP 回测明细为基础，尚未引入行业归因、样本外检验和真实容量模型。
- 前端诊断区仍是摘要卡与 JSON 明细，尚未提供专业交互图表。

### 阻塞原因

- 样本外、行业归因、容量和逐笔费用需要更完整的数据表与批量实验结果支撑。

### 潜在风险

- 阶段 43 评分公式是本地研究诊断口径，不可解释为实盘投资评级。

### 发布判断

- 阶段 43 可作为策略评价指标体系 MVP；允许进入参数实验矩阵与批量回测阶段。

## 阶段 44 验收补充：参数实验矩阵与批量回测

### 已验证项

- /api/backtest/parameter-matrix-tasks 支持创建和列出参数矩阵任务。
- /api/backtest/parameter-matrix-tasks/{task_id} 支持读取任务详情和 last_execution。
- /api/backtest/parameter-matrix-tasks/{task_id}/run 支持执行参数组合、生成 ranked rows、best_run_id 和 best_parameters。
- 参数矩阵执行后会登记实验索引，tags 包含 parameter_matrix，primary_run_id 指向最佳 run。
- Web 策略编辑区新增创建/执行参数矩阵入口，并联动最佳 run 面板、组合面板和实验索引。
- 新增 scripts/smoke_test_parameter_matrix_tasks.py，并纳入正式验证。
- HTTP 探测参数矩阵任务创建、执行和实验索引登记通过。

### 未验证项

- 当前参数矩阵结果仍以 JSON 输出为主，尚未形成专门的矩阵热力图或排序表格。
- rerun_failed_only 已预留执行参数，但尚未构造真实失败重试场景的端到端验证。

### 阻塞原因

- 图表化对比和更复杂失败重试需要更明确的任务队列 UI 与实验表结构。

### 潜在风险

- 当前矩阵执行仍是本地同步执行，过大参数网格会阻塞请求；后续需要后台任务队列或分片执行。

### 发布判断

- 阶段 44 可作为参数矩阵与批量回测 MVP；允许进入本地数据资产治理增强阶段。

## 阶段 45 验收补充：本地数据资产治理增强

### 已验证项

- /api/market/local-price-bars/assets 支持 symbol 与 limit 查询，返回本地行情资产清单。
- 资产清单包含 row_count、日期覆盖、最近同步、来源计数、质量状态、缺口/异常/重复计数和最新同步 run。
- 每个资产返回 data_version，可作为后续回测与报告的数据版本指纹。
- 响应 manifest 标明 scope=local_price_bars、storage、version_rule、只读边界和验证命令。
- Web 数据中心新增本地数据资产面板，展示资产摘要与 manifest JSON。
- 新增 scripts/smoke_test_market_data_assets.py，并纳入正式验证。
- Python 编译、node --check、阶段 45 smoke 和完整正式验证均通过。

### 未验证项

- 当前资产治理仍基于本地 SQLite 行情表和同步日志的只读聚合，尚未形成独立资产目录表。
- data_version 是轻量指纹，尚未绑定到每一次回测 run 的输入快照。

### 阻塞原因

- 回测级数据版本绑定需要在 backtest run 参数与报告包 manifest 中增加数据资产引用，适合下一阶段推进。

### 潜在风险

- 当前质量覆盖按自然日窗口计算，遇到真实交易日历、停牌或不同市场日历时可能高估缺口，需要后续用交易日历口径修正。

### 发布判断

- 阶段 45 可作为本地数据资产治理 MVP；允许进入回测数据版本绑定与报告级数据资产溯源阶段。

## 阶段 46 验收补充：回测数据版本绑定与报告级数据资产溯源

### 已验证项

- 回测完成后会把本地行情资产 data_asset_trace 写入 backtest run 的 extra_config。
- /api/backtest/results/{run_id}/panel 返回 data_asset_trace，summary 返回 data_asset_status 与 data_version。
- /api/reporting/run-detail/{run_id}/report-package 生成的 manifest 包含 data_assets，固化 data_version、质量状态、覆盖状态、行数、来源计数和 trace_manifest。
- 阶段 46 smoke 验证同步行情、执行回测、读取结果面板、创建报告包时 data_version 一致。
- 新增 scripts/smoke_test_backtest_data_asset_trace.py，并纳入正式验证。
- Python 编译、node --check、阶段 46 smoke 和完整正式验证均通过。 

### 未验证项

- 当前 data_asset_trace 写入 run.extra_config JSON，尚未拆成独立数据库表。
- Web 页面主要通过结果 JSON 和报告 manifest 查看数据版本，尚未增加专门的数据版本卡片。

### 阻塞原因

- 独立资产目录表、回测输入快照表和 UI 图表化需要进一步确定数据库治理范围。

### 潜在风险

- data_asset_trace 绑定发生在回测完成后，当前记录的是本地资产在完成时刻的只读摘要；若后续并发同步同一 symbol，需要更严格的输入快照冻结机制。

### 发布判断

- 阶段 46 可作为回测与报告的数据资产溯源 MVP；允许进入本地数据库表结构治理与资产目录持久化阶段。

## 阶段 47 验收补充：本地数据库表结构治理与资产目录持久化

### 已验证项

- SQLite runtime store 新增 local_data_assets 与 backtest_input_snapshots 表。
- 回测完成后自动持久化输入快照，并将对应数据资产写入资产目录。
- /api/backtest/results/{run_id}/input-snapshot 返回 run 绑定的持久化输入快照。
- /api/backtest/data-assets 支持 symbol 与 limit 查询，返回持久化资产目录和 summary。
- /api/backtest/results/{run_id}/panel 返回 input_snapshot 与 input_snapshot_id。
- 新增 scripts/smoke_test_backtest_input_snapshot_directory.py，并纳入正式验证。
- Python 编译、阶段 47 smoke 和完整正式验证均通过。

### 未验证项

- 当前资产目录只在回测完成时刷新，尚未对所有历史本地行情资产做一次性迁移扫描。
- Web 页面尚未增加专门的数据版本卡片，现阶段通过 API JSON 查看。

### 阻塞原因

- 历史资产批量迁移与可视化需要进一步确定数据量、筛选维度和 UI 展示方式。

### 潜在风险

- 新表为本地 MVP schema，后续若引入并发任务队列，需要补事务级输入快照冻结策略。

### 发布判断

- 阶段 47 可作为本地数据库资产目录和回测输入快照 MVP；允许进入 Web 数据版本可视化或实验级资产一致性检查阶段。

## 阶段 48 验收补充：Web 数据版本可视化与实验级资产一致性检查

### 已验证项

- /api/backtest/results/{run_id}/panel 返回 summary.data_version、summary.input_snapshot_id、input_snapshot 与 data_asset_trace，可供 Web 数据版本卡展示。
- /api/backtest/results/{run_id_prefix}/portfolio-panel 返回 asset_consistency，并在 summary 中暴露 asset_consistency_status 与 data_version_count。
- /api/backtest/experiments/{run_id_prefix}/panel 返回 asset_consistency，rows 包含 data_version、input_snapshot_id 与 asset_key。
- Web 回测结果面板新增数据版本摘要、输入快照输出和资产一致性摘要。
- 新增 scripts/smoke_test_asset_consistency_panels.py，并纳入正式验证。
- Python 编译、node --check、阶段 48 smoke 和完整正式验证均通过。

### 未验证项

- 尚未通过真实浏览器截图验收新 UI 视觉布局，仅完成 JS 语法与 HTTP/API 级验证。
- 历史已存在 run 若没有阶段 47 输入快照，资产一致性会按 missing 展示。

### 阻塞原因

- 当前阶段目标是可视化与一致性检查，历史 run 迁移和浏览器视觉回归可在下一阶段补齐。

### 潜在风险

- 若同一实验前缀混入不同 symbol 或不同时段数据版本，asset_consistency 会显示 mixed；这是预期风险提示，不会阻止读取结果。

### 发布判断

- 阶段 48 可作为 Web 数据版本可视化和实验级资产一致性检查 MVP；允许进入历史资产迁移、报告图表增强或回测分析解释层阶段。

## 阶段 49 验收补充：历史资产目录迁移与数据版本筛选增强

### 已验证项

- /api/backtest/data-assets 支持 symbol、dataset、data_version、quality_status、coverage_status 与 limit 筛选。
- /api/backtest/data-assets/migrate-input-snapshots 支持 dry_run 迁移预检与 dry_run=false 显式执行。
- 迁移接口能识别 already_snapshotted、planned、migrated 与 missing_trace 状态。
- Web 数据中心新增回测资产目录筛选、资产列表、目录 JSON 与迁移诊断输出。
- 新增 scripts/smoke_test_data_asset_directory_filters_migration.py，并纳入正式验证。
- Python 编译、node --check、阶段 49 smoke 和完整正式验证均通过。

### 未验证项

- 尚未用 Playwright 截图做新增 Web 面板的视觉回归。
- 当前迁移接口按 run_id_prefix 扫描，尚未加入更复杂的日期/策略筛选。

### 阻塞原因

- 阶段 49 聚焦数据资产目录与迁移诊断闭环，浏览器级布局验收和复杂批量筛选可后续补齐。

### 潜在风险

- 缺少阶段 46 data_asset_trace 的更早历史 run 无法自动补写输入快照，会以 missing_trace 暴露，需要人工决定是否按外部数据版本规则补录。

### 发布判断

- 阶段 49 可作为历史输入快照迁移诊断与回测资产目录筛选 MVP；允许进入回测报告可视化分析增强阶段。

## 阶段 50 验收补充：回测报告可视化分析增强

### 已验证项

- /api/reporting/strategy-evaluation/{run_id} 返回 analysis_summary，版本为 stage50-report-analysis-v1。
- analysis_summary 包含 verdict、headline、cards、data_asset、warning_flags、watch_flags 与 action_items。
- data_asset 能固化回测绑定的数据版本、质量状态、覆盖状态、行数和来源计数。
- Web 报告中心新增报告分析摘要、数据资产溯源和行动项区域。
- 报告包创建与 JSON 导出包含 analysis_summary。
- 新增 scripts/smoke_test_report_analysis_summary.py，并纳入正式验证。
- Python 编译、node --check、阶段 50 smoke 和完整正式验证均通过。

### 未验证项

- 尚未用 Playwright 做报告中心新增区域的截图回归。
- 当前 action_items 为规则化摘要，尚未引入 AI 解释或自然语言深度分析。

### 阻塞原因

- 阶段 50 聚焦后端可审计分析摘要与 Web 可读展示；浏览器视觉回归和 AI 报告解释层可独立推进。

### 潜在风险

- analysis_summary 依赖 run.extra_config.data_asset_trace；旧 run 若未绑定数据资产，会显示 not_bound 并提示重新运行或补齐快照。

### 发布判断

- 阶段 50 可作为回测报告可视化分析增强 MVP；允许进入报告视觉回归、实验报告对比或 AI 解释层阶段。

## 阶段 51 验收补充：报告视觉回归与图表打磨

### 已验证项

- Web 报告中心新增专用布局类 report-analysis-panel、report-analysis-cards、report-asset-grid 与 report-action-list。
- report-analysis-cards 渲染 6 类分析卡片，report-data-asset-summary 渲染资产 chip，report-action-items 渲染行动项列表。
- web/styles.css 新增分析卡片、数据资产 chip、行动项列表和移动端响应式规则。
- 新增 scripts/smoke_test_report_visual_contract.py，验证 HTML/CSS/JS 视觉契约与报告分析 payload 可渲染性。
- node --check、阶段 51 smoke 和完整正式验证均通过。

### 未验证项

- 当前环境未安装 Playwright，尚未执行真实浏览器截图与像素级布局回归。

### 阻塞原因

- 浏览器截图验证需要额外 Playwright/browser 依赖；阶段 51 未引入新依赖，先用无依赖契约验证覆盖结构和响应式规则。

### 潜在风险

- 无浏览器截图时，仍可能存在特定视口下的细微视觉问题；需在后续安装浏览器验证依赖后补 Playwright 截图验收。

### 发布判断

- 阶段 51 可作为报告分析区域视觉布局增强与无依赖视觉契约验证 MVP；允许进入截图回归依赖接入或实验级报告对比阶段。

## 阶段 52 验收补充：实验级报告对比视图

### 已验证项

- /api/reporting/experiments/{run_id_prefix}/comparison 能按前缀读取多个 run 并生成报告级横向对比。
- 对比 rows 包含 rank、run_id、score、verdict、total_return、annualized_return、max_drawdown、volatility、data_version、quality_status、coverage_status 与 action_count。
- 对比 summary 返回最佳/最差 run、数据版本数量、缺失版本数量和资产一致性状态。
- Web 报告中心新增实验报告对比 summary、表格和 JSON 输出。
- 新增 scripts/smoke_test_experiment_report_comparison.py，并纳入正式验证。
- Python 编译、node --check、阶段 52 smoke 和完整正式验证均通过。

### 未验证项

- 当前对比视图为表格和 summary，尚未做评分/收益/回撤的图表化对比。
- 尚未将实验报告对比固化为独立报告包导出。

### 阻塞原因

- 阶段 52 聚焦实验级报告对比 MVP；图表增强与导出可以在后续阶段独立推进。

### 潜在风险

- 对比接口依赖 run_id_prefix 约定；若实验命名不一致，需要用户通过明确前缀或实验索引映射进行查询。

### 发布判断

- 阶段 52 可作为实验级报告横向对比 MVP；允许进入实验对比图表增强或报告包级导出阶段。

## 阶段 53 验收补充：实验对比图表增强

### 已验证项

- Web 报告中心实验报告对比新增图表区 report-experiment-comparison-charts。
- 前端新增评分柱状图、年化收益柱状图、最大回撤柱状图和数据版本一致性条。
- 对比图表复用阶段 52 comparison rows 与 summary，不新增后端数据模型负担。
- CSS 新增 comparison-chart、experiment-comparison-charts 与 version-strip，并包含 980px 响应式规则。
- 新增 scripts/smoke_test_experiment_report_comparison_charts.py，并纳入正式验证。
- node --check、阶段 53 smoke 和完整正式验证均通过。

### 未验证项

- 当前仍未做 Playwright 真实浏览器截图回归。
- 图表当前为轻量 SVG，尚未支持交互筛选或 tooltip。

### 阻塞原因

- 浏览器截图需要额外依赖；交互式图表可作为后续独立增强。

### 潜在风险

- 当 run 数量非常多时，当前 SVG 会横向压缩；后续可增加分页、滚动或 Top N 过滤。

### 发布判断

- 阶段 53 可作为实验对比图表化 MVP；允许进入报告包级实验对比导出或浏览器截图回归阶段。

## 阶段 54 验收补充：报告包级实验对比导出

### 已验证项

- 新增 POST /api/reporting/experiments/{run_id_prefix}/comparison-package，可将阶段 52/53 的实验报告对比固化为报告包。
- 报告包 manifest 使用 stage54-experiment-comparison-package-v1，并记录 run_id_prefix、snapshot_id、package_id、导出格式和验证命令。
- 报告包 payload 包含 experiment_report_comparison、chart_source、manifest 与 data_quality_notes。
- JSON 导出包含实验对比 payload 与 manifest；HTML 导出使用专用模板展示实验对比摘要、排名表、图表源数据和数据质量边界。
- Web 报告中心新增“创建实验对比包”按钮，并在创建后更新报告包详情。
- 新增 scripts/smoke_test_experiment_report_comparison_package.py，并纳入正式验证。
- Python 编译、node --check、阶段 54 smoke 和完整正式验证均通过。

### 未验证项

- 尚未做 Playwright 真实浏览器截图回归。
- PDF/Word 当前沿用既有报告包导出链路，阶段 54 smoke 重点覆盖 JSON 与 HTML。

### 阻塞原因

- 浏览器截图仍依赖额外 Playwright/browser 环境；阶段 54 优先完成可审计报告包与导出链路闭环。

### 潜在风险

- 实验对比包依赖 run_id_prefix 约定；如果实验命名不稳定，需要后续接入实验索引选择器或显式 experiment_id 到 run 前缀映射。

### 发布判断

- 阶段 54 可作为报告包级实验对比导出 MVP；允许进入实验对比包归档索引、截图回归或更完整的研究报告分析增强阶段。

## 阶段 55 验收补充：报告包归档目录与管理增强

### 已验证项

- 新增 GET /api/reporting/report-packages 目录接口，支持 run_id、package_type、limit 查询。
- 目录接口可识别 research_report_package 与 experiment_report_comparison 两类报告包。
- 目录项包含 manifest_version、binding_mode、snapshot_id、workflow_id、best_run_id、asset_consistency_status 与 HTML/JSON/PDF/Word export_links。
- Web 报告中心新增“报告包归档目录”面板，支持筛选、刷新、列表展示和点击读取详情。
- 报告中心 loadReports 会同步当前 run_id 到归档目录并刷新目录。
- 新增 scripts/smoke_test_report_package_directory.py，并纳入正式验证。
- Python 编译、node --check、阶段 55 smoke 和完整正式验证均通过。

### 未验证项

- 尚未做真实浏览器截图回归。
- 尚未提供报告包删除、归档状态变更或批量导出操作。

### 阻塞原因

- 删除/归档状态变更属于数据生命周期策略，需要额外确认保留周期和审计边界；阶段 55 先提供只读目录管理能力。

### 潜在风险

- 当前目录按 SQLite report_packages 的 created_at 倒序和 limit 查询；当包数量很大时，需要后续增加分页游标或日期范围筛选。

### 发布判断

- 阶段 55 可作为报告包归档目录 MVP；允许进入批量归档策略、截图回归或报告包生命周期治理阶段。

## 阶段 56 验收补充：报告包生命周期治理

### 已验证项

- 新增 POST /api/reporting/report-packages/{package_id}/lifecycle，可更新报告包 lifecycle 元数据。
- lifecycle 更新为非破坏性操作，报告包原始 payload、manifest、导出链路均保留。
- lifecycle 包含 status、retention_policy、protected、reason、updated_by、updated_at 与 audit_log。
- 报告包目录支持 lifecycle_status 筛选，并展示生命周期状态、保留策略、保护标记和审计条数。
- Web 报告中心新增生命周期筛选，以及 active、archived、protected 三种状态操作按钮。
- 新增 scripts/smoke_test_report_package_lifecycle.py，并纳入正式验证。
- Python 编译、node --check、阶段 56 smoke 和完整正式验证均通过。

### 未验证项

- 尚未实现真实删除、批量归档、批量导出或外部归档存储。
- 尚未做 Playwright 浏览器截图回归。

### 阻塞原因

- 删除和外部归档涉及数据保留周期、审计责任与人工确认边界；阶段 56 先完成可审计、可回退的非破坏性生命周期标记。

### 潜在风险

- lifecycle 当前存储在 report_packages.payload_json 内；若未来报告包规模显著增长，可升级为独立 lifecycle 表以支持更高效查询。

### 发布判断

- 阶段 56 可作为报告包生命周期治理 MVP；允许进入批量导出清单、离线索引或浏览器截图验证阶段。

## 阶段 57 验收补充：报告包批量导出清单与离线索引

### 已验证项

- 新增 GET /api/reporting/report-packages/export-manifest，可基于目录筛选生成批量导出 manifest。
- manifest 支持 run_id、package_type、lifecycle_status、formats、limit 查询参数。
- manifest 固化 package 清单、导出格式、导出链接、类型分布、生命周期分布和离线边界。
- formats 会清洗为 html/json/pdf/word 合法集合，非法格式不会进入 manifest。
- Web 报告中心新增“生成导出清单”按钮、导出格式输入和导出清单输出区。
- 新增 scripts/smoke_test_report_package_export_manifest.py，并纳入正式验证。
- Python 编译、node --check、阶段 57 smoke 和完整正式验证均通过。

### 未验证项

- 当前仅生成 manifest，不写本地 zip/tar 文件，也不执行批量下载。
- 尚未做 Playwright 浏览器截图回归。

### 阻塞原因

- 真实离线文件包会引入本地文件写入、容量控制和保留策略，需要单独确认归档目录和清理边界；阶段 57 先完成 manifest-only 索引闭环。

### 潜在风险

- manifest 当前记录导出 endpoint 而非内容 hash；若后续需要长期离线审计，应增加导出内容快照或 hash 校验。

### 发布判断

- 阶段 57 可作为报告包批量导出清单与离线索引 MVP；允许进入真实离线包生成、导出 hash 校验或浏览器截图验证阶段。

## 阶段 58 A 股真实数据中心验证

- 已验证：真实 SQLite 源库只读连接。
- 已验证：5,496 个当前股票、5,747 个历史行情代码和 10,716,500 条不复权日线可由 API 统计。
- 已验证：000001 股票目录返回“平安银行”，2026-03-30/31 真实日线可查询。
- 已验证：Web 存在真实库总览、股票检索、复权选择、日期筛选、分页日线与 K 线控件。
- 已验证：python scripts/run_formal_verifications.py 全部通过。
- 未验证：补齐至最近完整交易日、规范化迁移后的全量一致性和用户人工抽检。
- 发布判断：阶段 58 只读浏览可验收；A 股完整数据尚不可判定通过。


## 阶段 59 A 股规范库与全市场增量验收

### 已验证项

- 旧 stockmarket.db 始终只读，规范库独立写入当前项目。
- raw/qfq/hfq 全量迁移完成，源重复记录由唯一键消解。
- AKShare 当前目录刷新为 5,528 只，目录总数 5,824。
- 三复权均补齐至 2026-07-17，最新日覆盖率均为 99.8915%。
- 三复权重复键均为 0，SQLite quick_check 为 ok。
- raw OHLC 全部有效，成交量无空值或负值。
- 000001、920000、689009 的三复权最近行情抽样通过。
- Web 已切换为项目规范库状态，并展示最新日覆盖率。
- 新增 scripts/smoke_test_a_share_full_market_quality.py 并纳入正式验证。

### 已知边界

- 6 只当前证券最后成交日早于 2026-07-17，属于交易状态差异。
- qfq/hfq 存在复权算法产生的非正历史价格；不伪造修正，策略使用时必须过滤。
- 东方财富历史接口在当前网络链路存在 TLS 问题，增量主链路使用 AKShare 新浪接口。

### 发布判断

- 工程质量门槛通过。
- 等待用户对 Web 数据中心执行人工抽检。
- 用户确认前，策略回测阶段继续冻结。

### 阶段 59 最终验证补充

- 完整正式验证全部通过。
- Web Demo 已在 http://127.0.0.1:8012 启动。
- HTTP 探测确认 source=canonical_a_share_sqlite、current=5528。
- raw/qfq/hfq 覆盖率均为 99.8915%。
- 000001 在 2026-07-17 的 raw/qfq/hfq 查询与页面规范库文案均通过。

## 阶段 59 用户人工验收

- 2026-07-18，用户明确确认“A股数据验收通过”。
- 阶段 59 发布状态由 awaiting_user_acceptance 更新为 completed。
- A 股数据阶段门槛关闭，允许进入策略回测能力建设。

## 阶段 60 版本化自定义策略验收

### 已验证项

- 策略定义和不可变版本写入独立 SQLite，保存源码、参数 Schema、SHA-256、校验状态和执行契约。
- `target-weights-v1` 策略源码经过 AST 校验，并在带超时的独立 Python 子进程执行。
- 两份不同自定义策略在相同行情上分别产生零交易和实际建仓，证明源码真实参与回测。
- 回测落盘原始结果包含 strategy_id、strategy_version、source_sha256 和 execution_contract。
- Web 支持新建策略、代码校验、保存新版本、显示 hash 和切换历史版本。
- 无效入口返回结构化校验问题；跳过校验直接保存时返回 HTTP 400。
- `node --check web/app.js`、Python 编译、阶段 60 smoke 和完整 `scripts/run_formal_verifications.py` 全部通过。
- Web Demo 已在 http://127.0.0.1:8013 启动；策略列表、校验、版本绑定回测和页面控件 HTTP 探测通过。

### 已确认后续边界

- 阶段 61：独立选股全范围并发回测，每只股票使用独立虚拟资金，仅建仓标的进入绩效汇总，同时保留完整筛选漏斗。
- 阶段 62：共享资金池多股组合回测，统一账户、现金、持仓、成交和净值时间轴。
- 阶段 63：报告中心分别输出独立选股汇总报告和共享资金池组合报告。

### 发布判断

- 阶段 60 工程验收通过；版本化策略真实执行能力可作为后续两种回测模式的统一策略基础。
- 全市场并发和共享资金池撮合尚未在阶段 60 实现，不应将当前单股票执行表述为双模式已完成。
## 阶段 61 独立选股并发回测验收

### 已验证项

- 回测行情入口已切换到阶段 59 A股规范库，支持 raw/qfq/hfq；规范库不可用时才使用旧 fallback。
- 全 A股股票池冻结探针确认当前股票 5,528 只，来源为 canonical_a_share_sqlite，并绑定策略 v1 与源码 hash。
- 后台任务、1 至 16 并发线程、单股独立策略子进程、0 至 3 次重试和中断恢复状态已实现。
- 三股模拟 smoke 验证 2 股建仓、1 股未建仓、失败重试和仅建仓统计口径。
- 真实规范库 raw 三股并发验证 3/3 完成、3 股建仓、0 失败。
- Web/HTTP 后台任务验证从 ready 进入 completed，进度、任务列表和建仓分页结果可查询。
- qfq 短窗口探针中一个标的无可用行时，任务正确记录为逐股失败并形成 partial_failed，没有静默混入绩效汇总。
- Web 新增全部 A股/交易所/指定代码、日期、复权、股票上限、并发、重试和单股资金控制。
- 阶段 61 smoke 已纳入完整 scripts/run_formal_verifications.py；完整正式验证全部通过。
- Web Demo 已在 http://127.0.0.1:8014 启动，错误日志为空。

### 发布判断

- 阶段 61 工程验收通过；独立资金全范围并发任务已经具备创建、执行、恢复、漏斗和建仓结果查询能力。
- 5,528 只全市场任务仅验证了股票池冻结，本轮没有自动启动耗时的完整全市场回测。
- 本阶段不是共享资金池组合回测；组合账户语义继续进入阶段 62。
## 阶段 62 共享资金池组合回测验收

### 已验证项

- 一个初始资金账户覆盖全部入选股票，现金、持仓和净值按统一交易日推进。
- T+1、100 股整手、先卖后买、费用、滑点、持仓上限、停牌估值和涨跌停近似规则已进入撮合。
- 组合任务支持冻结股票池、后台执行、中断恢复、策略版本/hash 绑定和失败原因记录。
- 专用 smoke 与完整 `scripts/run_formal_verifications.py` 全部通过。
- Web Demo `http://127.0.0.1:8015` 的组合任务控件和 API 可访问。
- 真实规范库 HTTP 任务 `stage62-http-real` 使用 000001、600000，执行状态 completed，58 个账户点、95 笔成交、2 个最终持仓。
- 标准报告面板成功读取 `stage62-http-real-shared-portfolio` 的指标、成交、持仓、账户、风险和敞口数据。

### 已知边界

- 当前为日线收盘撮合，不模拟盘口深度和盘中成交顺序。
- 涨跌停是按证券类型近似，尚未建立逐日规则变更库。
- 本轮验证真实两股任务和全市场股票池冻结能力，未自动运行 5,528 只全市场长周期组合任务。

### 发布判断

- 阶段 62 工程验收通过。共享资金池组合模式已形成可运行、可持久化、可由报告中心读取的闭环。
## 阶段 63 双模式专业分析报告验收

### 已验证项

- 共享资金池任务 `stage62-http-real` 成功生成当前 7 维专业模板报告，返回 7 个维度和综合评分。
- 独立任务 `stage61-http-three-probe` 仅统计 3 个实际建仓样本，未建仓与失败样本不进入收益分布。
- 3 个样本少于 Jarque-Bera 最小检验门槛，接口正确返回 `insufficient_sample`，未伪造正态结论。
- 均值置信区间、bootstrap 区间、分位数、偏度/峰度、亏损概率、VaR/CVaR 和分组比较字段可读。
- 000001、000002、000006 的历史行业已按 CNInfo 变更记录同步，真实任务行业覆盖率为 100%。
- 历史行业比较产生“货币金融服务”和“房地产业”分组。
- 概念历史成分没有可靠公共接口，当前覆盖率为 0%，报告未使用当前概念快照回填。
- `node --check web/app.js`、阶段 63 smoke、API/HTTP smoke 和完整正式验证全部通过。
- Web Demo `http://127.0.0.1:8015` 已加载双模式报告控件与 API。

### 发布判断

- 阶段 63 工程验收通过。历史概念数据属于透明的数据覆盖缺口，不影响市场、建仓时段、历史行业和统计数学报告使用。
## 阶段 64｜历史分类批量同步与离线审计增强

- 分类批量同步状态机冒烟通过：去重、完成、失败与恢复队列均已验证。
- 真实有限样本同步通过：1 个标的写入 10 个历史行业区间。
- 完整 `scripts/run_formal_verifications.py` 全部通过。
- 已知边界：CNInfo 存在瞬时 SSL 波动；全市场 5528 标的历史同步尚未自动执行。

## 阶段 65｜直接 CNInfo 并发与全市场自动恢复

- 已移除逐请求 JavaScript 引擎依赖，纯 Python AES 签名真实返回行业历史。
- 1标的与4标的样本全部成功；10标的节流样本8个成功、2个可恢复失败。
- 20标的突发压测确认 CNInfo 存在 TLS/限流边界，生产参数固定为2并发、2秒全局间隔。
- 完整正式验证全部通过；全市场任务仍在运行，最终覆盖率待任务结束后确认。

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

- 已验证统一目录同时返回独立选股和共享资金池任务，并按更新时间倒序排列。
- 已验证 mode、status、strategy_id、search 和 limit 过滤。
- 已验证策略 ID、版本、源码 hash、日期窗口、复权、股票池、进度和 Run ID 统一输出。
- 已验证 Web 任务中心具备筛选、刷新、选择、启动/恢复和双模式专业报告跳转控件。
- node --check、Python 编译、阶段 66 smoke、阶段 63 报告 smoke 和完整正式验证全部通过。

### 发布判断

- 阶段 66 工程验收通过。任务中心未改变独立虚拟资金和共享资金池的既有计算语义。
## 阶段 67｜全市场回测性能与资源调度

- 已验证股票上限 0 可冻结全部股票，不再需要每次手工限制 100 只。
- 已验证动态有界批次、自动并发和批量 SQLite 状态写入。
- 已验证暂停只完成当前批次，恢复继续剩余股票。
- 已验证取消任务将剩余股票标记 canceled，且不生成建仓绩效汇总。
- 已验证 Web 展示有效并发、批次、吞吐率、已耗时与预计剩余时间。
- 真实 HTTP 创建并取消 5 只任务成功，统一任务目录包含遥测。
- 最新代码状态的完整正式验证全部通过。

### 发布判断

- 阶段 67 工程验收通过。5528 项合成基准仅证明调度开销已解除，真实策略全市场耗时留待阶段 69 业务验收。
## 阶段 68B｜策略回测界面用户友好化改造

- 已验证四步流程状态与任务总览、策略管理、独立选股、共享资金池、结果分析五视图。
- 已验证默认只展示任务总览，视图切换不会同时铺开全部技术面板。
- 已验证双模式配置摘要、高级参数折叠及任务状态化操作按钮。
- 已验证策略卡点击事件不会误绑定双模式任务卡。
- 已验证 1440×1200 桌面视口与 390×844 移动视口无重叠和溢出。
- JavaScript 语法、Python 编译、阶段 68B smoke 与完整正式验证全部通过。

### 发布判断

- 阶段 68B 工程验收通过。界面改造未改变独立虚拟资金与共享资金池的计算语义。
## 阶段 68：策略库管理可用性验收

### 已验证项

- 活动策略库返回 4 条策略，包含 dual_ma_atr_dynamic_stop。
- Web 支持搜索、分类筛选、刷新、新建、编辑、保存新版本、软删除和版本历史查看。
- 分类为选择控件，参数按 Schema 使用数字、选项或开关控件。
- HTTP 临时策略创建、归档隐藏和历史保留链路通过。
- 桌面与 390x844 移动视口显示正常，策略列表、编辑区和操作按钮无关键重叠。
- Stage 68 CRUD smoke、Stage 60 版本策略 smoke、Stage 68B UI smoke 和 JavaScript 语法检查通过。

### 已知边界

- 删除为软归档，不物理删除版本和回测引用。
- 本次不改变独立选股与共享资金池回测计算语义。
- 历史实验对比处理函数尚未实现，但已隔离为可选绑定，不再影响页面初始化。

### 发布判断

- 策略管理 CRUD 和策略选择界面达到本地 Web 验收条件。
- Web Demo 验收地址：http://127.0.0.1:8018/?page=backtest。
- 完整 python scripts/run_formal_verifications.py：全部通过。

## 阶段 68：回测任务流程与进度可视化验收

### 已验证项

- 六个回测工作区和五步任务流程可正常切换。
- 任务总览显示单股、独立选股和共享资金池三类状态板。
- 双模式任务目录显示状态、进度条、处理量、日期范围、策略版本和操作入口。
- 独立选股真实进度显示 10/10、100%、耗时和吞吐。
- 真实单股浏览器探针从 running 切换为 completed，并自动进入结果分析。
- 已完成任务的结果和专业报告入口可用。
- 技术 JSON 默认折叠。
- 桌面和 390x844 移动视口无关键控件重叠。

### 进度边界

- 独立选股百分比来自后端任务 progress。
- 单股和共享资金池在没有后端细粒度计数时使用阶段型不确定进度，不显示虚构百分比。

### 发布判断

- 回测任务流程、进度展示和结果入口达到本地 Web 验收条件。
- 验收地址：http://127.0.0.1:8018/?page=backtest。

- 2026-07-21：Stage 68 全量正式验证全部通过；单股、独立选股、共享资金池、策略库、统一任务目录与报告链路回归通过。

- 2026-07-21：Stage 69 回测任务交互与进度语义验收通过；40 股真实任务可连续观察中间进度，Edge 创建任务交互通过，全量正式验证全部通过。
