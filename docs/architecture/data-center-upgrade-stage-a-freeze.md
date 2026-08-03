# 数据中心升级阶段 A：设计与契约冻结

## 1. 文档状态

- 项目：`SleeperCloudQuant`
- 冻结日期：`2026-07-30`
- 状态：`阶段 A 已冻结；阶段 B1—B4 与阶段 C 已于 2026-07-30 完成，阶段 D 待批准`
- 输入：《数据中心升级方案（修订版）》与当前阶段 86 候选基线
- 适用范围：数据中心 M0—M5
- 非目标：阶段 87 独立因子研究、策略信号、回测调度、实盘交易

本文冻结升级目标、业务语义、数据分类、交互状态、接口方向和迁移边界。阶段 B/C 的实际完成范围和验证结果分别以 `docs/architecture/data-center-upgrade-stage-b-implementation.md`、`docs/architecture/data-center-upgrade-stage-c-implementation.md` 为准；阶段 D 在验收前不得表述为已上线。

## 2. 已批准的总裁决

1. 采用兼容式升级，不引入 Celery、Redis、WebSocket、Vue 或 Pinia。
2. 继续使用 SQLite 持久任务、独立后台进程和前端轮询。
3. 数据业务同步改为人工创建；保留任务恢复，阶段 B 再暂停自动创建每日任务。
4. 保留“原始观察可落库、未通过质量门禁不得正式发布”的治理模型。
5. 数据中心第七层使用“治理与参考事实层”，不使用“信号层”。
6. 第一轮任务保持单数据集，不实现多数据集父子任务。
7. 数据源只允许从受控白名单注册，未验证来源默认停用。
8. M4 第一轮不实现多资产叠加、概念点时成分和全球指数。
9. 最新发布版本不自动成为默认研究版本。
10. 实施顺序固定为阶段 A → B → C → D；每阶段完成后人工确认下一阶段。

## 3. 现有基线与复用边界

```text
原生 HTML / CSS / JavaScript
  -> /api/data-center/*
  -> DataCenterService
     -> DataCenterStore
     -> AShareSyncScheduler
     -> MarketPanoramaService
     -> AShareGovernanceStore
     -> AShareMarketStore
  -> SQLite
```

继续复用：

- `RouteDefinition` 与标准库 HTTP 适配器。
- `DataCenterService` 聚合门面。
- `data_source_routes` 路由表。
- `market_incremental_sync_jobs/items` 与 `panorama_sync_jobs/items`。
- 独立 Python 同步工作进程。
- 启动恢复、优雅停止和失败项重试。
- 质量问题、处置记录和人工修正覆盖层。
- 不可变数据版本、质量报告和默认版本指针。
- 全局 Quant UI Token 与 VisActor VTable。

明确不做：

- 不增加 Redis、Celery 或 WebSocket 服务。
- 不将前端迁移到 Vue/Pinia。
- 不以 Pandas `DataFrame` 作为跨层强制公共类型。
- 不开放任意 Python Provider 或任意 URL 执行。

后台任务语义：

- 页面关闭或切换模块不终止已启动的独立工作进程。
- 页面重新打开后从 SQLite 恢复状态。
- 运行中任务默认每 3 秒轮询。
- 轮询失败显示“监控连接中断”，不得误标任务失败。
- 工作进程异常退出时任务进入 `interrupted`，允许恢复或重试。

## 4. 七大数据层冻结

| 层级 | 正式名称 | 数据集示例 | 阶段 B 可见性 |
| --- | --- | --- | --- |
| L1 | 行情层 | A股日线、指数日线、板块日线、板块资金流 | 已接入项显示 |
| L2 | 证券基础层 | 证券目录、市场、上市状态、代码映射 | 已接入项显示 |
| L3 | 公司与财务层 | 公司行动、分红送配、财务报表 | 公司行动显示；财务默认停用 |
| L4 | 行业与概念层 | 行业区间、行业板块、概念板块 | 已接入项显示 |
| L5 | 资金面层 | 行业资金流、概念资金流 | 已接入项显示并标注覆盖 |
| L6 | 公告、新闻与研报层 | 公告、新闻、研报目录 | 公告/新闻显示；研报待验证 |
| L7 | 治理与参考事实层 | 日历、停复牌、生命周期、质量、版本 | 已接入项显示 |

