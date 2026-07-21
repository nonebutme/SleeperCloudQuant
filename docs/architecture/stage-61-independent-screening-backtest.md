# 阶段 61：独立选股全范围并发回测

## 已确认业务语义

- 一个策略版本对冻结股票池中的每只股票独立执行。
- 每只股票使用相同但彼此独立的初始资金，不共享现金或持仓。
- `建仓` 定义为至少产生一笔数量大于零的有效买入成交。
- 收益、风险和交易绩效只统计建仓标的。
- 总股票数、已处理数、建仓数、未建仓数、失败数和剩余数必须完整披露。
- 未建仓和失败标的不得静默删除，也不得进入建仓绩效分母。

## 数据和策略快照

- 股票池来自阶段 59 的 `canonical_a_share_sqlite` 当前上市目录。
- 支持全部 A 股、SSE、SZSE、BSE 和显式股票代码列表。
- 创建任务时冻结股票代码、RQAlpha 代码、名称、市场和当前上市状态。
- 支持 `raw`、`qfq`、`hfq`；逐股数据不足时记录失败原因，不伪造行情。
- 任务绑定策略 ID、不可变版本、源码 SHA-256 和 `target-weights-v1` 契约。
- 回测行情入口已从旧数据库 fallback 切换为阶段 59 规范库；规范库不可用时才保留旧 fallback。

## 执行模型

- Web 创建任务后立即返回，后台线程负责完整任务生命周期。
- 一个任务使用受控线程池并发调度单股 run，并发数限制为 1 至 16。
- 每个单股 run 的策略源码仍在独立 Python 子进程中执行。
- 每只股票可配置 0 至 3 次重试。
- 单股结果继续写入正式回测结果库，run ID 为 `{task_id}-{symbol}`。
- 任务服务重启时把未完成的 `running` 状态转为 `interrupted`，允许再次启动恢复。

## 持久化

- 任务和逐股状态写入 `var/runtime/independent_screening.sqlite3`。
- 任务记录策略快照、日期范围、复权模式、基准、单股资金、并发数、重试数和股票池来源。
- 逐股记录状态、是否建仓、尝试次数、run ID、指标、错误和完成时间。
- 运行结果 SQLite 的 busy timeout 提升到 30 秒，以适应并发写入。

## 汇总口径

- `statistics_scope=entered_symbols_only`。
- 汇总平均总收益、中位总收益、正收益比例和平均年化收益。
- `top_entered` 最多展示前 20 个建仓标的。
- 完整建仓结果通过分页接口查询，页面默认展示前 100 条。
- 任一股票最终失败时任务状态为 `partial_failed`；全部失败时为 `failed`。

## API

- `GET /api/backtest/independent-screening-tasks`
- `POST /api/backtest/independent-screening-tasks`
- `GET /api/backtest/independent-screening-tasks/{task_id}`
- `POST /api/backtest/independent-screening-tasks/{task_id}/run`
- `GET /api/backtest/independent-screening-tasks/{task_id}/items`

## 阶段边界

- 本阶段不是共享资金池组合回测。
- 本阶段不把各股票收益简单拼成一个组合净值。
- 共享现金、多股持仓、组合调仓、A 股 T+1 和组合风险归因进入阶段 62。
