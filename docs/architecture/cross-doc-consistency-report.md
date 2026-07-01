# 跨文档一致性检查报告

## 一、文档定位

- `已确认` 本文档是基于 `cross-doc-consistency-check-plan.md` 执行后的实际检查报告。
- `已确认` 本文档只汇总现有主干规划文档之间的一致性情况，不直接修正文档内容。

## 二、检查范围

本轮已检查以下 5 份主干文档：

- `docs/architecture/phase-1-stitching-plan.md`
- `docs/architecture/domain-boundary-spec.md`
- `docs/architecture/backtest-kernel-minimum-spec.md`
- `docs/architecture/data-platform-minimum-spec.md`
- `docs/architecture/config-center-minimum-spec.md`

## 三、总体结论

- `已确认` 当前未发现 `P1` 级严重冲突。
- `已确认` 主体架构方向保持一致：第一阶段仍以 `data-platform + backtest-kernel + config-center + reporting` 为主干。
- `已确认` 来源仓库角色总体一致：`SleeperCloudQuant-old` 为主承接，`TradingAgents-CN-main` 为结构与配置主参考，`rqalpha-master` 与 `vnpy-master` 为语义来源。
- `待处理` 当前存在 2 项 `P2` 问题和 1 项 `P3` 表述问题。

## 四、已验证一致项

### 4.1 模块主线一致

- 第一阶段核心模块在主规划文档中定义为 `data-platform + backtest-kernel + config-center + reporting`，[phase-1-stitching-plan.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\phase-1-stitching-plan.md:15)
- `backtest-kernel`、`data-platform`、`config-center` 三份最小规格文档都围绕这条主线展开，没有出现越级扩展到实现层的情况。

### 4.2 对象语义主来源一致

- `BacktestRequest / BacktestResult` 主参考保持为 `SleeperCloudQuant-old`，[domain-boundary-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\domain-boundary-spec.md:325) [domain-boundary-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\domain-boundary-spec.md:362)
- `Order / Position / Account` 等交易与账户语义以 `rqalpha-master`、`vnpy-master` 为主补关系，前后表述一致，[domain-boundary-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\domain-boundary-spec.md:147) [backtest-kernel-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\backtest-kernel-minimum-spec.md:324)

### 4.3 依赖方向总体一致

- `data-platform` 向 `backtest-kernel` 提供标准化行情输入，[data-platform-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\data-platform-minimum-spec.md:80)
- `backtest-kernel` 向 `reporting` 提供稳定结果输入，[backtest-kernel-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\backtest-kernel-minimum-spec.md:47)
- `config-center` 分别服务于 `data-platform`、`backtest-kernel`、`reporting`，没有出现反向侵入定义，[config-center-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\config-center-minimum-spec.md:248)

## 五、发现的冲突项

### [P2] `Tick` 在第一阶段中的角色表述不一致

涉及文档：

- [phase-1-stitching-plan.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\phase-1-stitching-plan.md:91)
- [data-platform-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\data-platform-minimum-spec.md:44)
- [data-platform-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\data-platform-minimum-spec.md:327)

问题描述：

- 第一阶段拼接规划把 `Stock / Bar / Tick` 基础语义确认列为 `data-platform` 的前置依赖。
- 但数据平台最小规格又明确首阶段只支持 `Stock / Bar / 交易日历`，并写明 `Tick` 仅保留语义预留。

影响范围：

- 会影响第一阶段数据平台的完成标准判断。
- 后续如果据此进入文件级映射，可能误把 `Tick` 数据能力纳入首批候选。

建议处理方式：

- 统一为其一：
  - 要么把 `Tick` 从第一阶段 `data-platform` 前置依赖中降为“语义预留”
  - 要么在数据平台最小规格中明确 `Tick` 也属于首阶段必备读取边界

### [P2] `reporting` 已成为多文档依赖，但仍缺少对应最小规格文档

