# 阶段 87.0：独立因子研究治理冻结

## 1. 状态与范围

- 状态：已批准并冻结。
- 批准日期：2026-08-12。
- 执行顺序：87.0 治理就绪 → 87.1 P0 闭环 → 87.2 指数池与增强分析。
- 产品边界：本模块是独立因子研究，不把策略持仓暴露冒充因子值，不承诺实盘交易，不引入付费数据源。
- 兼容边界：历史 /api/factors/* 保留为兼容只读接口；正式能力只进入 /api/factor-research/*。
- 技术边界：沿用 Python 标准库、原生 HTML/CSS/JS、SQLite、Quant UI Token 与 AppVTable，不引入新依赖。

## 2. 数据与版本政策

### 2.1 数据版本

1. 新研究只允许绑定状态为 published 的最新合格版本。
2. superseded 版本只允许在显式给出 data_version_id 时用于历史复现。
3. 不把 data_center_settings.default_data_version_id 当作新研究的隐式真相。
4. 有效区间取所有必需数据成员覆盖区间的交集；响应同时返回 requested_range 与 effective_range。
5. 任务创建时冻结 data_version_id、quality_report_id、成员清单、内容哈希、股票池快照和研究配置哈希。
6. 缺失版本、覆盖不足或质量未通过时，预检返回 unavailable；不得切换到演示库、外部实时请求或另一版本。

### 2.2 股票池

- 87.1 P0：全 A 股点时可用池。成员必须来自本地证券主数据，并按上市状态、交易状态、价格覆盖和请求日期过滤。
- 87.2：沪深 300、中证 500、中证 800、中证 1000、中证全指。成员只允许来自本地有效区间事实。
- 指数成分事实缺失时必须返回 index_component_facts_unavailable，不得调用 FakeMarketDataRepository 的两只演示成员。
- 股票池快照是任务证据的一部分，至少包含 pool_type、pool_code、as_of_date、symbols、source、source_version 和 content_hash。

### 2.3 收益与可交易性

- 因子日 t 使用 t 日收盘后可获得的字段。
- 未来收益为 t 后第 h 个有效交易日的复权收盘价 / t 日复权收盘价 - 1。
- P0 默认 h=5，支持 1、5、10、20。
- 停牌日和不可交易记录不生成未来收益；覆盖率分母与剔除原因必须披露。
- 87.1 只报告研究毛收益；87.2 才提供显式佣金、印花税、滑点参数下的执行估算，且与研究毛收益并列展示。

## 3. P0 因子定义

所有 P0 因子均为版本 v1，输入是本地 a_share_daily，默认 raw 计算因子、qfq 计算未来收益。计算结果方向由 direction 字段决定，不改变原始因子值。

| factor_id | 中文名 | 公式 | 最小历史 | direction |
| --- | --- | --- | ---: | --- |
| close_to_close_return_1d | 1 日收益 | close_t / close_t-1 - 1 | 2 | positive |
| momentum_20d | 20 日动量 | close_t / close_t-20 - 1 | 21 | positive |
| momentum_60d | 60 日动量 | close_t / close_t-60 - 1 | 61 | positive |
| volatility_20d | 20 日波动率 | 最近 20 个 1 日收益的总体标准差 | 21 | negative |
| close_to_ma20_bias | MA20 乖离 | close_t / mean(close_t...close_t-19) - 1 | 20 | positive |
| amount_strength_20d | 20 日成交额强度 | amount_t / mean(amount_t...amount_t-19) - 1 | 20 | positive |

缺失或分母为零时不产生值。定义元数据必须包含公式、输入字段、版本、最小历史、默认方向、适用阶段和数据集绑定。

## 4. 横截面预处理

固定顺序：

1. 移除非有限值并记录原因。
2. 双侧 MAD 去极值，默认阈值 3；MAD 为零时保留原值。
3. 若启用行业中性化，按当日点时一级行业对因子值做组内去均值；行业缺失样本单列并披露。
4. Z-score 标准化；标准差为零时该截面标记 unavailable。
5. 按方向对齐，仅用于方向一致指标和分组排序。

每个步骤必须记录 before_count、after_count、excluded_count、parameters 和 content_hash。

## 5. 指标合同

### 5.1 覆盖与分布

- factor_coverage = 有限因子值数量 / 当日股票池成员数。
- outcome_coverage = 同时具有因子值与未来收益的数量 / 有限因子值数量。
- 分布至少含 count、mean、std、min、p01、p05、p25、median、p75、p95、p99、max。
- 所有分母为零的指标返回 null，并附 unavailable_reason，不返回 0 伪装有效结果。

### 5.2 IC 与显著性

- IC：当日 Pearson 相关。
- Rank IC：当日 Spearman 相关，平均秩处理并列值。
- 方向一致 Rank IC = raw_rank_ic × direction_sign。
- ICIR = 日 IC 均值 / 日 IC 总体标准差。
- t 值 = mean(IC) / (sample_std(IC) / sqrt(n))；n<2 或样本标准差为零时不可用。
- 正 Rank IC 比率基于方向一致 Rank IC。
- 滚动窗口默认 22 个有效截面，最少 10 个。
- 衰减按 horizon=1、5、10、20 分别计算，不以自然日替代交易日。

### 5.3 分组与换手

- 默认 5 组，使用稳定秩和等频分桶；样本不足 5 组时返回不可用。
- 分组收益为各组未来收益等权平均。
- Top-Bottom 毛收益为方向对齐后的最高组减最低组。
- 换手率 = 1 - |本期组内成员 ∩ 上期组内成员| / max(1, 上期组内成员数)。
- 净值从 1.0 起，以每个调仓截面的分组收益连乘。
- 最大回撤使用净值历史高点到当前值的最小比例变化。

### 5.4 87.2 增强项

- 行业 IC：按点时一级行业分别计算 Rank IC，并返回样本量和覆盖率。
- 信号持续性：相邻有效截面因子秩的 Spearman 相关。
- 池间比较：同一 factor_version、data_version_id、日期、预处理与收益口径下比较。
- 执行估算：换手率 × 单边成本近似；必须同时返回 gross_return、estimated_cost、net_return_estimate 和 cost_assumption。
- 不把执行估算命名为回测收益或可实现收益。

## 6. 上下文与身份

研究上下文 canonical JSON 至少包含：

- factor_id、factor_version、parameters
- pool_type、pool_code、pool_as_of_policy、pool_snapshot_hash
- data_version_id、quality_report_id
- requested_range、effective_range
- factor_adjustment、outcome_adjustment、forward_horizons
- preprocessing、group_count、rebalance_frequency
- cost_assumption（87.2）

context_hash = SHA-256(canonical JSON)。任务、快照和报告都必须携带同一个 context_hash。重试沿用原上下文，不自动升级版本。

## 7. 状态机与失败语义

任务状态：

ready → running → completed
ready/running → stop_requested → stopped
running → partial_completed | failed
running → interrupted（进程重启恢复）
failed/partial_completed/interrupted/stopped → running（显式重试）

失败记录至少包含 stage、code、type、message、retryable、symbol/date scope。停止是协作式停止：完成当前最小批次后终止，不杀进程。

## 8. 正式接口冻结

- GET /api/factor-research/definitions
- GET /api/factor-research/definitions/{factor_id}
- GET /api/factor-research/dashboard
- POST /api/factor-research/preflight
- POST /api/factor-research/tasks
- GET /api/factor-research/tasks
- GET /api/factor-research/tasks/{task_id}
- POST /api/factor-research/tasks/{task_id}/start
- POST /api/factor-research/tasks/{task_id}/stop
- POST /api/factor-research/tasks/{task_id}/retry-failed
- GET /api/factor-research/reports/{report_id}
- GET /api/factor-research/reports/{report_id}/compare

所有响应至少含 status、capabilities、context_hash（适用时）、data_version、requested_range、effective_range、evidence 与 reasons。写接口不得隐式同步数据或切换默认版本。

## 9. 存储冻结

新建独立运行库 var/runtime/factor_research.sqlite3，不修改历史 factor_result_cache：

- factor_definitions：版本化元数据。
- factor_research_tasks：配置、上下文、状态、进度和错误摘要。
- factor_research_snapshots：股票池和预处理证据快照。
- factor_research_observations：因子值、标准化值、未来收益、行业和分组。
- factor_research_reports：不可变报告载荷和哈希。
- factor_index_component_intervals：87.2 本地点时指数成员事实。

业务大库保持只读。运行库初始化是幂等的；正式运行不得写入 tmp/formal_http_demo.sqlite3 的研究结果。

## 10. UI 冻结

- F0 因子看板：筛选、关键指标列、能力/版本提示、VTable。
- F1 因子详情与配置：元数据、预检、任务创建。
- F2 任务中心：状态、进度、停止、失败重试。
- F3 研究报告：覆盖、分布、IC、滚动/衰减、分组收益、换手；87.2 增加行业 IC、信号持续性、池间比较和执行估算。
- 使用现有 Quant UI Token；可表达为行列的数据全部通过 AppVTable 渲染；741px 宽度不得横向溢出。
