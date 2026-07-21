# 下一阶段真实开发计划

## 1. 当前基线

### 1.1 已确认

- `data_platform`、`backtest_kernel`、`reporting`、`config_center` 已收束到正式模块。
- 深层 `phase1_*` 副本、兼容入口、fake/demo 资产均已清退完成。
- `domain/`、`app/services/`、`app/api/`、`app/main.py` 已出现正式模块骨架。
- 当前统一验证入口为：`python scripts/run_formal_verifications.py`
- 当前仓内已存在：
  - `python scripts/smoke_test_formal_services.py`
  - `python scripts/smoke_test_formal_api.py`
  - `python scripts/smoke_test_formal_http_adapter.py`

### 1.2 已确认但仍然缺失

当前项目不再缺少 `domain` 或 `app` 的最小骨架，真正仍缺的主要是：

- 计划文档与当前实现现状之间的同步
- 阶段 7 总览文档与最新执行批次之间的一致性同步
- 围绕最小本地量化服务闭环的后续小范围代码收束或阶段收尾判断

### 1.3 基于当前上下文推断

按照阶段 7 的最新定义，下一轮真实开发不应该：

1. 回到阶段 5 继续扩 `reporting` 字段或 route
2. 直接进入阶段 6 报告快照存储实现
3. 直接切到前端页面或 AI 分析流程

更合理的主线，应是把现有模块收束为：

1. 可稳定调用的服务层闭环
2. 可稳定访问的最小 API 闭环
3. 可被统一回归的阶段 7 验证闭环

## 2. 下一阶段目标

把当前“已有正式模块骨架”的项目，推进为“最小本地量化服务闭环”。

目标不是立刻做完整产品，而是先形成：

- 数据查询服务入口
- 因子查询与研究服务入口
- 单次回测与批量回测服务入口
- 报告读取服务入口
- 最小 API 访问入口
- 与现状一致的统一验证入口

## 3. 推荐推进顺序

### 3.1 第一批：校准计划与验证基线

目标：让后续开发依据不再滞后于仓库现状。

建议收束：

- `docs/architecture/next-real-development-plan.md`
- `docs/verification/verification-baseline.md`
- 与阶段 7 相关的批次记录

本批原则：

- 先修正文档滞后
- 先固定验证入口
- 不顺手扩大功能面

### 3.2 第二批：收束服务层职责

目标：让 `app/services` 真正成为阶段 7 的稳定编排入口。

建议重点复核：

- `app/services/market_data_service.py`
- `app/services/factor_research_service.py`
- `app/services/backtest_service.py`
- `app/services/persistent_backtest_service.py`
- `app/services/batch_research_service.py`
- `app/services/reporting_service.py`

建议验证项：

- 数据读取链可返回最小稳定结果
- 因子研究链可在本地 fake/runtime 条件下稳定回归
- 回测链可完成单次与批量执行
- 报告读取链继续满足阶段 5 冻结基线

本批原则：

- 只收束职责边界
- 不重写核心逻辑
- 不提前引入异步任务或新依赖

### 3.3 第三批：收束最小 API 与 HTTP 访问面

目标：让 `app/api`、`app/main.py` 与 HTTP adapter 成为稳定入口，而不是仅有骨架。

建议重点复核：

- `app/api/market.py`
- `app/api/factor.py`
- `app/api/backtest.py`
- `app/api/reporting.py`
- `app/main.py`
- `app/runtime/http_adapter.py`

建议验证项：

- 查询路由可返回最小正确响应
- 写入型最小接口在 fake/runtime 条件下可回归
- 缺失资源与非法参数语义保持稳定

本批原则：

- 只做阶段 7 闭环所需接口
- 不扩前端专用契约
- 不新增 AI 接口

### 3.4 第四批：收束统一验证入口（已完成）

目标：把阶段 7 smoke 脚本纳入统一入口，并将其状态从计划项切换为已完成基线。

已完成收束：

- `scripts/run_formal_verifications.py`

当前状态：

- 统一入口已串入 `smoke_test_formal_services.py`
- 统一入口已串入 `smoke_test_formal_api.py`
- 统一入口已串入 `smoke_test_formal_http_adapter.py`
- 当前统一入口已可直接回归阶段 7 七项最小验证组合

建议阶段 7 最小验证组合为：

- `python scripts/verify_formal_fake_runtime.py`
- `python scripts/verify_formal_reporting.py`
- `python scripts/verify_formal_sqlite_cache.py`
- `python scripts/smoke_test_factor_lab.py`
- `python scripts/smoke_test_formal_services.py`
- `python scripts/smoke_test_formal_api.py`
- `python scripts/smoke_test_formal_http_adapter.py`
- `python scripts/run_formal_verifications.py`

## 4. 当前不建议立刻进入的方向

### 4.1 不建议立刻做

- 前端页面实现
- AI 分析流程接入
- 报告快照存储实现
- 多用户权限
- 异步任务系统
- 完整领域对象全集
- 真实 Ricequant / RQAlpha 运行时集成落地

### 4.2 原因

- 阶段 5 与阶段 6 已有明确止步边界。
- 阶段 7 的核心价值，不是继续扩能力面，而是把现有正式模块收束成稳定闭环。
- 若现在直接做前端、AI 或报告快照实现，会重新打散当前已经收口的边界。

## 5. 推荐的下一批实际执行范围

如果进入下一轮真实开发，建议优先在下面两类工作中二选一：

### 推荐批次 A：`stage7-doc-consistency-review`

包含：

- 复核 `stage-7-goal-and-boundaries.md`、`next-real-development-plan.md`、`stage-7-service-and-api-boundaries.md` 与 `Batch 69-75` 之间是否存在陈旧表述
- 仅修正已被后续批次覆盖的总览文档描述
- 不回写历史批次记录

### 推荐批次 B：`http-adapter-or-contracts-minor-cleanup`

包含：

- 检查 `app/runtime/http_adapter.py` 与相关契约定义中是否仍有重复参数装配或重复错误映射逻辑
- 仅做阶段 7 闭环内的小范围代码收束

当前更稳的顺序仍是先做 A，再决定是否进入 B，因为：

- 不改业务边界
- 不引入新依赖
- 能先把阶段 7 的总览入口与 Batch 75 后现状重新对齐

## 6. 发布判断

- `已确认`：Phase 1 回收与清退工作已闭环。
- `已确认`：阶段 5 `reporting` 继续保持冻结。
- `已确认`：阶段 6 继续保持“边界澄清完成、实现暂缓”。
- `已确认`：项目已进入阶段 7。
- `建议`：下一轮优先从“阶段 7 文档一致性复核”或“`http_adapter` 小范围代码收束”中择一推进，而不是直接改功能面。