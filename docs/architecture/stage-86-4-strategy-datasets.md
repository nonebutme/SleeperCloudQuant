# 阶段 86.4：策略数据集

## 状态

- `已确认`：用户批准按 A—E 五阶段实现。
- `已确认`：主导航名称为“策略数据集”。
- `已确认`：列表采用左侧分类、右侧数据集卡片；详情保留 `About`、`Documentation`、`Research`、`Examples`。
- `已确认`：复用数据中心目录、规范 SQLite 数据、Published 数据版本和 M4 只读资产能力。
- `已确认`：不新增数据源、第三方依赖或数据库表。

## 产品边界

策略数据集是现有数据中心之上的研究消费层，不拥有第二份目录或第二份数据。数据中心继续负责同步、质量、发布和治理；策略数据集负责说明、调用契约、研究配方、策略示例和策略工作台交接。

数据集按 `consumer_scopes` 区分 `strategy`、`factor_research`、`data_browser` 和 `governance`。治理对象可以展示，但不得伪装为可执行策略输入。

## 首批范围

- `a_share_daily`
- `trade_calendar`
- `a_share_catalog`
- `corporate_actions`
- `industry_classification`
- `index_components`

## 兼容约束

- 现有策略继续使用 `target-weights-v1`：`generate_target_weights(bars, parameters)`。
- 示例通过 `DATASET_REQUIREMENTS` 声明数据依赖，通过 Strategy Manifest 固化字段、复权、缺失策略和版本策略。
- 示例实例化只生成草稿，不自动写入策略库或启动回测。
- 只有 `runtime_status=executable` 的示例才可声明可直接进入当前回测链；其余示例必须标记为研究模板。

## 验收

- 分类、卡片、详情和四页签可用。
- 示例代码可复制，完整策略可导入现有策略工作台。
- Dataset Schema、示例依赖和 Published 版本信息来自现有权威目录。
- M4、数据中心和旧策略行为保持不变。
