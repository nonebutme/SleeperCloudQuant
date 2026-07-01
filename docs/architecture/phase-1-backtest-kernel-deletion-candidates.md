# Phase 1 第六批正式回收：Backtest Kernel 实际下线候选清单

## 1. 评估目标

- 仅针对 `backtest_kernel phase1` 子图，形成第二批可执行的实际下线候选清单。
- 本轮不删除文件，只输出删除前确认单。

## 2. 评估范围

- `backtest_kernel/gateway/phase1_contracts.py`
- `backtest_kernel/adapters/phase1_rqalpha_support.py`
- `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`
- `backtest_kernel/use_cases/phase1_run_single_backtest.py`

## 3. 已确认事实

- `已确认`：`backtest_kernel/phase1.py` 当前只保留 7 个兼容别名：
  - `Phase1BacktestGateway`
  - `Phase1BacktestRequest`
  - `Phase1BacktestResult`
  - `Phase1ConnectedRqalphaGateway`
  - `Phase1RqalphaRuntime`
  - `Phase1RunSingleBacktest`
  - `Phase1RunSingleBacktestRequest`
- `已确认`：兼容入口导入检查通过，结果为 `backtest-kernel-phase1-compat-surface-ok`。
- `已确认`：代码区交叉检查未发现正式主路径继续引用本批 4 个深层文件。
- `已确认`：这 4 个文件当前剩余引用只存在于 `backtest_kernel phase1` 子图内部。
- `基于当前上下文推断`：如果没有仓外脚本直接导入这些深层文件，则它们已经具备进入整组删除评估的条件。

## 4. 逐文件候选判断

| 文件 | 当前角色 | 剩余引用情况 | 本轮判断 | 说明 |
| --- | --- | --- | --- | --- |
| `backtest_kernel/gateway/phase1_contracts.py` | phase1 子图基础合同 | 被 `phase1_rqalpha_support.py`、`phase1_connected_rqalpha_gateway.py`、`phase1_run_single_backtest.py` 引用 | `需联动删除` | 不能单删，应和整个 backtest_kernel phase1 子图一起处理 |
| `backtest_kernel/adapters/phase1_rqalpha_support.py` | phase1 runtime 支持函数 | 被 `phase1_connected_rqalpha_gateway.py` 引用 | `需联动删除` | 建议与 gateway/contracts 一并处理 |
| `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py` | phase1 gateway 入口 | 依赖 `phase1_contracts.py`、`phase1_rqalpha_support.py` | `本轮可删除候选` | 正式 gateway 已稳定，当前仅剩历史副本价值 |
| `backtest_kernel/use_cases/phase1_run_single_backtest.py` | phase1 use case 入口 | 依赖 `phase1_contracts.py` | `本轮可删除候选` | 正式 use case 已具备同类职责 |

## 5. 第一批建议删除分组

建议把 4 个文件作为同一组删除候选处理：

- `backtest_kernel/gateway/phase1_contracts.py`
- `backtest_kernel/adapters/phase1_rqalpha_support.py`
- `backtest_kernel/adapters/phase1_connected_rqalpha_gateway.py`
- `backtest_kernel/use_cases/phase1_run_single_backtest.py`

原因：四者形成一个完整小闭环，整组删比单文件删更稳。

## 6. 本轮代码收束判断

- `已确认`：`backtest_kernel/phase1.py` 当前没有额外多余兼容别名，本轮无需再收紧。
- `已确认`：未发现需要额外改写到正式模块的残余活代码引用。
- `已确认`：因此本轮不需要再做代码修改，直接进入删除前确认阶段即可。

## 7. 删除前确认单

若进入真正删除，建议按以下顺序人工确认：

1. 是否同意把这 4 个文件整组删除，而不是单文件删除。
2. 是否接受本轮只删除 `backtest_kernel phase1` 深层副本，不触碰 `reporting` 子图。
3. 是否接受删除后保留 `backtest_kernel/phase1.py` 兼容入口不变。

## 8. 建议结论

- `已确认`：`backtest_kernel phase1` 子图已经具备进入第二批实际删除的条件。
- `待确认`：你是否批准执行这 4 个文件的真正删除动作。
