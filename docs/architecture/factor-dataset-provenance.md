# 因子数据集依赖与输入版本溯源

状态：M2 兼容适配基线。

## 当前实现

`factor_lab/dataset_bindings.py` 为现有因子计算器提供旁路绑定，不改变现有因子 API：

- `close_to_close_return_1d` → `a_share_daily.close`
- `close_to_ma2_bias` → `a_share_daily.close`

两者默认使用 `raw` 行情，并要求按交易日进行 point-in-time 绑定。

## 版本解析

适配层复用 `MarketDataService.get_published_data_version`。解析成功时记录 `version_id`；日期范围缺失、解析器不存在或解析失败时记录 `unavailable + reason`，不填充模拟版本。

## 后续接入

M3 将把绑定显示到策略编辑器的数据需求校验中；M4 将把解析结果写入回测输入包和因子运行结果。现有策略编辑页面继续保留为备用入口。

