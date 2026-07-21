# 下一批真实开发执行记录（Batch 13）

时间：`2026-07-01`

## 本批目标

沿着已落地的 `factor_lab` 最小骨架，补一个最小因子注册表与统一运行入口：

- 因子定义列表
- `factor_id` 统一运行
- `factor_id` 统一股票池运行
- `factor_id` 统一指数成分股股票池运行

## 本批实际落地

### 1. 新增最小因子注册表

- `factor_lab/registry.py`
- `factor_lab/__init__.py`

新增：

- `FactorRegistry`

当前保持内存内置注册方式：

- `close_to_close_return_1d`
- `close_to_ma2_bias`

### 2. 扩展正式因子服务层统一入口

- `app/services/factor_research_service.py`

新增：

- `list_factor_definitions()`
- `run_factor(...)`
- `run_factor_for_symbols(...)`
- `run_factor_for_index(...)`

同时保留已有专用方法，作为向后兼容包装，不中断当前已有使用方式。

### 3. 扩展 smoke 验证

- `scripts/smoke_test_factor_lab.py`

新增验证：

- 因子定义列表读取
- 两个因子的统一单标的运行
- 两个因子的统一股票池运行
- 两个因子的统一指数成分股股票池运行

## 本批为何这样切

这一步仍然遵循保守策略：

- 不扩 API
- 不做复杂插件化注册
- 不做动态配置加载
- 只把“两个因子已经存在的能力”收敛到一个最小统一入口

这样后续如果要继续补因子、补 API、补批量研究编排，服务层就不需要继续复制方法了。

## 已验证项

- `待执行` `python scripts/smoke_test_factor_lab.py`
- `待执行` `python scripts/run_formal_verifications.py`
- `待执行` `python scripts/smoke_test_formal_services.py`

## 未验证项

- 尚未提供 factor API
- 尚未支持外部配置驱动的因子注册
- 尚未支持多因子统一比较报告

## 阻塞原因

- 无代码级阻塞；仅待本轮 smoke 实跑确认

## 潜在风险

- 当前注册表仍是代码内硬编码，后续若因子数量继续增长，需要再决定是否引入更正式的注册协议
- 当前统一入口主要解决运行收敛，不代表查询/导出层已经统一抽象

## 下一步建议

1. 若验证通过，下一小步优先补 factor API 只读查询入口
2. 或继续保持保守，先补统一多因子批量运行摘要
3. 再之后考虑把注册表升级为更通用的装配方式
