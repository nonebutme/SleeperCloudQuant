# Batch 86 - web-app 页面 B 最小因子只读访问层

## 本批目标
- 在不改后端架构、不新增依赖的前提下，为 web-app MVP 补齐页面 B。
- 仅复用现有 `/api/factors/*` 只读接口，提供最小查询壳层。
- 保持页面顺序约束下的实现收口：A、D、C 已有基础上，补齐 B。

## 本批范围
- 更新 `web/index.html`，启用因子页签并补齐页面 B 的最小表单与结果区。
- 更新 `web/app.js`，新增 factor definitions、pool members、summary、cross-section summary、values、top-n 六条只读查询逻辑。
- 更新 `web/styles.css`，补齐页面 B 所需的最小展示样式，并顺手清理此前页面文案乱码。

## 本批不做
- 不新增前端路由框架。
- 不进入因子写入、回测联动、图表可视化。
- 不扩展阶段 5 reporting 字段与 endpoint。
- 不进入报告快照实现。

## 验证
- 已验证：通过现有 demo server 成功命中 `GET /api/factors/pool-members?index_code=000300.XSHG&date=2020-01-02`，返回 200，symbols 为 `000001.XSHE,600000.XSHG`。
- 已验证：`web/` 三个文件已完成页面 B 静态壳层与脚本接入。
- 待补验证：由于当前工具审批额度与 helper 稳定性问题，`definitions`、`summary`、`values`、`top-n` 的本轮 HTTP 复验未全部跑完。

## 风险与暂停点
- 页面 C 仍保留已知风险：`run-once` 后立即通过当前 demo server 读取新 `run_id` 的 run detail 仍存在不稳定，当前前端仍采用“跳转并预填 run_id，手动查询”方案。
- 页面 B 当前为最小 JSON/列表展示壳层，尚未做页面级打磨。

## 结论
- 页面 B 已按 MVP 最小范围落地。
- A / D / C / B 四页的首批可访问壳层已形成一版可继续打磨的基线。
