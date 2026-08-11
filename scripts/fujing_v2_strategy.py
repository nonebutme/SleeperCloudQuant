# =============================================================================
# 拂经v2 —— SleeperCloudQuant 可执行适配版
# =============================================================================
#
# 原始策略来自通达信公式。本文件把公式改写为项目约定的
# ``target-weights-v1`` 策略契约，使同一份代码可以直接用于：
#
# 1. 单品种回测；
# 2. 多股票独立账户回测；
# 3. 共享资金组合回测（按信号分数排序，最多持有前 N 只）。
#
# 重要语义边界：
#
# - 项目暂不具备通达信原生筹码分布数据，因此 WINNER 使用最近 120 日
#   “成交量加权典型价分布”近似；这是一种研究替代，不是逐笔筹码复刻。
# - 原公式中的 TROUGHBARS/ZIG 可能包含未来确认语义。这里使用仅依赖当前及
#   历史行情的 16 日滚动低点事件，避免未来函数和前视偏差。
# - 信号在当日收盘后确认，目标仓位从下一根 K 线生效；当回测参数
#   ``execution_price=open`` 时，对应“次日开盘买入/卖出”。
# - 本策略仅用于本地量化研究，不构成投资建议、收益承诺或实盘交易指令。

# 声明策略运行所依赖的数据集。策略工作台在保存和运行前会校验该依赖，
# 回测任务也会把实际使用的数据版本写入证据链。
DATASET_REQUIREMENTS = [
    "a_share_daily",
    "a_share_catalog",
    "trade_calendar",
    "trading_status",
    "corporate_actions",
]

# 参数定义与策略版本一起保存。策略工作台根据该字典动态生成表单，回测任务
# 保存实际取值快照，因此不同策略不再共享固定的均线参数模板。
PARAMETER_SCHEMA = {
    "minimum_listing_bars": {
        "type": "integer", "default": 200, "min": 20, "step": 1,
        "label": "最低上市交易日数", "unit": "交易日",
        "help": "积累足够历史行情后才允许产生入场信号。",
    },
    "trough_window": {
        "type": "integer", "default": 16, "min": 3, "step": 1,
        "label": "低点观察窗口", "unit": "交易日",
        "help": "用于识别因果滚动低点事件。",
    },
    "winner_window": {
        "type": "integer", "default": 120, "min": 20, "step": 1,
        "label": "获利盘计算窗口", "unit": "交易日",
        "help": "成交量加权典型价分布的滚动观察长度。",
    },
    "winner_spread_min": {
        "type": "number", "default": 30.0, "min": 0, "max": 100, "step": 1,
        "label": "获利盘差值下限", "unit": "%",
        "help": "最高价与最低价近似获利盘比例差必须超过该值。",
    },
    "trailing_stop": {
        "type": "number", "default": 0.95, "min": 0.5, "max": 0.999, "step": 0.005,
        "label": "移动止损保留比例", "unit": "比例",
        "help": "0.95 表示收盘价跌破持仓期最高价的 95% 后退出。",
    },
    "volume_ratio_window": {
        "type": "integer", "default": 5, "min": 2, "step": 1,
        "label": "成交量均值窗口", "unit": "交易日",
        "help": "共享组合对候选股票进行量比排序时使用。",
    },
    "position_size": {
        "type": "number", "default": 1.0, "min": 0, "max": 1, "step": 0.05,
        "label": "目标仓位", "unit": "比例", "help": "单股目标仓位上限。",
    },
    "execution_price": {
        "type": "enum", "default": "open", "options": ["open", "close"],
        "label": "信号执行价格", "scope": "execution", "help": "open 表示信号确认后的下一交易日开盘执行。",
    },
}

# 数据集查询契约：
# - 只读取策略计算需要的日线 OHLC、成交量和成交额；
# - latest_published 表示使用数据中心最近一次已发布版本；
# - unavailable 表示缺数时明确失败，不用演示数据或静默填充值代替。
DATASET_QUERY = {
    "dataset_id": "a_share_daily",
    "fields": ["open", "high", "low", "close", "volume", "amount"],
    "version_policy": "latest_published",
    "missing_data_policy": "unavailable",
}


