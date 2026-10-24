"""拂经 v2 V7 候选源码；验证通过前不得设为活动策略版本。"""

DATASET_REQUIREMENTS = [
    "a_share_daily",
    "a_share_catalog",
    "trade_calendar",
    "trading_status",
    "factor_values",
]

FACTOR_REQUIREMENTS = [
    "winner_proxy_low_120d",
    "winner_proxy_high_120d",
    "winner_proxy_spread_120d",
    "causal_trough_event_16d",
    "amplitude_ratio_1d",
]

# 本策略自行把收盘信号安排到下一根 bar，运行时不得再次移位。
SIGNAL_TIMING = "before_open"

PORTFOLIO_EXECUTION_CONTRACT = {
    "rebalance_policy": "event_driven",
    "capacity_replacement_policy": "incumbent_priority",
    "event_driven_slot_weight_policy": "portfolio_exposure_divided_by_max_positions",
    "max_single_position_weight": 0.15,
    "position_cap_trigger": "prior_close_snapshot_next_tradable_open_trim_to_cap",
    "position_cap_released_cash": "retain_as_cash",
}

DATASET_CONTRACTS = [
    {
        "dataset_id": "a_share_daily",
        "required_fields": ["symbol", "open", "high", "low", "close", "volume"],
        "minimum_history": 200,
        "adjustment": "qfq",
        "coverage_mode": "same_trade_date",
        "missing_data_policy": "unavailable",
        "version_policy": "exact_published",
    },
    {
        "dataset_id": "a_share_catalog",
        "required_fields": [
            "symbol", "listing_status", "risk_warning", "valid_from", "available_at",
        ],
        "coverage_mode": "as_of_trade_date",
        "missing_data_policy": "unavailable",
        "version_policy": "exact_published",
    },
    {
        "dataset_id": "trade_calendar",
        "required_fields": ["trade_date", "is_open"],
        "coverage_mode": "same_trade_date",
        "missing_data_policy": "unavailable",
        "version_policy": "exact_published",
    },
    {
        "dataset_id": "trading_status",
        "required_fields": ["trade_date", "is_tradable"],
        "coverage_mode": "same_trade_date",
        "missing_data_policy": "unavailable",
        "version_policy": "exact_published",
    },
    {
        "dataset_id": "factor_values",
        "required_fields": ["factor_id", "artifact_id", "value"],
        "minimum_history": 10,
        "coverage_mode": "same_trade_date",
        "missing_data_policy": "unavailable",
        "version_policy": "exact_published",
    },
]

PARAMETER_SCHEMA = {
    "minimum_listing_bars": {
        "type": "integer", "default": 200, "min": 200, "step": 1,
        "label": "最低有效交易日数", "unit": "交易日",
    },
    "winner_low_threshold": {
        "type": "number", "default": 0.10, "min": 0, "max": 1, "step": 0.01,
        "label": "WINNER低位阈值", "unit": "比例",
    },
    "winner_high_threshold": {
        "type": "number", "default": 0.80, "min": 0, "max": 1, "step": 0.01,
        "label": "WINNER高位排除阈值", "unit": "比例",
    },
    "winner_spread_min": {
        "type": "number", "default": 0.30, "min": 0, "max": 1, "step": 0.01,
        "label": "WINNER差值下限", "unit": "比例",
    },
    "amplitude_ratio_min": {
        "type": "number", "default": 0.004, "min": 0, "max": 0.20, "step": 0.001,
        "label": "昨收振幅比例下限（开发期候选）", "unit": "比例",
    },
    "volume_ratio_window": {
        "type": "integer", "default": 5, "min": 2, "max": 60, "step": 1,
        "label": "量比窗口", "unit": "交易日",
    },
    "trailing_stop": {
        "type": "number", "default": 0.95, "min": 0.5, "max": 0.999, "step": 0.005,
        "label": "移动止损保留比例", "unit": "比例",
    },
    "position_size": {
        "type": "number", "default": 1.0, "min": 0, "max": 1, "step": 0.05,
        "label": "单标的目标仓位", "unit": "比例",
    },
    "execution_price": {
        "type": "enum", "default": "open", "options": ["open"],
        "label": "信号后下一交易日开盘执行", "scope": "execution",
    },
}


def _factor_value(bar, factor_id):
    factors = (bar.get("datasets") or {}).get("factor_values") or {}
    factor_record = factors.get(factor_id) or {}
    value = factor_record.get("value")
    return None if value is None else float(value)


