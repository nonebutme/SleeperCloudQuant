# 阶段 66｜双模式回测任务中心

## 目标

在阶段 60-63 已完成的策略版本、独立账户批量回测、投资组合回测回测和双模式专业报告之上，提供统一任务目录。统一目录仅负责检索、状态查看和操作入口，不改变两种回测的资金、成交和统计语义。

## API

- GET /api/backtest/mode-tasks
- 查询字段：mode、status、strategy_id、search、limit
- 模式值：independent-screening、shared-portfolio
- 统一字段：任务标识、模式、状态、策略版本绑定、日期窗口、复权方式、股票池数量、进度、Run ID、详情/运行/报告链接
- 最大返回 200 条，按更新时间倒序排列

## Web 任务中心

策略回测页新增“双模式回测任务中心”，支持：

- 按模式、状态、策略 ID 和关键词筛选
- 汇总任务总数、模式分布、运行中、已完成和异常数量
- 选择任务并同步到原有模式详情区
- 直接启动或恢复任务
- 自动带入模式与任务 ID 并跳转专业报告

原有“全范围独立账户批量回测”和“投资组合回测”区域继续保留，用于创建任务和查看模式专属详情。

## 语义边界

- 独立账户批量回测仍为每只股票独立虚拟资金，仅实际建仓样本进入汇总。
- 投资组合回测仍为单一资金账户、多股持仓、统一现金和仓位约束。
- 任务中心不合并两类绩效指标，不重算回测，不写行情或分类数据。
- 报告入口继续调用阶段 63 的双模式专业报告 API。

## 验证

- node --check web/app.js
- python -m py_compile app/schemas/backtest.py app/api/backtest.py
- python scripts/smoke_test_backtest_mode_task_directory.py
- python scripts/smoke_test_backtest_mode_reports.py
- python scripts/run_formal_verifications.py

以上验证全部通过。