# MVP 冻结基线

## 当前基线

- `已确认` 当前 MVP 基线目标是：满足最初需求的可视化验收，展示五仓库拆解重构成果，并完成本地服务闭环验证。
- `已确认` 当前版本不是实盘交易系统，不输出真实投资建议，不要求真实外部服务在线。

## 已冻结能力

| 能力域 | 当前状态 | 验收入口 |
| --- | --- | --- |
| 需求基线 | 已补齐 | `docs/requirements/*` |
| 五仓库拆解 | 已补齐比较和复用矩阵 | `docs/code-archaeology/repo-comparison.md`, `docs/architecture/reuse-integration-plan.md` |
| 数据中心 | 已接入 API 和 Web 展示 | Web 数据中心 |
| 因子分析 | 已接入 API 和 Web 展示 | Web 因子分析 |
| 策略回测 | 已接入单次回测和报告跳转 | Web 策略回测 |
| AI 分析 | 已接入本地结构化 demo 服务 | Web AI 分析 |
| 报告中心 | 已接入 run detail 和 batch summary | Web 报告中心 |
| 配置中心 | 已接入非敏感状态 API | Web 配置中心 |
| 重构溯源 | 已接入静态映射矩阵 | Web 重构溯源 |
| 统一验证 | 已通过 | `python scripts/run_formal_verifications.py` |

## 下一阶段候选

1. 真实数据源接入与授权确认。
2. 真实 rqalpha 运行时接入。
3. 真实 LLM Provider 接入与免责声明流程。
4. 浏览器截图级视觉 QA 与交互验收。
5. 外部仓库逐文件许可证复核。

## 发布判断

- `已确认` 当前基线可以进入人工 MVP 审批。
- `待确认` 用户是否接受当前 demo/runtime 边界，并授权进入真实外部依赖接入阶段。
