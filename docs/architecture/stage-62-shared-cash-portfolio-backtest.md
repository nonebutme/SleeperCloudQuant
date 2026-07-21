# 阶段 62：共享资金池组合回测

## 已确认目标

- 阶段 61 的独立选股模式保持“每股独立资金、只汇总建仓标的”语义。
- 阶段 62 新增真实组合模式：一个初始资金池、统一交易日、多股共享现金和持仓上限，只生成一条组合净值曲线。
- 两种模式复用阶段 59 规范 A 股库和阶段 60 不可变策略版本，但不互相拼接收益结果。

## 执行语义

- 创建任务时冻结当前上市 A 股范围、策略版本、源码 SHA-256、日期、复权和费用参数。
- 每只股票先在隔离子进程中执行 `target-weights-v1`，再按统一交易日进入共享账户撮合。
- 每日先卖后买，100 股整手，现金不得透支；当日买入数量下一交易日才可卖出。
- 缺少当日行情视为停牌：不交易，并用最近收盘价估值。
- 涨跌停采用 ST 5%、主板 10%、创业板/科创板 20%、北交所 30% 的近似判定。
- 信号按强度排序并受 `max_positions` 限制，入选信号按 `portfolio_exposure` 归一化分配组合目标权重。

## 接口与持久化

- `GET/POST /api/backtest/shared-portfolio-tasks`
- `GET /api/backtest/shared-portfolio-tasks/{task_id}`
- `POST /api/backtest/shared-portfolio-tasks/{task_id}/run`
- 任务状态存储于 `var/runtime/shared_portfolio.sqlite3`，运行中断后标记为 `interrupted`，可再次启动。
- 组合运行写入现有 `backtest_runs`、metrics、trades、positions、accounts 和 yearly_returns，报告中心可按标准 run_id 直接读取。

## 已知边界

- 当前按日线收盘价加滑点撮合，不模拟盘中成交顺序或订单簿深度。
- 涨跌停判定属于代码和名称驱动的工程近似，不替代逐证券历史交易规则库。
- 复权由规范库 raw/qfq/hfq 数据决定；除现金分红在复权数据中的体现外，不单独模拟公司行动。
- 全市场股票池可冻结，但本阶段没有自动启动 5,528 只股票的长周期耗时运行。

## 验证结论

- 专用 smoke 验证共享现金不为负、整手成交、持仓上限、卖出路径和标准结果落库。
- 完整 `scripts/run_formal_verifications.py` 全部通过。
- 真实 HTTP 小样本使用 `000001`、`600000`，2020-01-01 至 2020-03-31，共产生 58 个组合账户点和 95 笔成交。
- 真实 run `stage62-http-real-shared-portfolio` 已被标准报告面板读取，状态为 `completed`，最终持仓数为 2。
