# phase-1-fake-assets-verification-note

## 1. 本轮新增验证脚本

- `scripts/verify_phase1_fake_runtime.py`
- `scripts/verify_phase1_fake_reporting.py`

## 2. 验证目标

### 2.1 fake runtime

- 验证 `Phase1RunSingleBacktest`
- `Phase1ConnectedRqalphaGateway`
- `Phase1FakeRqalphaRuntime`

是否能形成：

- request -> payload -> normalized result

### 2.2 fake reporting

- 验证 `Phase1RunResultsReader`
- `Phase1BatchComparisonService`
- `Phase1FakeReportingStore`

是否能形成：

- run detail 聚合
- account/trade/yearly chart 数据生成
- batch comparison summary 聚合

## 3. 当前状态

- 验证脚本已新增
- 当前轮次仍未实际执行

## 4. 说明

- 当前可以确认“验证入口已落地”
- 当前不能确认“验证已经通过”

## 5. 下一步建议

- 若 helper 恢复稳定：
  - 先执行 fake runtime / fake reporting 验证
  - 再执行 sqlite cache 验证
- 若 helper 继续不稳：
  - 继续整理 future merge 清单
