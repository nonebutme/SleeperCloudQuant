# phase-1-first-merge-prep-checklist

## 1. 文档定位

- 目标：为 `phase1_* -> 正式骨架` 的第一批实际合并提供可执行准备清单。
- 范围：本清单只覆盖“开始真正合并前”的准备动作，不直接执行合并。
- 状态：`已确认（第一批合并准备层）`

## 2. 为什么先做这一步

虽然当前三类本地验证已经通过，但真正开始回收合并时，风险点会从“静态接线是否成立”切换到“既有骨架文件是否会被安全替换”。

因此，在直接改正式骨架前，先明确：

- 先合哪一块
- 具体改哪些文件
- 每一步如何验证
- 哪些条件不满足就先停

## 3. 第一批建议只合并哪一块

建议第一批只处理：

- `data_platform`

原因：

- 这一块已经有最完整的 `phase1_*` 实现层
- 已有 `sqlite cache` 本地验证通过
- 它是后续 `backtest_kernel` 和 `reporting` 的基础
- 风险仍低于直接碰 `backtest_kernel` 的 runtime 接线

## 4. 第一批合并目标文件

### 4.1 正式骨架文件

- `data_platform/repository/contracts.py`
- `data_platform/repository/cached_market_repository.py`
- `data_platform/storage/sqlite_metadata_store.py`
- `data_platform/providers/ricequant_repository.py`

### 4.2 当前 phase1_* 来源

- `data_platform/repository/phase1_contracts.py`
- `data_platform/repository/phase1_cached_market_repository.py`
- `data_platform/storage/phase1_sqlite_metadata_store.py`
- `data_platform/providers/phase1_ricequant_support.py`
- `data_platform/providers/phase1_connected_ricequant_repository.py`

### 4.3 本轮不动的文件

- `data_platform/providers/phase1_ricequant_repository.py`
- `data_platform/phase1.py`
- fake / verify 脚本

说明：

- 第一批只合并“正式实现所需最小主链路”
- 先不处理兼容导出与演示资产迁移

## 5. 第一批建议的具体顺序

### Step 1

- 用 `phase1_contracts.py` 覆盖性更新 `repository/contracts.py`

目标：

- 让正式仓储协议先与当前验证通过的 phase-1 协议对齐

验证：

- 导入路径不变
- 方法签名与 `phase1_cached_market_repository.py` 一致

### Step 2

- 用 `phase1_cached_market_repository.py` 回收进 `repository/cached_market_repository.py`

目标：

- 让正式缓存包装层与已验证逻辑对齐

验证：

- 仍能构建 cache key
- 仍调用 `fetch_market_data_cache / upsert_market_data_cache`

### Step 3

- 用 `phase1_sqlite_metadata_store.py` 回收进 `storage/sqlite_metadata_store.py`

目标：

- 让正式 SQLite store 至少具备当前已验证通过的 `market_data_cache` 能力

验证：

- `ensure_schema`
- `fetch_market_data_cache`
- `upsert_market_data_cache`

### Step 4

- 把 `phase1_ricequant_support.py` 与 `phase1_connected_ricequant_repository.py` 的最小静态接线合并进 `providers/ricequant_repository.py`

目标：

- 让正式 provider 文件具备：
  - client 协议
  - 归一化函数
  - injectable repository

验证：

- 不接真实 SDK 的情况下，静态导入能成立

## 6. 每一步后的最小验证

每完成一步后，都建议至少执行：

1. `scripts/run_phase1_verifications.py`

如果 helper 稳定，也建议补充：

1. 直接导入正式骨架对应模块
2. 直接导入 `phase1_*` 模块
3. 对比两边是否仍可共存

## 7. 第一批暂不做的事情

以下内容建议明确后置：

- 删除任何 `phase1_*` 文件
- 迁移 fake runtime / fake store
- 修改 `backtest_kernel`
- 修改 `reporting`
- 改统一导出文件

原因：

- 第一批的目标是“把 data_platform 正式骨架对齐到已验证实现”
- 不是一次性完成全仓收口

## 8. 停止条件

出现以下任一情况，第一批应立即停下：

1. `scripts/run_phase1_verifications.py` 回归失败
2. helper 再次无法稳定更新既有文件
3. 合并后出现导入循环或协议签名不一致
4. 需要连带修改 `backtest_kernel` 才能继续

## 9. 完成判断

第一批可视为完成，当且仅当：

- `data_platform` 正式骨架文件已承载 phase-1 主链路逻辑
- `scripts/run_phase1_verifications.py` 仍通过
- `phase1_*` 文件虽然仍保留，但已不再是 data-platform 主实现入口

## 10. 第一批完成后的下一步

完成 data-platform 回收后，建议第二批再进入：

1. `backtest_kernel`
2. `reporting`

不建议直接跳过 data-platform 去改后两块。
