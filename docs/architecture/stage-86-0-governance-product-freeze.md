# 阶段 86.0：治理基线与产品冻结

## 1. 阶段定位

- `已确认`：本阶段只保护和核验现有候选基线，冻结数据中心与独立因子研究的产品、交互、接口和数据边界。
- `已确认`：不修改产品代码、数据库 schema、依赖、运行配置，不启动外部同步，不覆盖或回滚当前未提交成果。
- `已确认`：项目用于非商用、本地量化研究。
- `已确认`：用户已批准按顺序完成阶段 86；数据库只增迁移、数据中心公共接口和非商用免费数据源边界已按冻结稿执行。

## 2. 候选基线

- 当前分支：`agent/stage-76-10-github-sync`。
- 已提交基线停留在阶段 77；阶段 78—85 成果主要位于当前未提交工作树。
- 当前工作树作为候选基线保留，禁止覆盖、回滚或以旧提交替换。
- 候选基线只有在统一正式验证通过、治理文档对齐且人工确认后，才可进入正式提交或发布流程。

## 3. 数据中心产品冻结

数据中心采用一个内部工作台、六个视图：

1. `M0 总览指挥舱`
   - 展示正式发布版本、新鲜度、存储规模、资产规模、异常数量和近期同步审计。
   - 正式截止日与未发布观察最大日期必须分开展示。
2. `M1 源路由配置`
   - 按数据集配置 Provider、端点、限频、并发、退避和重试。
   - 测试连接只执行轻量读取，不写规范库。
3. `M2 同步执行器`
   - 支持增量补缺、分片预览、任务确认、实时进度、优雅停止和仅重试失败项。
   - 全量重建属于高风险操作，默认禁用；启用前需备份、影响预览和二次审批。
4. `M3 质量纠错工坊`
   - 展示质量规则、有限失败样本、隔离项和处置状态。
   - 人工修正不覆盖原始观察，使用修正覆盖层并保留操作者、时间、原因和前后值。
5. `M4 资产浏览`
   - 按数据集浏览已发布资产，支持表格、K 线和满足数据条件时的行业热力图。
   - 隔离数据和未发布观察不得进入默认浏览、因子或回测读取。
6. `M5 快照管理`
   - 发布不可变数据版本，查看成员、质量报告和来源证据。
   - “设为默认”只切换默认指针；历史 Run 继续绑定原版本，不重写历史结果。

## 4. 数据中心状态机冻结

### 同步任务

`draft -> previewed -> queued -> running -> completed/partial_failed/failed/stopped`

- `stopping` 表示停止接收新工作项、等待在途请求完成。
- 暂停和恢复不得跳过限频、重试、质量门禁或审计。

### 质量异常

`open -> quarantined -> accepted/rejected/corrected -> superseded`

- `warning` 不等于自动失败，是否阻断发布由规则严重度决定。
- `error` 或关键数据集失败必须阻断新版本发布。
- 修复后生成新质量报告；历史报告不可原地修改。

### 数据版本

`draft -> validating -> published/rejected -> superseded`

- 同时只能有一个默认 `published` 指针。
- `superseded` 版本仍可供历史 Run 读取。
- 数据库中较新的原始观察不自动扩大正式发布范围。

## 5. 金融数据质量规则修正

- 不要求复权因子单调；检查非空、正值、连续性、公司行动对账和计算口径。
- 不把缺少行情推断为停牌、退市或其他确定状态；未知保持 `unknown`。
- 财务事实使用公告日或首次可得时间控制可用性，不能仅按报告期回填历史。
- 当前行业或概念分类不能静默回填历史时点。
- 输入、插入、更新、未变化和拒绝数量必须守恒，不使用“写入行数不得少于接口行数”的错误规则。

## 6. 免费数据源策略冻结

### 首期原则

- 优先复用现有 AKShare 依赖和适配器，不新增数据依赖。
- 只用于非商用、本地研究；免费可访问不等于供应商授权或 SLA。
- 所有 Provider 必须保存来源网站、AKShare 接口名、抓取时间、请求范围、适配器版本、响应摘要和失败原因。
- 单一接口失效不得破坏旧的 `published` 版本。

### 首期候选路由

