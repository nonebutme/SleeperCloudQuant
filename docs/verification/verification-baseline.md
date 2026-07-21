# 验证基线

## 自动化验证命令

- 统一验证入口：`python scripts/run_formal_verifications.py`
- 运行时与缓存验证：
  - `python scripts/verify_formal_fake_runtime.py`
  - `python scripts/verify_formal_reporting.py`
  - `python scripts/verify_formal_sqlite_cache.py`
- 因子与服务级 smoke：
  - `python scripts/smoke_test_factor_lab.py`
  - `python scripts/smoke_test_formal_services.py`
- API 与访问面 smoke：
  - `python scripts/smoke_test_formal_api.py`
  - `python scripts/smoke_test_formal_http_adapter.py`

## 人工验收范围

- 核心流程是否可走通
- 关键文案与业务术语是否一致
- 风险提示是否充分

## 当前阶段说明

- `已确认`：当前验证基线服务于阶段 7“最小本地量化服务闭环”。
- `已确认`：当前自动化验证重点覆盖 `data_platform`、`factor_lab`、`backtest_kernel`、`reporting`、`app/services`、`app/api` 与 `http_adapter` 的最小闭环。
- `已确认`：当前不要求在本阶段补齐独立 `lint` 或完整 `tests/` 体系后，才允许继续真实开发。
- `基于当前上下文推断`：后续若进入前端、AI 或报告快照实现，应在本基线之外新增对应专项验证，而不是直接扩写本阶段命令集。

## 输出结构

- `已验证项`
- `未验证项`
- `阻塞原因`
- `潜在风险`
- `发布判断`