硬约束：

- 因子值、策略信号、回测任务和交易执行不得进入七层数据目录。
- “待接入”节点默认折叠，不与可用数据混排。
- 每个叶子节点必须绑定唯一稳定的 `dataset_id`。
- 未建立规范表、字段契约和来源证据的数据集不得标记为“已接入”。

## 5. 受控数据源注册表契约

数据源回答“谁提供能力”，路由回答“某数据集按什么顺序使用哪些能力”。

```text
SourceDefinition
  source_id / display_name / provider_type / upstream_name
  enabled / verification_status / allowed_hosts
  secret_env_names / rate_limit / concurrency / retry_policy

DatasetRoute
  route_id / dataset_id / source_id / endpoint_id
  priority / enabled / fallback_policy / mapping_version
```

数据源状态：

- `verified`：实现、契约和最小真实探测均通过。
- `candidate`：允许展示但默认停用。
- `disabled`：已注册但禁止任务调用。
- `rejected`：不满足来源、稳定性或安全边界。

规则：

- 阶段 B 只允许 `verified` 数据源用于正式路由。
- 不允许上传或输入可执行 Python。
- 不允许绕过白名单访问任意主机。
- 只保存密钥环境变量名，不读取或回显真实值。
- 测试连接只读取最小样本，写入数必须为 0。
- Provider 内部可以使用 DataFrame，但进入服务边界前必须转换为标准记录。

标准输出：

```text
ProviderResult
  status / source_id / endpoint_id / dataset_id / observed_at
  records / schema_version / source_evidence / warnings
```

## 6. 路由策略冻结

支持：

- `primary`：成功且满足字段契约即停止。
- `fill_missing`：只补充主源明确缺失的字段或记录。
- `on_failure`：主源失败后才调用。

约束：

1. 优先级使用可审计整数，UI 同时提供上移、下移和数字输入。
2. 同一数据集只能有一个最高优先级 `primary`。
3. 回退源不得静默覆盖主源已有非空值。
4. 每条记录保留实际命中的源和端点。
5. 路由修改只影响之后创建的新任务。
6. 运行中和历史任务使用任务创建时冻结的路由快照。

## 7. 同步任务契约冻结

阶段 B 一个任务只允许一个 `dataset_id`：

```text
SyncRequest
  dataset_id
  mode=incremental
  target_trade_date
  scope
  symbols
  adjustment
  selected_shards
```

全量重建继续阻断，必须有新备份、影响预览、单独批准并保护当前默认版本。

任务创建前强制预览：目标数据集、路由摘要、目标日期、范围、分片、预计请求、预计写入、已有覆盖、风险与阻断。预览不调用 Provider、不创建任务、不写规范数据。

分片沿用现有语义：

- A股日线：证券 × 复权口径。
- 板块历史/资金流：板块代码。
- 公告新闻：股票代码或明确市场范围。
- 分类修复：失败证券。

用户可以在预览阶段取消分片；创建后分片集合冻结。

任务状态机：

```text
previewed -> queued -> running -> validating -> published
running -> stopping -> stopped
running -> interrupted -> queued/running
running -> partial_failure -> queued/running
running/validating -> failed
queued -> completed_noop
```

- `published`：质量门禁通过并产生不可变版本。
- `completed_noop`：没有需要补齐的工作项。
- `partial_failure`：部分工作项失败或隔离，未整体发布。
- `failed`：任务或质量门禁失败。
- `interrupted`：工作进程异常退出，可恢复。
- `stopped`：人工优雅停止。

阶段 B 实施时停止自动创建每日同步任务，但保留启动恢复和运行中任务监控；不自动创建任务、不自动发布、不自动切换默认版本。

## 8. 质量治理契约冻结

- 原始观察允许进入规范观察表。
- 异常观察必须产生质量问题。
- 未通过质量门禁的数据不得进入新的正式版本。
- 默认研究版本只能引用已发布版本。
- 人工修正使用覆盖层，原始观察不可覆盖。

