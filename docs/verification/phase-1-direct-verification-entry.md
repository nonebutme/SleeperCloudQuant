# Phase 1 直接验证入口

## 1. 当前统一入口

- `python scripts/run_formal_verifications.py`

## 2. 当前单脚本入口

- `python scripts/verify_formal_fake_runtime.py`
- `python scripts/verify_formal_reporting.py`
- `python scripts/verify_formal_sqlite_cache.py`

## 3. 说明

- 这些脚本当前验证的是正式实现链路。
- 脚本内部已自带最小 fake 支撑，不再依赖仓内 `phase1` 兼容入口或 fake/demo 资产。