涉及文档：

- [phase-1-stitching-plan.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\phase-1-stitching-plan.md:199)
- [backtest-kernel-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\backtest-kernel-minimum-spec.md:47)
- [backtest-kernel-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\backtest-kernel-minimum-spec.md:266)
- [config-center-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\config-center-minimum-spec.md:155)
- [config-center-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\config-center-minimum-spec.md:281)

问题描述：

- `reporting` 已被纳入第一阶段范围。
- `backtest-kernel` 已把它视为稳定下游。
- `config-center` 已开始为其定义模板配置边界。
- 但 5 份主干文档中还没有与 `backtest-kernel-minimum-spec`、`data-platform-minimum-spec` 同等级的 `reporting-minimum-spec`。

影响范围：

- 会导致回测结果输出边界、报告模板边界、历史记录边界只能停留在规划层表达。
- 后续进入文件级映射时，`reporting` 模块的目标范围容易漂移。

建议处理方式：

- 在进入第一批候选文件映射前，补一份 `docs/architecture/reporting-minimum-spec.md`
- 至少收敛：
  - 回测报告输入边界
  - 报告摘要对象边界
  - 历史记录与模板配置边界

## 六、待统一表述项

### [P3] `ai` 被排除在第一阶段范围外，但 `config-center` 仍纳入了模型配置

涉及文档：

- [phase-1-stitching-plan.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\phase-1-stitching-plan.md:21)
- [phase-1-stitching-plan.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\phase-1-stitching-plan.md:257)
- [config-center-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\config-center-minimum-spec.md:42)
- [config-center-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\config-center-minimum-spec.md:121)

问题描述：

- 第一阶段拼接规划明确 `ai` 当前不纳入范围。
- 但配置中心最小规格已经把模型配置列入第一阶段配置分类之一。

影响范围：

- 不会直接破坏当前规划，但会让后续读者误以为 `ai` 已经部分进入第一阶段实现边界。

建议处理方式：

- 在 `config-center-minimum-spec.md` 中把模型配置统一表述为：
  - `为后续 ai 预留，不构成第一阶段实现阻塞项`

## 七、待补齐边界项

### 7.1 `factor-lab` 虽不在第一阶段范围，但已出现在数据输出和领域对象关系中

涉及文档：

- [phase-1-stitching-plan.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\phase-1-stitching-plan.md:22)
- [data-platform-minimum-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\data-platform-minimum-spec.md:29)
- [domain-boundary-spec.md](D:\Dev-AI\Dev\projects\SleeperCloudQuant\docs\architecture\domain-boundary-spec.md:32)

判断：

- `非冲突`
- `待补齐边界`

说明：

- 当前表述整体合理，因为数据平台和领域对象需要为后续扩展预留边界。
- 但后续若继续收文档，最好补一句“仅作为后续扩展接口预留，不代表第一阶段实现纳入”。

## 八、建议修正优先级

1. 先处理 `Tick` 的首阶段角色定义不一致问题
2. 再补 `reporting-minimum-spec.md`，避免下游边界长期悬空
3. 最后统一 `config-center` 中模型配置的阶段表述

## 九、发布判断

### 已验证项

- 当前主干规划文档没有发现会直接阻断实现方向的 `P1` 级冲突
- 文档主线可继续用于下一阶段收敛

### 未验证项

- 若补齐 `reporting-minimum-spec.md` 后，是否还会暴露新的依赖冲突
- 若进入文件级映射，是否会引出新的对象粒度问题

### 阻塞原因

- `Tick` 的阶段角色尚未统一
- `reporting` 仍缺对应最小规格文档

### 潜在风险

- 若现在直接进入文件级候选映射，会把这两处边界不稳的问题带入下一阶段

### 发布判断

- `已确认` 可以先做小规模文档修正，再进入第一批候选文件映射清单
- `待确认` 当前不建议跳过修正直接进入文件级拼接规划

