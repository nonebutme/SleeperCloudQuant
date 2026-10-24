# 拂经 v2 V7 P0 点时股票池与 OOS 门禁候选验收

## 已验证项

- 新增统一 fail-closed preflight 调用面，聚合字段契约、研究窗口、共同覆盖、点时股票池、因果负向检查和封存 OOS 输入一致性。
- 点时股票池按 `valid_from/valid_to` 选择历史有效事实。先以代码前缀执行科创板、北交所和沪深 B 股结构排除；结构排除项要求 `listing_status/available_at`，剩余候选还必须具备明确 `risk_warning`。
- 风险警示值缺失或含糊、事实尚未可见、同一证券有效区间重叠时，股票池整体失败关闭。
- 策略口径真实审计覆盖 2015-01-05 至 2026-08-10：母池 5,802 只、结构排除 1,188 只、风险事实必需 4,614 只；10,401,779 个必需证券交易日缺失 0、重叠 0、上市边界缺失 0。
- 封存清单冻结策略源码哈希、参数、精确数据版本、质量报告、因子制品、股票池快照、开发/OOS 窗口、主指标和决策阈值。
- 冻结后任一输入变化时，OOS 被判为 `oos_invalidated`。
- 生成首次查看记录后，该窗口永久标记为不再“未见样本”。
- 以下验证通过：
  - `python scripts/smoke_test_fujing_v7_preflight_service.py`
  - `python scripts/smoke_test_fujing_v7_universe_oos_gates.py`
  - `python scripts/smoke_test_fujing_v7_research_gates.py`
  - 相关新增文件 `py_compile`。

## 未验证项

- preflight 已接入策略保存、resolver、单标的、独立账户和共享组合任务入口。
- 当前证券上市生命周期及行情对应逐日交易状态已同步至 2026-08-10；策略实际需要的历史风险状态已通过全量审计。北交所风险状态和历史名称不再是 V7 纳入判断依赖。
- 封存清单和首次查看事件已进入追加式 SQLite 服务；尚未接入 Web 用户身份审计。
- 尚未建立精确全 A 股每日 universe snapshot 和内容哈希。
- 尚未确定振幅比例、研究窗口与 OOS 判定阈值的业务数值。

## 阻塞原因

- Windows sandbox 与 `apply_patch` 已恢复，正式服务和统一 runner 已完成接线。
- 当前数据事实已满足策略作用域覆盖；剩余阻塞为业务口径人工确认、生成新的精确正式数据版本，以及冻结研究/OOS阈值。

## 潜在风险

- 严格 `DATASET_CONTRACTS` 策略已受正式门禁保护；不声明严格契约的旧策略仍按 legacy 兼容路径执行。
- 早期未采用草稿 `app/services/point_in_time_universe_gate.py` 已在用户明确授权后删除；正式实现为 `governed_point_in_time_universe.py`。
- 因果门禁是样本上的负向测试，不等于形式化证明。
- OOS 封存若没有持久化和访问审计，仍可能被流程外查看。

## 发布判断

- `可继续迭代`
- P0 机制已形成统一调用面、接入正式主链并通过完整统一验证；策略作用域数据审计已通过，但正式发布仍须人工确认“结构排除先于风险字段”的业务口径，并冻结研究阈值。
