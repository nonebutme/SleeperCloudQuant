# 第一轮逐文件候选确认结果：data-platform

## 一、文档定位

- `已确认` 本文档是 `data-platform` 模块第一轮逐文件候选确认结果。
- `已确认` 本轮只基于少量高相关目录与文件头部进行确认，不展开大规模源码阅读。
- `已确认` 本文档不直接触发文件复制或代码实现。

## 二、本轮确认范围

### 2.1 来源仓库

- `D:/Dev-AI/Dev/projects/SleeperCloudQuant-old`
- `D:/Dev-AI/Dev/projects/TradingAgents-CN-main`

### 2.2 本轮重点核对的高相关文件

来自 `SleeperCloudQuant-old`：

- `SleeperCloudQuant/core/repository.py`
- `SleeperCloudQuant/data/cache/cached_market_data_repository.py`
- `SleeperCloudQuant/data/cache/sqlite_cache.py`
- `SleeperCloudQuant/data/ricequant/ricequant_repository.py`

来自 `TradingAgents-CN-main`：

- `tradingagents/dataflows/data_source_manager.py`
- `tradingagents/dataflows/providers/base_provider.py`
- `app/services/data_sources/base.py`
- `app/services/data_sources/manager.py`

## 三、本轮结论

### 3.1 已确认可进入候选名单的文件

#### 来自 `SleeperCloudQuant-old`

1. `SleeperCloudQuant/core/repository.py`
   结论：`直接采纳候选`
   理由：明确定义了 `MarketDataRepository` 抽象，且接口正好覆盖价格历史、指数成分、财务指标、交易日历这类数据平台核心读取边界。

2. `SleeperCloudQuant/data/cache/cached_market_data_repository.py`
   结论：`直接采纳候选`
   理由：职责非常清晰，是“缓存优先仓储包装器”，与当前规划中的“统一读取入口 + 本地缓存”结构高度一致。

3. `SleeperCloudQuant/data/cache/sqlite_cache.py`
   结论：`改造后采纳候选`
   理由：它同时承载了市场数据缓存和大量回测元数据落盘逻辑，适合作为本地缓存与轻量存储思路来源，但不宜整段直接作为 `data-platform` 实现。

4. `SleeperCloudQuant/data/ricequant/ricequant_repository.py`
   结论：`改造后采纳候选`
   理由：它是标准的上游数据仓储实现，并且已经做了标准化输出与派生字段注入，适合承接为首个 provider/adapter 类型候选。

#### 来自 `TradingAgents-CN-main`

5. `tradingagents/dataflows/providers/base_provider.py`
   结论：`仅参考`
   理由：它提供了清晰的数据 provider 抽象接口，适合作为 provider 分层结构参考，但当前接口更偏异步、多市场、多数据类型，直接采纳成本偏高。

6. `app/services/data_sources/base.py`
   结论：`仅参考`
   理由：它是应用层数据源适配器基类，抽象清晰，但接口范围已经包含实时行情、新闻、K线等扩展能力，超过第一阶段最小数据底座需要。

7. `app/services/data_sources/manager.py`
   结论：`仅参考`
   理由：它展示了按优先级调度多个 adapter 的结构方式，适合作为“多数据源 fallback 组织方式”参考，但当前强依赖数据库优先级与一致性检查，偏上层。

8. `tradingagents/dataflows/data_source_manager.py`
   结论：`仅参考`
   理由：它更像数据源编排与运行时管理器，而不是第一阶段需要的最小仓储抽象，不适合作为首批直接候选文件。

## 四、建议排除的文件类别

### 4.1 来自 `SleeperCloudQuant-old`

- `data/ricequant/ricequant_backtest_adapter.py`
  排除理由：职责属于 `backtest-kernel`，不是 `data-platform`

- `core/services/*backtest*`
  排除理由：属于回测服务层，不属于市场数据底座

- `tests/test_ricequant_backtest_adapter.py`
  排除理由：当前不是测试确认轮次

### 4.2 来自 `TradingAgents-CN-main`

- `app/routers/*`
  排除理由：属于 Web/API 入口层，不属于数据平台底座

- `app/services/*financial_data_service.py`、`*historical_data_service.py`、`*stock_data_service.py`
  排除理由：更偏应用服务层，依赖上层组织方式，不适合作为首批底层文件候选

- `frontend/*`
  排除理由：不在第一阶段范围内

- `scripts/*`
  排除理由：当前不是脚本迁移轮次

- `docs/*`
  排除理由：当前只确认代码候选，不确认外部文档

## 五、来源角色再确认

### 5.1 `SleeperCloudQuant-old`

- `已确认` 是 `data-platform` 第一轮逐文件候选的主来源
- `已确认` 更适合提供：
  - 仓储抽象
  - 缓存包装器
  - 本地缓存实现思路
  - 上游市场数据仓储实现

### 5.2 `TradingAgents-CN-main`

- `已确认` 在 `data-platform` 第一轮中更适合作为结构参考来源
- `已确认` 更适合提供：
  - provider / adapter 分层方式
  - 多数据源管理器组织方式
  - 配置驱动型来源选择思路

## 六、风险与待确认项

1. `sqlite_cache.py` 当前同时包含市场缓存与回测元数据存储职责，后续若纳入，需要先做职责拆分判断。
2. `ricequant_repository.py` 当前包含派生字段注入逻辑，后续需要确认哪些字段属于 `data-platform`，哪些应上移到研究层。
3. `TradingAgents-CN-main` 的 data source manager 明显偏应用层编排，后续若误当作底层仓储候选，容易引入过重依赖。

## 七、下一步建议

1. 进入 `backtest-kernel` 第一轮逐文件候选确认
2. 后续若继续细化 `data-platform`，建议只对以下 4 个文件做下一轮更深确认：
   - `core/repository.py`
   - `data/cache/cached_market_data_repository.py`
   - `data/cache/sqlite_cache.py`
   - `data/ricequant/ricequant_repository.py`

## 八、发布判断

### 已验证项

- `data-platform` 已有一组清晰的首批高价值候选文件
- `SleeperCloudQuant-old` 与 `TradingAgents-CN-main` 在本模块中的角色差异已明确

### 未验证项

- 这 4 个候选文件之间是否存在需要一起迁移的隐式依赖
- 是否还存在未纳入本轮查看但同样高价值的仓储辅助文件

### 阻塞原因

- 当前尚未进入更深一轮源码细读

### 发布判断

- `已确认` 可以进入 `backtest-kernel` 的第一轮逐文件候选确认
- `待确认` 当前还不建议直接进入文件复制执行