def _winner_ratio(index, price, typical_prices, volumes, window):
    # 计算 WINNER 的近似值：在指定滚动窗口内，统计“典型价不高于当前比较价”
    # 的成交量占总成交量的比例。结果范围为 [0, 1]。
    #
    # 直观解释：若结果为 0.10，可近似理解为窗口内约 10% 的成交量对应成本
    # 不高于当前比较价。该算法没有逐笔持仓迁移信息，因此只用于替代研究。
    start = max(0, index - window + 1)
    total = sum(volumes[start:index + 1])
    # 停牌、缺失或异常数据可能导致窗口成交量为 0；此时返回 0，避免除零。
    if total <= 0:
        return 0.0
    winning = 0.0
    for offset in range(start, index + 1):
        # 用成交量作为权重，避免把极低成交量交易日与放量交易日等权处理。
        if typical_prices[offset] <= price:
            winning += volumes[offset]
    return winning / total


def _volume_ratio(index, volumes, window):
    # 量比 = 当日成交量 / 前 window 个交易日平均成交量。
    # 注意 history 不包含当前交易日，防止当日成交量同时进入分子和基准均值。
    start = max(0, index - window)
    history = volumes[start:index]
    baseline = sum(history) / len(history) if history else 0.0
    # 历史均量不可用时返回 0，使该股票自然排在候选列表末端。
    return volumes[index] / baseline if baseline > 0 else 0.0


def _is_allowed_security(bars):
    # 在进入昂贵的指标计算前完成证券范围过滤。
    if not bars:
        return False
    first = bars[0]
    catalog = (first.get("datasets") or {}).get("a_share_catalog") or {}
    # symbol 可能是 000001、000001.XSHE 等形式；过滤规则只使用六位代码。
    symbol = str(catalog.get("symbol") or first.get("symbol") or "").split(".")[0]
    name = str(catalog.get("name") or first.get("name") or "").upper()
    # 对齐原公式的范围：排除科创板、北交所常见前缀，以及沪深 B 股。
    excluded_prefixes = ("688", "8", "43", "83", "87", "92", "900", "200")
    # S、ST、*ST 名称都以 S 或 *S 开头，因此一并排除。
    return not symbol.startswith(excluded_prefixes) and not name.startswith(("S", "*S"))