| 数据集 | 首选候选接口 | 主要上游 | 阶段边界 |
| --- | --- | --- | --- |
| A 股目录 | `stock_info_a_code_name` / 现有目录适配器 | 公开财经站点 | 继续沿用现有实现 |
| A 股日线 | `stock_zh_a_hist` | 东方财富 | 已有实现，保留限频与回退 |
| 交易日历 | `tool_trade_date_hist_sina` | 新浪 | 先刷新参考事实再确定目标日 |
| 指数日线 | `index_zh_a_hist` | 东方财富 | 沪深 300 为首期正式基准 |
| 指数成分 | `index_stock_cons_csindex` 或现有点时成分存储 | 中证指数公开数据 | 必须保存生效区间 |
| 公司行动 | `stock_fhps_em` / 现有公司行动适配器 | 东方财富 | 使用公告日控制可用性 |
| 行业分类 | `stock_board_industry_name_em`、`stock_board_industry_cons_em` | 东方财富 | 当前分类与历史分类分离 |
| 财务报表 | `stock_zcfz_em`、`stock_lrb_em`、`stock_xjll_em` | 东方财富 | 阶段 86 不接入；先冻结点时模型 |
| 全球指数 | `index_global_hist_em` | 东方财富 | P2，可选，不阻塞 A 股研究闭环 |

## 7. 独立因子研究边界冻结

### 业务对象

- 因子研究评估抽象因子值与未来收益的横截面关系。
- 策略暴露分析评估策略原始分数、目标权重或真实持仓暴露。
- 两者可复用统计引擎，但因子 ID、输入证据、报告标题和结论不得混用。

### 首期输入契约

- 因子定义：`factor_id`、名称、版本、参数、方向、所需数据集、实现摘要。
- 研究范围：点时股票池、开始/结束日期、调仓周期、未来收益周期。
- 数据绑定：明确的 `published data_version_id`、复权口径和股票池快照。
- 预处理：缺失处理、缩尾、标准化、行业中性化及处理顺序。
- 时间边界：`T` 时点因子值只能评价 `T+N` 收益。

### 首期分析能力

- 普通 IC、Rank IC、IC 均值/标准差、ICIR、显著性和正 IC 比例。
- IC 时间序列、滚动均值、1/5/10 期衰减和行业分布。
- Q1—Q5 分组收益、Top-Bottom、多空净值、最大回撤和分组换手率。
- 因子覆盖率、缺失率、分布和预处理前后对比。
- 因子加权收益、波动率和最大回撤。

### 首期因子范围

- P0：价格、收益、成交量、成交额、波动、动量和技术派生因子。
- P1：行业中性化和可获得的市值控制。
- P2：财务、风格风险和 Alpha 类因子；必须等待点时财务事实、来源覆盖和授权边界通过。
- 不开放任意 Python 执行；自定义因子先使用受控注册表，安全表达式另行审批。

## 8. 最小接口契约

### 数据中心

- `GET /api/data-center/overview`
- `GET/PUT /api/data-center/routes`
- `POST /api/data-center/routes/test`
- `POST /api/data-center/sync/preview`
- `POST /api/data-center/sync/tasks`
- `GET /api/data-center/sync/tasks`
- `POST /api/data-center/sync/tasks/{task_id}/stop`
- `POST /api/data-center/sync/tasks/{task_id}/retry-failed`
- `GET /api/data-center/quality/issues`
- `POST /api/data-center/quality/issues/{issue_id}/disposition`
- `GET /api/data-center/assets`
- `GET /api/data-center/versions`
- `POST /api/data-center/versions/publish`
- `POST /api/data-center/versions/{version_id}/set-default`

### 因子研究

- `GET /api/factor-research/definitions`
- `POST /api/factor-research/tasks`
- `GET /api/factor-research/tasks`
- `GET /api/factor-research/tasks/{task_id}`
- `GET /api/factor-research/tasks/{task_id}/report`

历史 `/api/market/*` 和 `/api/factors/*` 暂不删除；阶段 86.1 通过薄适配迁移，公共接口变更需再次审批。

## 9. 数据库增量候选

以下只冻结概念，不在阶段 86.0 建表：

- `data_source_routes`
- `data_quality_issues`
- `data_quality_dispositions`
- `data_correction_overlays`
- `factor_definitions`
- `factor_research_tasks`
- `factor_research_snapshots`
- `factor_research_reports`

优先复用现有同步任务、工作项、质量报告、数据版本和因子缓存表。新表采用只增不改迁移，迁移前备份，失败时保留旧读路径。

## 10. 下一审批门禁

进入阶段 86.1 前需人工确认：

1. 批准 M0—M5 信息架构和状态机。
2. 批准上述最小接口命名与历史接口兼容策略。
3. 批准质量异常、人工处置和修正覆盖层的增量数据模型。
4. 批准首期免费数据源路由与非商用研究边界。
5. 批准独立因子研究首期只做价格、量价、技术类因子，财务因子后置。

