# 一致性修正决议

## 一、文档定位

- `已确认` 本文档用于记录本轮跨文档一致性检查后的修正结论。
- `已确认` 当前由于已有文件原位更新受到本地写入助手影响，先以本决议文档固化统一口径。
- `待确认` 后续在写入助手恢复后，再将本决议回填到对应原文档。

## 二、本轮修正结论

### 2.1 `Tick` 的第一阶段角色

- `已确认` `Tick` 在第一阶段只保留语义预留，不作为 `data-platform` 首批必备读取能力。
- `已确认` 第一阶段 `data-platform` 的必备读取主线仍为：
  - `Stock`
  - `Bar`
  - `交易日历`

影响文档：

- `docs/architecture/phase-1-stitching-plan.md`
- `docs/architecture/data-platform-minimum-spec.md`

### 2.2 `reporting` 最小规格补齐

- `已确认` 第一阶段 `reporting` 现在已有独立最小规格文档：
  - `docs/architecture/reporting-minimum-spec.md`

影响文档：

- `docs/architecture/phase-1-stitching-plan.md`
- `docs/architecture/backtest-kernel-minimum-spec.md`
- `docs/architecture/config-center-minimum-spec.md`

### 2.3 模型配置与 `ai` 阶段边界

- `已确认` `config-center` 中的模型配置仅作为后续 `ai` 能力预留。
- `已确认` 模型配置的存在不代表 `ai` 模块进入第一阶段实现范围。
- `已确认` 若第一阶段只做回测闭环，可暂不落地模型配置实现。

影响文档：

- `docs/architecture/phase-1-stitching-plan.md`
- `docs/architecture/config-center-minimum-spec.md`

## 三、后续回填建议

1. 在 `phase-1-stitching-plan.md` 中把 `Tick` 从第一阶段 `data-platform` 前置依赖降为语义预留。
2. 在 `phase-1-stitching-plan.md` 的后续文档顺序中加入 `reporting-minimum-spec.md`。
3. 在 `config-center-minimum-spec.md` 中把模型配置明确标注为“预留，不构成第一阶段阻塞项”。

## 四、发布判断

### 已验证项

- 本轮 3 个优先修正点已经形成统一口径

### 未验证项

- 原文档尚未完成原位回填

### 阻塞原因

- 本地写入助手当前对已有文件更新不稳定

### 发布判断

- `已确认` 本文档可作为当前阶段的统一修正依据
- `待确认` 待写入助手恢复后，应补做原文档回填