质量问题状态：

| 内部状态 | 中文 |
| --- | --- |
| open | 待处理 |
| quarantined | 已隔离 |
| accepted | 接受原观察 |
| rejected | 拒绝原观察 |
| corrected | 已人工修正 |
| superseded | 已被新观察取代 |

沿用处置动作：`accept`、`reject`、`quarantine`、`correct`。

“重新拉取”不直接改变原问题状态：创建受控重拉任务、绑定原 `issue_id`、新结果再次检测；原问题只有在人工处置或新观察明确取代后才变更。

所有处置记录问题编号、动作、原因、操作者、时间、前后值、来源任务和关联观察。批量处置只允许同一数据集、同一规则、同一动作、同一原因，并强制二次确认。

## 9. 版本语义冻结

必须同时区分：

1. 当前默认研究版本。
2. 最新已发布版本。
3. 最新观察日期。

- “观察”不是版本。
- “发布”不等于“设为默认”。
- `superseded` 版本仍可成为默认，以保持旧研究复现。
- 切换默认版本不影响已绑定旧版本的 Run。
- 历史版本不得删除。

M0 与 M5 必须同时展示默认版本和最新发布版本；两者不同时显示解释性提示。

## 10. M0—M5 目标 UX 冻结

### M0 总览指挥舱

- 首屏回答“当前能否开展研究”。
- 展示研究就绪、默认版本、最新发布、正式截止日、最新观察日、阻断异常、最近人工同步。
- 每行最多 4 张指标卡，不使用持续脉冲动画。
- “一键补全”改为“生成缺口同步预览”。
- A股三复权继续同表比较。
- 增加最近 5 个关键版本的简化时间轴。
- 日历热力图只表达有真实覆盖和质量证据的日期。

### M1 数据源管理中心

子视图：数据源配置、源路由配置。

- 数据源配置展示受控源、验证状态、上游、允许主机、限频、环境变量名和只读探测。
- 源路由配置展示七层树、VTable 路由、优先级、回退策略、映射版本和测试。

### M2 同步执行器

- 七层树形单选数据集。
- 按数据集动态显隐字段。
- 强制先预览再创建任务。
- 当前任务摘要与异常快讯。
- 可选择的分片 VTable。
- 历史任务默认折叠。
- 优雅停止、仅重试失败项。
- 异常快讯跳转 M3 并携带 `source_task_id`。
- 全量重建为禁用项并说明审批边界。

### M3 质量纠错工坊

- 摘要：待处理、隔离、接受、拒绝、修正、阻断。
- 支持状态、严重度、数据集、代码、日期、规则、来源任务筛选。
- VTable 异常列表，正式详情面板替代浏览器 `prompt`。
- 显示证据、规则、任务和操作历史。
- 支持接受、拒绝、隔离、修正和受控重拉。
- 支持导出筛选结果 CSV。

### M4 资产浏览（阶段 D）

第一批：

- 默认只显示已接入数据，待接入统一折叠。
- 十字光标与日期快捷区间。
- 原生 SVG/CSS 行业/概念热力，不增加图表依赖。
- 资金流 VTable 迷你水平条。
- 新闻公告卡片流。
- 不可用分区展示失败原因和 M2 修复入口。
- 市场全景使用摘要＋分区标签。

推迟：多资产叠加、概念点时成分、指数历史成分、全球指数。

### M5 快照管理

- 并列显示当前默认版本和最新发布版本。
- 最近 5 个关键版本时间轴。
- 完整历史版本 VTable。
- 质量报告覆盖入口。
- 设为默认二次确认，不提供删除。

## 11. 计划接口变更

阶段 B 目标接口，最终参数在实现前复核。

数据源：

```text
GET  /api/data-center/sources
GET  /api/data-center/sources/{source_id}
PUT  /api/data-center/sources/{source_id}
POST /api/data-center/sources/{source_id}/test
```

不提供任意来源创建接口；白名单源通过代码注册和单独评审进入。

数据集目录：

```text
GET /api/data-center/datasets
```

路由继续沿用并扩展 `/api/data-center/routes`，增加 `source_id`、`fallback_policy` 和路由快照。

