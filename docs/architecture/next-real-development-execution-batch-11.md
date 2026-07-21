# 下一批真实开发执行记录（Batch 11）

时间：`2026-07-01`

## 本批目标

沿着已落地的 `factor_lab` 最小骨架，补齐最基础的股票池输入能力：

- 显式 `symbols` 股票池
- 基于 `index_code` 的最小指数成分股股票池
- 对应 smoke 验证

## 本批实际落地

### 1. 扩展股票池运行结果模型

- `factor_lab/models.py`

新增：

- `FactorPoolRunResult`

用于表达一次因子在一个股票池上的批量运行结果。

### 2. 扩展行情服务层股票池读取入口

- `app/services/market_data_service.py`

新增：

- `get_index_components(...)`

当前仅做最小透传，不提前引入更复杂的股票池抽象层。

### 3. 扩展正式因子服务层

- `app/services/factor_research_service.py`

新增：

- `run_close_to_close_return_for_symbols(...)`
- `run_close_to_close_return_for_index(...)`

当前能力保持收敛：

- 支持显式 symbol 列表
- 支持按指数成分读取 symbol 列表
- 复用既有单标的因子计算、SQLite 落盘与排序查询链路

### 4. 扩展 smoke 验证

- `scripts/smoke_test_factor_lab.py`

新增验证：

- symbol 列表股票池批量运行
- index 成分股股票池批量运行
- 与既有 TopN 排序读取能力协同验证

## 本批为何这样切

这一步仍然遵循保守策略：

- 不扩 API
- 不做独立股票池管理模块
- 不做多因子批量调度
- 只把“单因子可对一组股票批量跑起来”补齐

这样能让 `factor_lab` 从“单标的研究”推进到“最小股票池研究”，但仍保持实现收敛、可验证。

## 已验证项

- `待执行` `python scripts/smoke_test_factor_lab.py`
- `待执行` `python scripts/run_formal_verifications.py`
- `待执行` `python scripts/smoke_test_formal_services.py`

## 未验证项

- 尚未提供 HTTP 查询/运行入口
- 尚未支持持久化股票池定义
- 尚未支持多因子批量研究编排

## 阻塞原因

- 无代码级阻塞；仅待本轮 smoke 实跑确认

## 潜在风险

- 当前 index 成分股能力仍依赖上游仓储直接返回，后续若要支持缓存或快照时间语义，可能需要补数据中心侧落盘
- 当前股票池运行仍按串行逐只执行，尚未引入调度与并发控制

## 下一步建议

1. 若验证通过，下一小步优先补第二个基础技术型因子
2. 然后再评估是否需要因子运行 API
3. 之后再考虑股票池持久化定义
