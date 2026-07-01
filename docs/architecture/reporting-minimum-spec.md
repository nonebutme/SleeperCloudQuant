# 报告模块最小规格规划

## 一、文档定位

- `已确认` 本文档是 `reporting` 模块的最小规格规划版，不是实现文档。
- `已确认` 本文档只定义第一阶段报告模块的最小输入、输出、边界和依赖关系。
- `已确认` 本文档不直接触发模板实现、页面开发或报告生成代码编写。

## 二、输入来源

- `docs/architecture/phase-1-stitching-plan.md`
- `docs/architecture/domain-boundary-spec.md`
- `docs/architecture/backtest-kernel-minimum-spec.md`
- `docs/architecture/config-center-minimum-spec.md`

## 三、范围边界

### 3.1 纳入范围

- 回测报告输入边界
- 报告摘要对象边界
- 历史记录边界
- 模板配置引用边界
- 报告查询边界

### 3.2 当前不纳入

- AI 报告完整生成链路
- 图表渲染实现
- Web 展示页面
- 多模板复杂编排
- 自然语言长报告生成实现

## 四、模块目标

第一阶段 `reporting` 只服务于以下目标：

1. 接收 `backtest-kernel` 提供的标准化结果输入
2. 生成统一的 `BacktestReport` 摘要对象
3. 保留最小历史记录与查询边界
4. 为后续模板扩展预留稳定配置接口

## 五、总体设计原则

### 5.1 已确认

- 第一阶段 `reporting` 优先服务于回测闭环，不扩展为完整 AI 报告中心。
- 报告模块消费标准化结果，不反向侵入回测运行时实现。
- 报告对象边界必须与 `domain-boundary-spec.md` 中的 `BacktestReport` 保持一致。

### 5.2 基于当前上下文推断

- 第一阶段更适合“结构化摘要报告”，而不是完整叙事型长文报告。
- 报告模板配置应保持最小化，避免先于结果结构稳定。

## 六、最小输入边界

### 6.1 来自 `backtest-kernel`

- 回测摘要
- 指标摘要
- 风险摘要
- 订单/成交摘要
- 观察性日志摘要

### 6.2 来自 `config-center`

- 报告模板启用状态
- 模板分类
- 模板版本或结构引用

## 七、最小输出边界

### 7.1 核心输出对象

- `BacktestReport`

### 7.2 最小字段承接

- `report_id`
- `result_id`
- `generated_at`
- `summary`
- `performance_metrics`
- `risk_metrics`
- `observations`
- `conclusion`

### 7.3 查询输出

- 单次回测报告摘要
- 历史报告列表摘要

## 八、历史记录边界

### 8.1 职责

- 保证报告结果可追踪、可回查
- 作为回测历史阅读入口，而不是执行层日志存储入口

### 8.2 最小记录范围

- `report_id`
- `result_id`
- `generated_at`
- `report_type`
- `summary`

### 8.3 边界要求

- 报告历史与回测运行日志分层保存
- 当前阶段只要求摘要级历史能力

## 九、模板配置引用边界

### 9.1 职责

- 允许报告模块引用最小模板配置
- 保持报告结构可控但不过度复杂

### 9.2 最小引用内容

- `template_id`
- `template_name`
- `report_type`
- `summary_schema_ref`

### 9.3 边界要求

- 模板配置仅影响结构和字段组织
- 不要求首阶段支持复杂模板切换

## 十、来源项目承接关系

### 10.1 承接 `SleeperCloudQuant-old`

- 回测摘要结构
- 指标解释组织方式
- 历史记录思路

### 10.2 补充参考 `TradingAgents-CN-main`

- 结构化输出组织方式
- 模板配置引用思路

## 十一、前置依赖

- `backtest-kernel-minimum-spec.md` 已定义标准化结果输出边界
- `domain-boundary-spec.md` 已定义 `BacktestReport` 对象边界
- `config-center-minimum-spec.md` 已定义最小模板配置边界

## 十二、当前不做的事

- 不生成 AI 研究长文报告
- 不定义完整模板 DSL
- 不定义前端展示协议
- 不定义图表数据渲染结构

## 十三、发布判断

### 已验证项

- `reporting` 已形成与 `backtest-kernel`、`domain`、`config-center` 的最小依赖闭环
- 当前范围已限制在回测报告摘要和历史查询边界

### 未验证项

- `summary` 与 `observations` 的最终结构粒度
- 历史记录是否需要更细的版本管理

### 阻塞原因

- 当前仍未进入字段级实现确认

### 潜在风险

- 若在结果结构稳定前先固化模板实现，后续返工成本高

### 发布判断

- `已确认` 本文档可作为第一阶段 `reporting` 模块的最小规格基础
- `待确认` 仍不应把本文件直接视为最终实现契约

