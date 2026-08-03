# Pattern：正式发布范围与未发布观察分层展示

- `memory_id`: `mem-staging-sleepercloudquant-pattern-published-observed-isolation-001`
- `category`: `Pattern`
- `source`: `SleeperCloudQuant 阶段 78.3 全市场上下文回填`
- `timestamp`: `2026-07-27T21:45:00+08:00`
- `scope`: `项目专属；适用于增量行情、数据目录和质量概览`
- `validation_status`: `validated_once`
- `confirmation_count`: `0`

## 压缩结论

增量写入可能先于质量验证和版本发布。面向回测的“当前数据”必须读取不可变正式版本成员；数据库中更晚的原始行只能作为未发布观察单独披露，不能静默扩大正式数据范围。

## 适用启发

- 回测只绑定 `published` 版本。
- 概览同时返回正式截止日、观察到的最大日期和是否存在未发布观察。
- 未发布观察不参与正式覆盖率和质量结论。
- 恢复任务完成并通过质量门禁后，再以原子事务切换正式版本。

## 证据

阶段 78.3 正式版本截止 2026-07-24；2026-07-27 增量任务处于恢复队列且存在局部原始观察。概览正确保持正式截止日并显式标记未发布观察，完整正式验证通过。
