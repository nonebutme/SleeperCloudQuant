# 下一批真实开发执行记录（Batch 84）
时间：`2026-07-06`

## 本批目标

执行上一轮建议中的：

- `[下一阶段：web-app 最小访问层]` 正式进入批次 1 实现，只做页面 A 与最小前端壳层

## 本批实际落地

### 1. 新增最小静态前端壳层

- `web/index.html`
- `web/styles.css`
- `web/app.js`

本批建立了一个最小可运行的页面壳层，并只点亮：

- 页面 A：市场数据查询页

当前仅包含：

- 标题区
- 最小导航
- 页面 A 三块查询区
- 最小结果区与错误提示区

### 2. 新增同源本地 web demo 启动脚本

- `scripts/run_formal_web_demo.py`

本批新增了一个最小 demo 启动脚本：

- 同时承载静态页面与 `/api/...` 请求
- 复用当前已有 `build_demo_app + dispatch_request`
- 保持现有 HTTP 4xx 语义，不新增页面专用后端接口

### 3. 打通页面 A 的三条最小读取路径

本批已实际联调：

- `GET /api/market/price-history`
- `GET /api/market/trading-calendar`
- `GET /api/market/sync-status/{dataset}`

并确认：

- 首页可访问
- 价格历史查询成功返回
- 交易日历查询成功返回
- 同步状态查询成功返回
- 非法请求仍返回 `400 {"detail":"invalid request parameters"}`

## 本批为何这样切

当前 `web-app` 首批实现的目标，不是立即做完整前端，而是先验证：

- 当前项目是否能跑起最小静态访问层
- 页面 A 是否能在不扩后端能力面的前提下完成真实联调

因此，本批只做页面 A 和同源 demo，不并行打开页面 D / C / B。

## 验证结果

已完成验证：

- `git diff --check -- web/index.html web/styles.css web/app.js scripts/run_formal_web_demo.py`
- 启动 `python scripts/run_formal_web_demo.py`
- 访问 `http://127.0.0.1:8010/`
- 请求 `http://127.0.0.1:8010/api/market/price-history?symbol=000001.XSHE&start_date=2020-01-01&end_date=2020-01-02`
- 请求 `http://127.0.0.1:8010/api/market/trading-calendar?start_date=2020-01-01&end_date=2020-01-03`
- 请求 `http://127.0.0.1:8010/api/market/sync-status/price_history`
- 请求失败样例 `http://127.0.0.1:8010/api/market/trading-calendar?start_date=2020-01-01`
- 实际运行 `python scripts/run_formal_verifications.py`

说明：本批仅进入 `web-app` 批次 1，实现范围仍限制在页面 A 与最小静态壳层。

## 下一步建议

1. `[下一阶段：web-app 最小访问层]` 若继续推进，可进入页面 D 的只读结果查看批次。
2. `[下一阶段：web-app 最小访问层]` 若希望先继续看页面 A，也可在不扩后端能力面的前提下，再补少量表格可读性与空状态细节。