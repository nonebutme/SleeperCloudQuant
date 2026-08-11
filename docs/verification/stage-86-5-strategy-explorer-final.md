# 阶段 86.5 策略工作台验证记录

## 验收范围

- 排行榜折线图、Top 10 与策略列表切换。
- 策略详情指标、说明与三个页签。
- OOS 八类图表，不包含 Capacity。
- Code 页签复用现有工作台。
- Version Notes 展示版本历史。

## 自动验证

- `node --check web/strategy-explorer.js`
- `python scripts/smoke_test_strategy_explorer_ui.py`
- 策略库、统一回测工作区、VTable 与正式 HTTP 适配器既有 smoke test。

## 发布判断

验证通过后可作为本地候选基线。真实 OOS 语义仍依赖未来为回测运行补充明确的样本内/样本外区间元数据。
