# 调度器应先刷新参考事实再确定增量目标

- `memory_id`: `mem-staging-sleepercloudquant-pattern-scheduler-reference-first-atomic-release-001`
- `type`: `Pattern`
- `scope`: `SleeperCloudQuant`
- `source`: `stage-78.2 incremental scheduler`
- `observed_at`: `2026-07-27`
- `validation_status`: `validated_once`
- `confirmation_count`: `1`

## 压缩结论

市场数据调度器不能仅依赖本地旧交易日历决定同步目标。每次盘后增量应先刷新目录、交易日历和正式基准，再确定目标交易日；参考事实未就绪时不得启动大规模价格任务或发布新版本。

## 适用规则

- 调度顺序采用“目录 → 交易日历 → 目标交易日 → 正式基准 → 价格任务 → 质量门禁 → 原子发布”。
- 正式基准未覆盖目标交易日时返回 `data_not_ready`，保留旧 `published` 版本。
- 调度任务和工作项必须持久化，启动恢复只重置中断状态，不直接绕过限频访问外部数据源。
- “当天已调度”不能简单等同于“任务已完成”；必须检查原任务状态并继续未执行的队列。
- 新版本清单必须重算已刷新的参考数据范围和摘要，不能沿用旧版本元数据。

## 证据

阶段 78.2 初版若直接使用停在上一交易日的本地日历，会持续生成无工作任务。加入参考事实预刷新、基准就绪门禁和版本成员重算后，确定性调度测试与完整统一验证均通过。
