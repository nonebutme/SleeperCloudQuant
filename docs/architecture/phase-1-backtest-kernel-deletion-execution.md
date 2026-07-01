# Phase 1 第七批正式回收：Backtest Kernel 深层 Phase1 副本实际删除记录

## 1. 本轮执行范围

已实际删除以下 4 个深层 `phase1_*` 文件：

- `backtest_kernel/gateway/phase1_contracts.py`
- `backtest_kernel/adapters/phase1_rqalpha_support.py`
- `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`
- `backtest_kernel/use_cases/phase1_run_single_backtest.py`

## 2. 保留项

- `backtest_kernel/phase1.py` 继续保留，作为兼容入口。
- `backtest_kernel` 正式实现文件保持不变：
  - `gateway/contracts.py`
  - `adapters/rqalpha_ricequant_gateway.py`
  - `use_cases/run_single_backtest.py`
- fake/demo 资产继续保留：
  - `adapters/phase1_fake_runtime.py`
  - `use_cases/phase1_fake_runtime_demo.py`

## 3. 已验证项

### 3.1 正式验证脚本

执行 `scripts/run_phase1_verifications.py` 通过，输出为：

- `[formal] running verify_phase1_fake_runtime.py`
- `formal fake runtime verification passed`
- `[formal] running verify_phase1_fake_reporting.py`
- `formal reporting verification passed`
- `[formal] running verify_phase1_sqlite_cache.py`
- `formal sqlite cache verification passed`
- `[formal] all verifications passed`

### 3.2 正式包导入

- `formal-package-imports-ok`

### 3.3 Backtest Kernel 兼容入口导入

- `backtest-kernel-phase1-compat-surface-ok`

## 4. 当前判断

- `已确认`：`backtest_kernel phase1` 深层副本已完成第二批实际删除。
- `已确认`：正式主路径和统一验证链未受影响。
- `已确认`：`backtest_kernel/phase1.py` 兼容入口仍可用。
- `待确认`：下一步是否继续对 `reporting phase1` 子图做删除候选准备。