def _is_allowed_security(bar):
    catalog = (bar.get("datasets") or {}).get("a_share_catalog") or {}
    symbol = str(catalog.get("symbol") or bar.get("symbol") or "").split(".")[0]
    excluded_prefixes = ("688", "689", "8", "43", "83", "87", "92", "900", "200")
    if symbol.startswith(excluded_prefixes):
        return False
    listing_status = str(catalog.get("listing_status") or "").lower()
    risk_warning = catalog.get("risk_warning")
    return listing_status in ("listed", "active", "normal") and risk_warning is False


def _volume_ratio(index, volumes, window):
    history = volumes[max(0, index - window):index]
    baseline = sum(history) / len(history) if history else 0.0
    return volumes[index] / baseline if baseline > 0 else 0.0


def _build_signal_series(bars, parameters):
    count = len(bars)
    if not count:
        return [], []
    minimum_days = max(200, int(parameters.get("minimum_listing_bars", 200)))
    low_threshold = min(max(float(parameters.get("winner_low_threshold", 0.10)), 0.0), 1.0)
    high_threshold = min(max(float(parameters.get("winner_high_threshold", 0.80)), 0.0), 1.0)
    spread_minimum = min(max(float(parameters.get("winner_spread_min", 0.30)), 0.0), 1.0)
    amplitude_minimum = max(float(parameters.get("amplitude_ratio_min", 0.004)), 0.0)
    trailing_stop = min(max(float(parameters.get("trailing_stop", 0.95)), 0.5), 0.999)
    position_size = min(max(float(parameters.get("position_size", 1.0)), 0.0), 1.0)
    volume_window = max(2, int(parameters.get("volume_ratio_window", 5)))
    highs = [float(bar.get("high") or bar.get("close") or 0.0) for bar in bars]
    closes = [float(bar.get("close") or 0.0) for bar in bars]
    volumes = [max(0.0, float(bar.get("volume") or 0.0)) for bar in bars]
    winner_lows = [_factor_value(item, "winner_proxy_low_120d") for item in bars]
    winner_highs = [_factor_value(item, "winner_proxy_high_120d") for item in bars]
    spreads = [_factor_value(item, "winner_proxy_spread_120d") for item in bars]
    troughs = [_factor_value(item, "causal_trough_event_16d") for item in bars]
    amplitudes = [_factor_value(item, "amplitude_ratio_1d") for item in bars]

    entries = [False for _ in bars]
    entry_scores = [0.0 for _ in bars]
    for index, bar in enumerate(bars):
        if not _is_allowed_security(bar):
            continue
        datasets = bar.get("datasets") or {}
        if (datasets.get("trade_calendar") or {}).get("is_open") is False:
            continue
        if (datasets.get("trading_status") or {}).get("is_tradable") is False:
            continue
        if index + 1 < minimum_days:
            continue
        recent_buy = any(
            troughs[offset] == 1.0
            and amplitudes[offset] is not None
            and amplitudes[offset] > amplitude_minimum
            for offset in range(max(0, index - 4), index + 1)
        )
        recent_low = any(
            value is not None and value < low_threshold
            for value in winner_lows[max(0, index - 5):index + 1]
        )
        recent_high = any(
            value is not None and value > high_threshold
            for value in winner_highs[max(0, index - 9):index + 1]
        )
        spread = spreads[index]
        entries[index] = (
            recent_buy and recent_low and not recent_high
            and spread is not None and spread > spread_minimum
        )
        if entries[index]:
            entry_scores[index] = _volume_ratio(index, volumes, volume_window)

    weights = [0.0 for _ in bars]
    scores = [0.0 for _ in bars]
    holding = False
    pending_entry = False
    pending_score = 0.0
    active_score = 0.0
    highest_price = 0.0
    for index in range(count):
        if pending_entry:
            holding = True
            pending_entry = False
            active_score = pending_score
            highest_price = highs[index]
        if holding:
            highest_price = max(highest_price, highs[index])
            weights[index] = position_size
            scores[index] = active_score
            if closes[index] < highest_price * trailing_stop:
                holding = False
                active_score = 0.0
            continue
        if entries[index] and index + 1 < count:
            pending_entry = True
            pending_score = entry_scores[index]
    return weights, scores


def generate_target_weights(bars, parameters):
    weights, _ = _build_signal_series(bars, parameters)
    return weights


def generate_signal_scores(bars, parameters):
    _, scores = _build_signal_series(bars, parameters)
    return scores
