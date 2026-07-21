# 阶段 58：A 股真实源库只读接入与质量基线

## 已确认范围

- 主参考源：SleeperCloudQuant-old/PyDB/StockMarket/stock_database/data/stockmarket.db
- 原数据库永久只读，不在旧库执行建表、更新、清洗或删除。
- 第一阶段数据范围：2015-01-05 至最近完整交易日，沪深北及历史退市 A 股，日线 raw/qfq/hfq。
- 阶段 2 策略回测保持冻结，直到用户明确确认 A 股数据验收通过。

## 已实现

- 新增 AShareSQLiteRepository，SQLite 连接强制 mode=ro 与 query_only。
- 新增总览、股票目录和日线分页 API：
  - GET /api/market/a-share/overview
  - GET /api/market/a-share/symbols
  - GET /api/market/a-share/daily
- Web 数据中心新增真实库总览、市场/代码/名称检索、复权选择、日期区间、分页日线、K 线和成交指标。
- Web Demo 支持 SCQ_WEB_PORT，避免覆盖既有 8010 进程。
- 新增 scripts/smoke_test_a_share_source_database.py 并纳入正式验证。

## 数据基线

- 当前股票：5,496。
- 历史行情代码：5,747。
- 不复权日线：10,716,500 行，2015-01-05 至 2026-03-31，重复 213 行。
- 前复权日线：10,055,269 行，2015-01-05 至 2025-09-19。
- 后复权日线：10,267,333 行，2015-01-05 至 2025-09-19，重复 149,137 行。
- 数据源代码确认使用 AKShare。

## 当前判断

- 已完成真实源库可见性和质量事实暴露。
- 当前数据状态为 needs_attention，不能判定为完整数据验收通过。
- 尚未完成规范化数据库迁移、去重持久化、AKShare 增量补齐和最近交易日对照。
- 当前 Python 环境未安装 akshare 与 pandas；进入阶段 59 前需要依赖安装授权。
