# 下一批真实开发执行记录（Batch 71）
时间：`2026-07-05`

## 本批目标

执行上一轮建议中的：

- `[阶段 7：最小本地量化服务闭环]` 更新 `docs/verification/verification-baseline.md`，把当前真实验证命令集同步进去
- `[阶段 7：最小本地量化服务闭环]` 再把 `services / api / http_adapter` 三条 smoke 纳入 `scripts/run_formal_verifications.py`

## 本批实际落地

### 1. 更新验证基线文档

- `docs/verification/verification-baseline.md`

本批把原来仍停留在占位状态的验证基线，正式更新为当前真实命令集，明确纳入：

- fake runtime 验证
- reporting 验证
- sqlite cache 验证
- factor lab smoke
- services smoke
- API smoke
- HTTP adapter smoke

### 2. 收束统一验证入口

- `scripts/run_formal_verifications.py`

本批把以下三条阶段 7 smoke 正式并入统一入口：

- `smoke_test_formal_services.py`
- `smoke_test_formal_api.py`
- `smoke_test_formal_http_adapter.py`

这样后续回归不再需要人工记忆阶段 7 的补充分支命令。

### 3. 实跑统一验证入口

本批已实际运行：

- `python scripts/run_formal_verifications.py`

结果为：

- fake runtime 通过
- reporting 通过
- sqlite cache 通过
- factor lab smoke 通过
- services smoke 通过
- API smoke 通过
- HTTP adapter smoke 通过

## 本批为何这样切

阶段 7 当前最重要的，不是继续扩大功能面，而是把“已经存在的最小闭环”变成“可以一键回归的最小闭环”。

先把验证基线文档和统一入口收束好，后续再改服务或 API 时，回归成本会明显更低，也更不容易漏掉阶段 7 的访问面。

## 验证结果

已完成验证：

- 更新并复核 `docs/verification/verification-baseline.md`
- 更新并复核 `scripts/run_formal_verifications.py`
- 实际运行 `python scripts/run_formal_verifications.py`
- `git diff --check -- docs/verification/verification-baseline.md scripts/run_formal_verifications.py docs/architecture/next-real-development-execution-batch-71.md`

说明：本批仅更新验证基线文档、统一验证入口与批次记录，不涉及生产功能逻辑改动。

## 下一步建议

1. `[阶段 7：最小本地量化服务闭环]` 开始逐项复核 `app/services` 的职责边界，优先确认哪些是最小闭环必须保留、哪些已超出当前阶段范围。
2. `[阶段 7：最小本地量化服务闭环]` 再针对 `app/api` 与 `http_adapter` 做一轮契约级收束，减少阶段 7 之后继续扩接口面的冲动。
