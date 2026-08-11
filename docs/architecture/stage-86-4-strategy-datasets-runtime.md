# 策略数据集运行时契约

## 已确认边界

- M4 DataCenter Catalog 是唯一数据集目录权威，策略数据集不维护第二份目录或数据。
- 目录展示 M4 的全部 20 个数据集；治理数据集只用于浏览和审计。
- 策略继续使用 `target-weights-v1`：`generate_target_weights(bars, parameters)`。
- 策略通过 `DATASET_REQUIREMENTS` 声明依赖。
- `StrategyDatasetResolver` 在执行前校验依赖，把辅助数据按交易日注入 `bar["datasets"][dataset_id]`。
- `a_share_daily`、`index_daily`、`a_share_catalog`、`trade_calendar`、`trading_status` 和 `corporate_actions` 已具备只读适配器，状态为 `executable`。
- 行情数据作为主时间序列；证券目录、交易日历、交易状态和公司行为按标的与交易日注入策略上下文。交易日历和交易状态要求窗口完整，公司行为允许窗口内无事件。
- 其他已连接数据集继续提供文档、Research 配方和策略模板；适配器完成前状态为 `template_only`，页面明确显示“仅研究/待适配”。
- 停用或未发布数据集状态为 `not_available`。

## 运行证据

回测结果的 `strategy_binding.datasets` 保存数据集 ID、绑定方式、辅助标的、匹配行数和请求行数。Research 预览只允许调用注册过的只读适配器，不开放任意 SQL、文件或 Python 执行。策略参数由源码顶层 `PARAMETER_SCHEMA` 声明，保存版本时以源码声明为权威并校验类型、必填项、范围和枚举值，避免工作台固定参数与实际策略漂移。

## 复用裁决

QuantConnect 仅作为 Dataset 产品结构、文档层次和统一调用体验的设计参考；本项目不复制其源码或云端商业数据。实现复用当前 M4、Published Version、策略库、VTable 和本地回测运行时。
