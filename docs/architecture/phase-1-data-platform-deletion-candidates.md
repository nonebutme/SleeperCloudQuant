# Phase 1 第四批正式回收：Data Platform 实际下线候选清单

## 1. 评估目标

- 仅针对 `data_platform phase1` 子图，形成第一批可执行的实际下线候选清单。
- 本轮不删除文件，只输出删除前确认单。

## 2. 评估范围

- `data_platform/repository/phase1_contracts.py`
- `data_platform/repository/phase1_cached_market_repository.py`
- `data_platform/storage/phase1_sqlite_metadata_store.py`
- `data_platform/providers/phase1_ricequant_repository.py`
- `data_platform/providers/phase1_ricequant_support.py`
- `data_platform/providers/phase1_connected_ricequant_repository.py`

## 3. 已确认事实

- `已确认`：`data_platform/phase1.py` 当前只保留 5 个兼容别名：
  - `Phase1CachedMarketDataRepository`
  - `Phase1MarketDataRepository`
  - `Phase1RicequantClientProtocol`
  - `Phase1RicequantMarketDataRepository`
  - `Phase1SqliteMetadataStore`
- `已确认`：兼容入口导入检查通过，结果为 `data-platform-phase1-compat-surface-ok`。
- `已确认`：代码区交叉检查未发现正式主路径继续引用本批 6 个深层文件。
- `已确认`：这 6 个文件当前剩余引用只存在于 `data_platform phase1` 子图内部。
- `基于当前上下文推断`：如果没有仓外脚本直接引用这些深层文件，则它们已经具备进入整组删除评估的条件。

## 4. 逐文件候选判断

| 文件 | 当前角色 | 剩余引用情况 | 本轮判断 | 说明 |
| --- | --- | --- | --- | --- |
| `data_platform/repository/phase1_contracts.py` | phase1 子图基础合同 | 被 `phase1_cached_market_repository.py`、`phase1_ricequant_repository.py`、`phase1_connected_ricequant_repository.py` 引用 | `需联动删除` | 不能单删，应和整个 data_platform phase1 子图一起处理 |
| `data_platform/repository/phase1_cached_market_repository.py` | phase1 缓存仓库入口 | 依赖 `phase1_contracts.py`、`phase1_sqlite_metadata_store.py` | `本轮可删除候选` | 正式缓存仓库已稳定，当前仅剩历史副本价值 |
| `data_platform/storage/phase1_sqlite_metadata_store.py` | phase1 SQLite 副本 | 被 `phase1_cached_market_repository.py` 引用 | `需联动删除` | 建议与 phase1 缓存仓库一起删除 |
| `data_platform/providers/phase1_ricequant_repository.py` | 占位 provider 副本 | 无正式引用；自身仍是未实现占位 | `本轮可删除候选` | 保留价值最低，优先删除候选 |
| `data_platform/providers/phase1_ricequant_support.py` | phase1 provider 支持函数 | 被 `phase1_connected_ricequant_repository.py` 引用 | `需联动删除` | 建议与 connected provider 一起处理 |
| `data_platform/providers/phase1_connected_ricequant_repository.py` | phase1 provider 入口 | 依赖 `phase1_contracts.py`、`phase1_ricequant_support.py` | `本轮可删除候选` | 正式 provider 已具备同类职责 |

## 5. 第一批建议删除分组

### 5.1 分组 A：缓存子组

建议作为同一组删除候选处理：

- `data_platform/repository/phase1_contracts.py`
- `data_platform/repository/phase1_cached_market_repository.py`
- `data_platform/storage/phase1_sqlite_metadata_store.py`

原因：三者形成一个小闭环，拆着删风险更高，整组删更干净。

### 5.2 分组 B：Provider 子组

建议作为同一组删除候选处理：

- `data_platform/providers/phase1_ricequant_repository.py`
- `data_platform/providers/phase1_ricequant_support.py`
- `data_platform/providers/phase1_connected_ricequant_repository.py`

原因：三者也是一个独立小闭环，而且正式 provider 已可替代。

## 6. 本轮代码收束判断

- `已确认`：`data_platform/phase1.py` 当前没有额外多余兼容别名，本轮无需再收紧。
- `已确认`：未发现需要额外改写到正式模块的残余活代码引用。
- `已确认`：因此本轮不需要再做代码修改，直接进入删除前确认阶段即可。

## 7. 删除前确认单

若进入真正删除，建议按以下顺序人工确认：

1. 是否同意按“分组 A / 分组 B”整组删除，而不是单文件删除。
2. 是否接受本轮只删除 `data_platform phase1` 深层副本，不触碰 `backtest_kernel` 与 `reporting`。
3. 是否接受删除后保留 `data_platform/phase1.py` 兼容入口不变。

## 8. 建议结论

- `已确认`：`data_platform phase1` 子图已经具备进入第一批实际删除的条件。
- `待确认`：你是否批准执行“分组 A + 分组 B”的真正删除动作。
