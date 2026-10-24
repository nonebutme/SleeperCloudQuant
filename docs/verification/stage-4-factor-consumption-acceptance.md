# 阶段四因子消费闭环验收

## 验收口径

1. `factor_values` 权威注册必须包含 `artifact_id` 与 `aligned_value`。
2. 导出必须绑定精确 `artifact_id`，默认使用 `aligned_value`。
3. 导出源码必须能经策略数据解析器和 `target-weights-v1` 执行器运行。
4. 缺少绑定、制品不存在或日期覆盖不足必须显式失败，禁止 latest 回退。
5. 导出不得写入任务，不得自动启动。
6. 阶段五和 91.4 保持未启动。

## 自动化证据

`python scripts/smoke_test_stage4_factor_consumption.py` 使用临时 SQLite：

- 发布一个含完整 `aligned_value` 的不可变因子制品；
- 导出静态策略因子声明并核对制品、研究配置和显式启动边界；
- 通过策略解析器绑定同日因子值，并执行得到预期目标权重；
- 验证缺少 `artifact_id` 不回退 latest；
- 验证不存在的制品与日期覆盖缺口均失败；
- 验证 HTTP 路由返回相同的固定制品声明。

## 验证结果

- 阶段四因子消费专项：通过。
- 阶段 88 完整性桥回归：通过。
- 策略 Dataset 合同回归：通过。
- FA-OPT 固定制品优化回归：通过。
- 统一正式验证：退出码 0，最终输出 `[formal] all verifications passed`。
- 人工浏览器验收：未执行。
- 阶段 91.4：未启动。
