# 下一批真实开发执行记录（Batch 12）

时间：`2026-07-01`

## 本批目标

沿着已落地的 `factor_lab` 最小骨架，补第二个基础技术型因子：

- 新增一个仅依赖价格序列的技术因子
- 复用既有 SQLite 落盘、排序与股票池能力
- 对应 smoke 验证

## 本批实际落地

### 1. 新增第二个基础技术型因子

- `factor_lab/calculators/price_factors.py`
- `factor_lab/calculators/__init__.py`
- `factor_lab/__init__.py`

新增：

- `CloseToMa2BiasCalculator`
- `factor_id = close_to_ma2_bias`

当前算法保持最小化：

- 以最近 2 个收盘价均值为 MA2
- 计算 `close / ma2 - 1`

### 2. 扩展正式因子服务层

- `app/services/factor_research_service.py`

新增：

- `run_close_to_ma2_bias(...)`
- `run_close_to_ma2_bias_for_symbols(...)`
- `run_close_to_ma2_bias_for_index(...)`

同时把单标的与股票池执行逻辑收敛到服务内的最小公共实现，避免重复扩散。

### 3. 扩展 smoke 验证

- `scripts/smoke_test_factor_lab.py`

新增验证：

- 单标的 MA2 因子计算与落盘
- 股票池 MA2 因子运行
- 指数成分股股票池 MA2 因子运行
- MA2 因子 Top1 排序读取

## 本批为何这样切

这一步仍然遵循保守策略：

- 不扩 API
- 不引入指标第三方库
- 不做通用因子注册中心
- 只补一个可验证、可排序、可入股票池的第二因子

这样能先证明 `factor_lab` 已具备“多基础因子并存”的最小能力，再决定后面是否走更通用的组织方式。

## 已验证项

- `待执行` `python scripts/smoke_test_factor_lab.py`
- `待执行` `python scripts/run_formal_verifications.py`
- `待执行` `python scripts/smoke_test_formal_services.py`

## 未验证项

- 尚未提供因子运行/查询 API
- 尚未支持更多窗口参数配置
- 尚未支持多因子统一编排与比较报告

## 阻塞原因

- 无代码级阻塞；仅待本轮 smoke 实跑确认

## 潜在风险

- 当前第二因子仍是固定窗口 `MA2`，后续若扩展到更多窗口或参数化因子，服务层方法命名可能需要再抽象
- 当前服务层内部通过最小公共方法复用，但尚未形成正式的因子注册机制

## 下一步建议

1. 若验证通过，下一小步优先评估是否抽出最小因子注册表
2. 或者继续保守推进，先补 factor 查询 API
3. 再之后考虑多因子批量研究汇总