同步继续沿用现有接口，计划增加：

```text
GET /api/data-center/sync/tasks/{task_id}
GET /api/data-center/sync/tasks/{task_id}/items
```

质量计划增加：

```text
GET  /api/data-center/quality/issues/{issue_id}
GET  /api/data-center/quality/issues/{issue_id}/history
POST /api/data-center/quality/issues/{issue_id}/refetch
GET  /api/data-center/quality/issues/export
```

## 12. 计划数据表变更

阶段 B 只做增量 schema，禁止重建 17GB 规范库。

计划新增：

- `data_source_definitions`
- `data_source_capabilities`
- `data_dataset_catalog`
- `data_route_snapshots`

计划扩展：

- `data_source_routes`：`source_id`、`fallback_policy`
- `data_quality_issues`：`source_task_id`、`field_name`
- `data_quality_dispositions`：`related_task_id`、`related_issue_id`

迁移约束：

- 只使用 `CREATE TABLE IF NOT EXISTS` 或可回退的 `ALTER TABLE ADD COLUMN`。
- 不删除、不改名现有列。
- 不重写现有行情数据。
- 迁移前备份控制表 schema 与行数。
- 迁移后验证旧 API 和旧任务仍可读取。

## 13. 阶段 B 实施批次

### B1 数据集目录与数据源管理

七层目录 API、受控数据源注册表、M1 两子视图、路由能力与探测。

### B2 同步执行器 UX

动态表单、强制预览、分片选择、任务详情、轮询恢复、停止自动创建每日任务。

### B3 质量联动

来源任务筛选、正式处置详情、历史、受控重拉、CSV导出。

### B4 M0 与 M5 版本语义

研究就绪、默认/最新发布双版本、最近版本时间轴、缺口预览入口。

M4 可视化增强归入阶段 D，不与 B1—B4 混改。

## 14. 阶段 B 验收门禁

功能：

- M1 能区分数据源与路由，未验证来源不能启用。
- M2 无关字段按数据集隐藏，未预览不能创建任务。
- 页面关闭后任务继续，重新进入恢复监控。
- M2 可按任务跳转 M3。
- M3 所有处置强制原因，原始观察不被修正覆盖。
- M0 区分默认版本、最新发布和最新观察。
- M5 切换默认不影响历史 Run。

安全与数据：

- 无密钥落盘；测试连接写入数为 0。
- 无任意 URL/Python 执行。
- 全量重建继续阻断。
- 无历史版本删除和 17GB 规范库重建。

UX与回归：

- 所有适用表格使用 VisActor VTable。
- 亮暗主题语义一致，741px 窄屏无页面级横向溢出。
- 加载、空、失败、部分失败和停止状态可区分。
- 技术证据默认折叠。
- 通过阶段86、M4、VTable、正式API/HTTP、调度器恢复/停止/重试验收。

## 15. 阻断与升级条件

出现以下情况必须停止阶段 B 并重新人工确认：

- 需要新增依赖或修改锁文件。
- 需要 Redis、Celery、WebSocket 或前端框架。
- 需要删除、移动或重命名文件。
- 需要重建或大规模迁移规范行情库。
- 需要更改异常观察的入库语义。
- 需要多数据集任务原子发布。
- 需要开放任意自定义数据源。
- 数据来源、授权或字段口径无法确认。

## 16. 阶段 A 完成判断

本文完成并通过文档一致性检查后，阶段 A 视为完成。阶段 B 不自动开始，必须由用户再次批准。

## 17. 后续实施状态

- `已完成`：用户批准后，阶段 B1—B4 已于 2026-07-30 按本冻结契约实施。
- `已验证`：专项代码、API、调度器、M4/VTable 回归及全新浏览器验收通过。
- `已披露`：全量正式验证仍被当前 raw 数据质量门禁阻断，未表述为全量通过。
- `已完成`：阶段 C 质量闭环经再次批准后完成专项实现与验收。
- `待确认`：阶段 D 不自动开始，须再次取得人工批准。
- 实施证据：`docs/architecture/data-center-upgrade-stage-b-implementation.md`、`docs/architecture/data-center-upgrade-stage-c-implementation.md`。