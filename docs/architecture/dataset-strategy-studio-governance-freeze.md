# 数据集与策略工作室治理冻结

状态：P0 正式基线。

## 1. 正式模型

本阶段正式采用 `Dataset Product + Strategy Manifest` 双核心模型。数据中心现有 `data_dataset_catalog` 是数据集身份与运行状态的唯一事实源；策略工作室只消费其公开契约，不维护第二套目录。

正式术语：

- `DatasetProduct`：面向研究的稳定数据产品。
- `DatasetRelease`：不可变数据发布版本。
- `DatasetRequirement`：策略或因子对数据的显式需求。
- `StrategyManifest`：资产、数据、信号、组合、风控、执行、代码和验证清单。
- `RunInputBundle`：一次回测冻结后的全部输入。

## 2. 此前草案处置

- `domain/dataset/models.py`：保留为 M0 兼容契约；`DatasetSubscription` 不再用于新功能。
- `data_platform/dataset_registry.py`：保留为只读适配原型；其中静态字段表不是正式事实源。
- `factor_lab/dataset_bindings.py`：保留为两个内置因子的迁移绑定。
- `app/services/strategy_dataset_validation.py`：保留为旧策略迁移校验；源码字面量不是新工作室的主要持久化方式。
- 现有策略编辑页面继续作为备用入口，不删除、不覆盖。

上述文件不物理删除；新功能只依赖 P0 正式契约或显式兼容适配器。

## 3. 强制门禁

- 数据集目录不得复制为第二套可写事实源。
- 正式 Run 只能绑定 `published` 数据版本。
- 策略和因子不得静默读取未声明的数据。
- 历史分类必须按 point-in-time 有效区间读取。
- 缺失数据、版本或证据时返回 `unavailable + reason`。
- 样本外、幸存者偏差和未来信息检查必须进入验证状态。
- 三种回测模式的资金和统计语义保持独立。

## 4. 下一阶段

P1 只增加数据集目录的只读产品适配和查询，不修改同步、质量处置、发布流程和现有策略页面。