def _build_signal_series(bars, parameters):
    # 本函数是策略核心，分为三步：
    # 1. 规范化行情并预计算筹码/低点指标；
    # 2. 生成收盘后可确认的入场条件与量比排名分数；
    # 3. 用持仓状态机把信号转换为逐日目标仓位。
    if not _is_allowed_security(bars):
        # 被排除的证券仍返回与行情等长的序列，便于批量回测统一对齐日期。
        return [0.0 for _ in bars], [0.0 for _ in bars]
    # 所有参数都设置安全边界，防止前端误输入负数、0 或超过 100% 的仓位。
    minimum_days = max(1, int(parameters.get("minimum_listing_bars", 200)))
    trough_window = max(3, int(parameters.get("trough_window", 16)))
    winner_window = max(20, int(parameters.get("winner_window", 120)))
    # 前端输入 30 表示 30%，内部统一转为 0.30。
    spread_minimum = max(0.0, float(parameters.get("winner_spread_min", 30.0))) / 100.0
    # trailing_stop=0.95 表示收盘价跌破持仓期最高价的 95% 时触发退出。
    trailing_stop = min(max(float(parameters.get("trailing_stop", 0.95)), 0.5), 0.999)
    position_size = min(max(float(parameters.get("position_size", 1.0)), 0.0), 1.0)
    volume_ratio_window = max(2, int(parameters.get("volume_ratio_window", 5)))

    # 将可能为 None/空值的行情字段转换为确定的浮点数。
    # open/high/low 缺失时回退到 close；volume 最低截断为 0。
    opens = [float(bar.get("open") or bar.get("close") or 0.0) for bar in bars]
    highs = [float(bar.get("high") or bar.get("close") or 0.0) for bar in bars]
    lows = [float(bar.get("low") or bar.get("close") or 0.0) for bar in bars]
    closes = [float(bar.get("close") or 0.0) for bar in bars]
    volumes = [max(0.0, float(bar.get("volume") or 0.0)) for bar in bars]
    # 典型价采用 OHLC4。它是筹码成本位置的日频代理，不是实际成交均价。
    typical_prices = [(opens[index] + highs[index] + lows[index] + closes[index]) / 4.0 for index in range(len(bars))]

    # 预计算每个交易日的三个基础序列，后续组合条件只读取历史切片。
    winner_lows = []
    winner_highs = []
    trough_events = []
    for index in range(len(bars)):
        # WINNER(L)：近似成本低于当日最低价的筹码比例。
        winner_lows.append(_winner_ratio(index, lows[index], typical_prices, volumes, winner_window))
        # WINNER(H)：近似成本低于当日最高价的筹码比例。
        winner_highs.append(_winner_ratio(index, highs[index], typical_prices, volumes, winner_window))
        start = max(0, index - trough_window + 1)
        rolling_low = min(lows[start:index + 1]) if lows[start:index + 1] else lows[index]
        # 因果低点事件：当日最低价达到最近 trough_window 日最低位，同时日内
        # 振幅至少 0.04 元，用于排除完全无波动的一字行情。
        trough_events.append(lows[index] <= rolling_low and highs[index] > lows[index] + 0.04)

    # entries 保存“当日收盘后确认”的入场信号；entry_scores 保存该信号的
    # 量比分数，供共享资金组合在多个同时出现的候选中选择前 3 名。
    entries = [False for _ in bars]
    entry_scores = [0.0 for _ in bars]
    for index in range(len(bars)):
        datasets = bars[index].get("datasets") or {}
        calendar = datasets.get("trade_calendar") or {}
        trading_status = datasets.get("trading_status") or {}
        # 数据集明确标记为休市、停牌或不可交易时，不产生入场信号。
        if calendar.get("is_open") is False or trading_status.get("is_tradable") is False:
            continue
        # 至少积累 minimum_days 根 K 线，用日线数量近似“上市超过 200 日”。
        if index + 1 < minimum_days:
            continue
        # 最近 5 日内至少出现一次滚动低点事件。
        recent_buy = any(trough_events[max(0, index - 4):index + 1])
        # 最近 6 日内 WINNER(L) 曾低于 10%，表示低价获利筹码比例较低。
        recent_low = any(value < 0.10 for value in winner_lows[max(0, index - 5):index + 1])
        # 最近 10 日若 WINNER(H) 曾高于 80%，则认为高获利筹码状态过强并排除。
        recent_high = any(value > 0.80 for value in winner_highs[max(0, index - 9):index + 1])
        # 当日高低价对应的近似筹码比例差，模拟原公式 KK 条件。
        spread = abs(winner_highs[index] - winner_lows[index])
        entries[index] = recent_buy and recent_low and not recent_high and spread > spread_minimum
        if entries[index]:
            # 分数只负责组合横截面排名，不直接改变单股目标仓位大小。
            entry_scores[index] = _volume_ratio(index, volumes, volume_ratio_window)

    # 把信号转换为逐日目标仓位和分数。
    # weights 取值 0~1；scores 在持仓期间保留入场时的量比分数。
    weights = [0.0 for _ in bars]
    scores = [0.0 for _ in bars]
    holding = False
    # pending_entry 把收盘确认信号延迟到下一根 K 线，避免使用当日收盘后
    # 才知道的信息在当日开盘成交。
    pending_entry = False
    pending_score = 0.0
    active_score = 0.0
    highest_price = 0.0
    for index in range(len(bars)):
        if pending_entry:
            # 当前 K 线是信号后的下一交易日；目标仓位从这里变为 position_size。
            holding = True
            pending_entry = False
            active_score = pending_score
            highest_price = highs[index]
        if holding:
            # 最高价只使用入场日至当前日的已知数据，作为移动止盈止损基准。
            highest_price = max(highest_price, highs[index])
            weights[index] = position_size
            scores[index] = active_score
            # 当日收盘跌破最高价的 trailing_stop 比例后，将 holding 置为 False。
            # 当前日目标仓位仍为持有；下一交易日目标仓位变为 0，因此在
            # execution_price=open 配置下对应“次日开盘卖出”。
            if closes[index] < highest_price * trailing_stop:
                holding = False
                active_score = 0.0
            continue
        if entries[index] and index + 1 < len(bars):
            # 最后一根 K 线之后没有可执行交易日，因此不创建悬空入场指令。
            pending_entry = True
            pending_score = entry_scores[index]
    return weights, scores


def generate_target_weights(bars, parameters):
    # target-weights-v1 的必需入口：返回每个交易日的目标仓位比例。
    # 单品种和独立账户模式直接使用该序列；共享组合模式会再施加总暴露、
    # 最大持仓数、整手、现金和 T+1 等账户级约束。
    weights, _ = _build_signal_series(bars, parameters)
    return weights


def generate_signal_scores(bars, parameters):
    # 共享资金组合的可选排名入口：同一天多个股票给出入场/持仓信号时，
    # 引擎按该分数从高到低选取 max_positions 个候选。本策略的分数是
    # 入场日量比，并在持仓期间保持不变。
    _, scores = _build_signal_series(bars, parameters)
    return scores
