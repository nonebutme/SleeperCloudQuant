# 阶段 68：策略库管理可用性修复

## 问题与结论

- 用户反馈策略库为空、dual_ma_atr_dynamic_stop 不可见，且策略查询、新建、修改、删除不清晰。
- 后端策略列表实际已有 4 条；页面为空的直接原因是前端初始化阶段引用了不存在的可选处理函数，导致 main() 在加载策略库前中断。
- 策略管理界面原有大量自由文本输入，缺少清晰的目录、筛选、选中态和删除入口。

## 已实现能力

- 策略库以目录形式展示名称、ID、分类、版本和说明，并提供名称/ID 搜索、分类筛选、刷新和新建。
- 默认选中 dual_ma_atr_dynamic_stop，编辑区展示策略 ID、名称、分类、说明、结构化参数、源码和版本历史。
- 参数根据 Schema 渲染为数字、选项或开关控件；分类使用下拉选择。
- 保存策略时持久化分类和说明，并生成不可变新版本。
- 新增 DELETE /api/backtest/strategies/{strategy_id}。删除采用软归档：从活动策略库隐藏，但历史版本和既有回测引用继续可解析。
- 同一策略 ID 再次保存时解除归档并生成后续版本。
- SQLite 连接在事务结束后关闭，避免 Windows 文件句柄长期占用。
- Web Demo 和通用 HTTP Adapter 均支持 DELETE 转发。
- 策略库优先于行情、报告和 AI 面板加载；缺失的可选实验对比处理函数不再中断全页初始化。

## 验收

- python scripts/smoke_test_strategy_library_crud.py：通过。
- python scripts/smoke_test_versioned_custom_strategies.py：通过。
- python scripts/smoke_test_backtest_workspace_ui.py：通过。
- node --check web/app.js：通过。
- HTTP 实测：列表返回 4 条策略，双均线 ATR 策略存在；临时策略创建为 v1，DELETE 返回 archived，归档后不再出现在活动列表。
- Edge 桌面和 390x844 移动视口验收：策略库显示 4/4，双均线 ATR 策略默认选中，删除按钮启用，分类控件为 SELECT，无关键控件重叠。

## 边界

- 删除不物理清除源码、版本或回测引用。
- 本阶段不改变两种回测模式的资金与统计语义。
- 实验对比按钮的历史缺失实现不在本次范围；当前仅保证该可选功能不会阻断策略管理和全页初始化。

- 完整 python scripts/run_formal_verifications.py：全部通过。
