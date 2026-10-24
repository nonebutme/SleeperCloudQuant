# FA-OPT 0→3 验收记录

## 验收口径

1. 制品绑定必须是精确、不可变的 `artifact_id`。
2. 未传 `value_field` 时必须使用 `aligned_value`。
3. 创建任务后不得自动执行。
4. 只有显式启动后才生成不可变报告。
5. 执行期间不得访问行情库或启动阶段 91.4。
6. 新表必须进入资产治理目录和血缘目录。

## 自动化证据

专项脚本使用临时 SQLite 数据库构造来源研究任务、24 条因子观测和一个不可变制品，验证：

- 缺失 `artifact_id` 不会按因子自动回退。
- 预检默认 `aligned_value`。
- 新建任务保持 `ready`、`started_at=null`、`report_id=null`。
- 显式 `start(wait=True)` 后任务完成并生成报告。
- 报告保留原 `artifact_id`、内容哈希、数据版本与质量报告身份。
- 两张新表存在，API 路由合同已注册。

## 阶段边界

- `已确认`：91.0–91.3 基线继续有效。
- `已确认`：91.4 未启动。
- `待确认`：人工浏览器业务验收不在本轮自动化验收范围内。

## Actual results (2026-08-14)

- `python scripts/smoke_test_factor_optimization.py`: passed.
- `python scripts/smoke_test_stage89_data_governance.py`: passed with 79 assets and 24 lineage edges.
- `python scripts/smoke_test_stage88_integrity_bridge.py`: passed.
- Stage 87 factor core/API and stage 91.0-91.3 governance regressions: passed.
- `python scripts/run_formal_verifications.py`: exit code 0; `[formal] all verifications passed`.
- Manual browser acceptance: not run. Stage 91.4: not started.
