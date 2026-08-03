# 治理事件稳定 ID 不应包含观察时间

- `memory_id`: `mem-staging-sleepercloudquant-pitfall-governance-event-id-observation-time-001`
- `type`: `Pitfall`
- `scope`: `SleeperCloudQuant`
- `source`: `stage-78.1 governance sample integration`
- `observed_at`: `2026-07-27`
- `validation_status`: `validated_once`
- `confirmation_count`: `1`

## 压缩结论

不可变业务事件的稳定 ID 必须来自业务自然身份，不应包含抓取时间、同步 Run 或观察批次等采集元数据；否则重复同步会把同一业务事实写成多个事件。

## 适用规则

- 生命周期事件可由证券、事件类型、生效区间和必要业务字段确定身份。
- 公司行动可由证券、行动类型、除权日、登记日、支付日等自然键确定身份。
- 观察时间、来源响应哈希和同步 Run 只进入证据与审计字段。
- 发布门禁应检查自然键重复组，而不只检查代理主键。
- 清理或去重事务必须显式提交，并在发布前重新执行重复键核验。

## 证据

阶段 78.1 首轮样本重试曾因 ID 含观察时间产生生命周期和公司行动重复事实；调整稳定 ID、提交去重事务并加入自然键硬门禁后，重复组均降为 0，质量报告通过。
