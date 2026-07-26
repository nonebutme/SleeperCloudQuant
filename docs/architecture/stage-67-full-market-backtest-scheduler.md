# 阶段 67｜全市场回测性能与资源调度

## 目标

移除 Web 默认股票上限造成的“小批次”使用障碍，降低数千股票任务的编排和状态写入开销，并提供可暂停、可恢复、可取消、可估时的独立账户批量回测任务执行能力。

## 调度升级

- 股票上限 0 表示冻结全部当前 A 股，不再默认限制为 20 或 100。
- 并发数 0 表示自动选择；手工并发范围扩展至 1-32。
- 调度器由一次提交全部 Future 改为 bounded_dynamic_batches。
- 自动批次为有效并发数的 4 倍；手工批次范围为 1-256。
- 每批结果使用单个 SQLite 批量事务落库。
- 每个批次前后检查 pause_requested 和 cancel_requested。
- 任务重启恢复 running、pause_requested、cancel_requested 状态。

## 任务控制

POST /api/backtest/independent-screening-tasks/{task_id}/control

支持动作：

- pause：当前批次结束后暂停，不再调度下一批。
- resume：继续 pending、failed 或 interrupted 股票。
- cancel：将剩余项标记 canceled，不进入建仓绩效统计。

## 遥测

任务 progress 新增：

- elapsed_seconds
- throughput_per_minute
- estimated_remaining_seconds
- canceled

任务 execution 新增：

- scheduler
- requested_workers
- effective_workers
- batch_size

Web 独立账户批量回测区和统一任务中心展示进度、吞吐率和预计剩余时间。

## 调度层合成基准

环境参数：8 个工作线程、32 项批次、无真实行情读取、无策略子进程计算。

| 项目数 | 创建耗时 | 执行耗时 | 调度吞吐 |
| ---: | ---: | ---: | ---: |
| 100 | 0.0098 秒 | 0.0815 秒 | 1226.89 项/秒 |
| 1000 | 0.0118 秒 | 0.6632 秒 | 1507.80 项/秒 |
| 5528 | 0.0353 秒 | 3.1683 秒 | 1744.78 项/秒 |

该基准只证明调度层无需固定 100 项限制，不代表真实全市场策略回测速度。真实耗时仍由行情读取、策略子进程和正式结果落库决定，阶段 69 将执行代表性策略的全市场业务验收。

## 验证

- 阶段 61 独立账户批量回测语义 smoke 通过。
- 阶段 66 统一任务目录 smoke 通过。
- 阶段 67 暂停、恢复、取消和有界批次 smoke 通过。
- Node 和 Python 静态检查通过。
- 完整正式验证全部通过。
- 8017 HTTP 创建 5 只任务并取消：canceled=5，percent=100。
- 页面暂停、取消和调度批次控件探测通过。

## 下一阶段

按用户确认顺序进入阶段 68B：策略回测界面用户友好化改造；之后依次为阶段 68A 使用说明、阶段 68 策略工作台业务验收。