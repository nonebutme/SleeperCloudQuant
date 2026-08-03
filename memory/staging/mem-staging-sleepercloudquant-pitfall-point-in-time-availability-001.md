# Pitfall：时间点版本必须按事实可知时间裁剪

- `memory_id`: `mem-staging-sleepercloudquant-pitfall-point-in-time-availability-001`
- `category`: `Pitfall`
- `source`: `SleeperCloudQuant 阶段 78.3 全市场上下文回填`
- `timestamp`: `2026-07-27T21:45:00+08:00`
- `scope`: `项目专属；适用于公司行动、生命周期等时间点数据版本`
- `validation_status`: `validated_once`
- `confirmation_count`: `0`

## 压缩结论

构建时间点数据版本时，事实是否可进入版本必须由其“当时可知时间”决定，不能简单使用事件生效日。公司行动应以公告日裁剪；截止日前已公告的未来生效事件可以进入版本，截止日后才公告的历史生效事件不能进入。

## 适用启发

- 为每类事实明确 `available_at` 语义。
- 版本清单查询统一应用 `available_at <= as_of`。
- 质量测试同时覆盖“未来生效但已公告”和“历史生效但晚公告”。
- 发布清单与运行时查询使用同一时间点规则，避免前视偏差。

## 证据

阶段 78.3 初始清单曾按除权日裁剪公司行动，修正为公告日后重新发布 `scq-20260724-06a16f4a9fb078d9`，质量报告通过且三类真实回测完成。
