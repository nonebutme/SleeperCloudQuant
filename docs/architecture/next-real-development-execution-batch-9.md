# 下一批真实开发执行记录（Batch 9）

时间：`2026-07-01`

## 本批目标

在不扩展 Web/API 入口的前提下，为 `factor_lab` 落地最小可验证正式骨架：

- 因子定义模型
- 单个基础价量因子计算器
- 因子结果 SQLite 落盘
- 独立 smoke test

## 本批实际落地

### 1. 新增 `factor_lab` 最小正式骨架

- `factor_lab/models.py`
- `factor_lab/calculators/price_factors.py`
- `factor_lab/storage/sqlite_factor_store.py`
- `factor_lab/__init__.py`

当前只实现一个保守型首因子：

- `close_to_close_return_1d`

该因子直接复用正式 `domain.market.models.Bar` 作为输入，不额外引入新的行情对象层。

### 2. 新增正式服务封装

- `app/services/factor_research_service.py`
- `app/services/__init__.py`

服务职责保持收敛：

- 从 `MarketDataService` 读取价格序列
- 运行单个基础价量因子计算
- 把结果写入共享 SQLite
- 提供最小结果查询能力

### 3. 新增独立 smoke 验证脚本

- `scripts/smoke_test_factor_lab.py`

验证范围：

- 因子计算是否产出预期行数
- 因子结果是否真实写入 SQLite
- 读取结果是否与预期收益率一致

### 4. 接入统一验证入口

- `scripts/run_formal_verifications.py`

让因子最小闭环纳入正式验证集合，但仍保持为独立脚本，便于后续单独扩展。

## 本批为何这样切

这是一个保守型、小步快跑切法：

- 先打通 `行情读取 -> 因子计算 -> SQLite 落盘 -> 结果回读`
- 暂不扩展 API、筛选排序、股票池、多因子编排
- 暂不引入财务因子和技术指标库

这样可以先确认 `factor_lab` 的正式开发主链路成立，再继续往结果筛选、评价和导出扩展。

## 已验证项

- `待执行` `python scripts/smoke_test_factor_lab.py`
- `待执行` `python scripts/run_formal_verifications.py`

## 未验证项

- 尚未把 `factor_lab` 接入统一 API
- 尚未补因子结果排序与 TopN 查询
- 尚未引入多因子并行计算

## 阻塞原因

- 无代码级阻塞；仅待本轮 smoke 实跑确认

## 潜在风险

- 当前因子存储表由 `factor_lab` 独立维护，后续若希望统一纳入 `data_platform` 元数据中心，可能需要再做一次轻量整合
- 当前只验证了基础价量因子，不代表财务因子或更复杂技术指标已具备稳定抽象

## 下一步建议

1. 若 smoke 通过，下一小步优先补因子结果排序/TopN 查询
2. 再补简单股票池输入
3. 然后再考虑第二个基础技术型因子
