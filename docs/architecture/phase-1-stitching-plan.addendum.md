# 第一阶段拼接规划修订附注

## 一、文档定位

- `已确认` 本附注用于补充 `phase-1-stitching-plan.md` 的一致性修正结论。
- `已确认` 当前由于已有文件原位更新受本地写入助手影响，先以附注形式完成回填替代。

## 二、修订事项

### 2.1 `Tick` 的第一阶段角色

- 原文中 `data-platform` 前置依赖提到 `Stock / Bar / Tick` 基础语义确认。
- `已确认` 现统一修订为：
  - 第一阶段 `data-platform` 的必备基础语义是 `Stock / Bar`
  - `Tick` 仅保留语义预留，不作为第一阶段数据平台必备读取能力

### 2.2 后续文档顺序补充

- `已确认` 第一阶段后续文档顺序应补充：
  - `docs/architecture/reporting-minimum-spec.md`

## 三、适用方式

- 在阅读 `phase-1-stitching-plan.md` 时，应以本附注作为优先修正解释。
- 待本地写入助手恢复后，再将本附注内容回填到原文。

