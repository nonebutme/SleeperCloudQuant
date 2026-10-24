"""Curated, versioned examples for the strategy Dataset catalog."""

from __future__ import annotations

from data_platform.data_center_catalog import DATASET_CATALOG
from data_platform.dataset_registry import DatasetRegistry
from domain.dataset.product_models import DatasetExample


_REGISTRY = DatasetRegistry(DATASET_CATALOG)
_DATASET_TITLES = {
    str(item["dataset_id"]): str(item.get("display_name") or item["dataset_id"])
    for item in DATASET_CATALOG
}
_REQUIRED_FIELDS = {
    dataset_id: tuple(field.name for field in _REGISTRY.require(dataset_id).fields)
    for dataset_id in _DATASET_TITLES
}
_EXECUTABLE_DATASETS = {
    "a_share_daily",
    "index_daily",
    "a_share_catalog",
    "trade_calendar",
    "trading_status",
    "corporate_actions",
}


def list_dataset_examples(dataset_id: str | None = None) -> tuple[DatasetExample, ...]:
    examples = tuple(example for key in _DATASET_TITLES for example in _examples_for(key))
    if dataset_id is None:
        return examples
    normalized = str(dataset_id).strip()
    return tuple(example for example in examples if example.dataset_id == normalized)


def get_dataset_example(dataset_id: str, example_id: str) -> DatasetExample:
    for example in list_dataset_examples(dataset_id):
        if example.example_id == example_id:
            return example
    raise KeyError(f"dataset example not found: {dataset_id}/{example_id}")


def _examples_for(dataset_id: str) -> tuple[DatasetExample, ...]:
    title = _DATASET_TITLES[dataset_id]
    fields = _REQUIRED_FIELDS[dataset_id]
    return (
        DatasetExample(
            example_id=f"{dataset_id}-getting-started",
            dataset_id=dataset_id,
            kind="getting_started",
            title=f"调用 {title}",
            description="声明数据集、字段、复权和版本策略；运行时只读取已发布版本。",
            source_code=_getting_started_source(dataset_id, fields),
            dataset_ids=(dataset_id,),
            required_fields=fields,
        ),
        DatasetExample(
            example_id=f"{dataset_id}-research",
            dataset_id=dataset_id,
            kind="research",
            title=f"研究 {title}",
            description="使用受控数据切片检查覆盖、缺失和时间边界。",
            source_code=_research_source(dataset_id),
            dataset_ids=(dataset_id,),
            required_fields=fields,
        ),
        _strategy_example(dataset_id, fields),
    )


def _getting_started_source(dataset_id: str, fields: tuple[str, ...]) -> str:
    return (
        f'DATASET_REQUIREMENTS = ["{dataset_id}"]\n\n'
        "DATASET_QUERY = {\n"
        f'    "dataset_id": "{dataset_id}",\n'
        f"    \"fields\": {list(fields)!r},\n"
        '    "version_policy": "latest_published",\n'
        '    "missing_data_policy": "unavailable",\n'
        "}\n"
    )


def _research_source(dataset_id: str) -> str:
    return (
        f'DATASET_REQUIREMENTS = ["{dataset_id}"]\n\n'
        "def summarize_dataset(rows):\n"
        "    dates = [row.get(\"trade_date\") or row.get(\"event_date\") for row in rows]\n"
        "    dates = [value for value in dates if value]\n"
        "    return {\n"
        "        \"row_count\": len(rows),\n"
        "        \"coverage_start\": min(dates) if dates else None,\n"
        "        \"coverage_end\": max(dates) if dates else None,\n"
        "    }\n"
    )


def _strategy_example(dataset_id: str, fields: tuple[str, ...]) -> DatasetExample:
    auxiliary = dataset_id != "a_share_daily"
    requirements = ("a_share_daily", dataset_id) if auxiliary else (dataset_id,)
    if dataset_id == "factor_values":
        source = _factor_value_source(requirements)
        description = (
            "调用示例固定读取 aligned_value；请通过指定 artifact_id 的策略声明导出"
            "替换占位因子与制品后执行。"
        )
        parameters = {
            "factor_artifacts": {
                "replace_with_exported_factor_id": "replace_with_exact_artifact_id"
            },
            "factor_threshold": 0.0,
            "position_size": 1.0,
            "execution_price": "close",
        }
    else:
        source = (
            _index_regime_source(requirements)
            if dataset_id == "index_daily"
            else _moving_average_source(requirements)
        )
        description = (
            "可直接导入当前 target-weights-v1 策略工作台。"
            if not auxiliary
            else "可导入策略工作台；辅助数据的运行时切片接入前按研究模板使用。"
        )
        parameters = {
            "short_window": 5,
            "long_window": 20,
            "position_size": 1.0,
            "execution_price": "close",
        }
    return DatasetExample(
        example_id=f"{dataset_id}-strategy",
        dataset_id=dataset_id,
        kind="strategy",
        title=f"{_DATASET_TITLES[dataset_id]}策略模板",
        description=description,
        source_code=source,
        dataset_ids=requirements,
        required_fields=fields,
        parameters=parameters,
        assets={"symbols": ["000001.XSHE"], "universe_type": "explicit_symbols"},
        runtime_status="executable" if dataset_id in _EXECUTABLE_DATASETS else "template_only",
    )


def _factor_value_source(dataset_ids: tuple[str, ...]) -> str:
    return f'''DATASET_REQUIREMENTS = {list(dataset_ids)!r}
FACTOR_REQUIREMENTS = ["replace_with_exported_factor_id"]
FACTOR_VALUE_FIELD = "aligned_value"

def generate_target_weights(bars, parameters):
    threshold = float(parameters.get("factor_threshold", 0.0))
    position_size = min(max(float(parameters.get("position_size", 1.0)), 0.0), 1.0)
    weights = []
    for bar in bars:
        factor_rows = (bar.get("datasets") or {{}}).get("factor_values") or {{}}
        factor_row = factor_rows.get("replace_with_exported_factor_id") or {{}}
        value = factor_row.get(FACTOR_VALUE_FIELD)
        weights.append(position_size if value is not None and float(value) > threshold else 0.0)
    return weights
'''


def _moving_average_source(dataset_ids: tuple[str, ...]) -> str:
    return f'''DATASET_REQUIREMENTS = {list(dataset_ids)!r}

def generate_target_weights(bars, parameters):
    short_window = max(1, int(parameters.get("short_window", 5)))
    long_window = max(short_window + 1, int(parameters.get("long_window", 20)))
    position_size = min(max(float(parameters.get("position_size", 1.0)), 0.0), 1.0)
    closes = [float(bar.get("close") or 0.0) for bar in bars]
    weights = []
    for index in range(len(closes)):
        if index + 1 < long_window:
            weights.append(0.0)
            continue
        short_ma = sum(closes[index - short_window + 1:index + 1]) / short_window
        long_ma = sum(closes[index - long_window + 1:index + 1]) / long_window
        weights.append(position_size if short_ma > long_ma else 0.0)
    return weights
'''


def _index_regime_source(dataset_ids: tuple[str, ...]) -> str:
    return f'''DATASET_REQUIREMENTS = {list(dataset_ids)!r}

def generate_target_weights(bars, parameters):
    window = max(2, int(parameters.get("long_window", 20)))
    position_size = min(max(float(parameters.get("position_size", 1.0)), 0.0), 1.0)
    index_closes = []
    weights = []
    for bar in bars:
        index_row = (bar.get("datasets") or {{}}).get("index_daily") or {{}}
        index_closes.append(float(index_row.get("close") or 0.0))
        if len(index_closes) < window or not index_closes[-1]:
            weights.append(0.0)
            continue
        average = sum(index_closes[-window:]) / window
        weights.append(position_size if index_closes[-1] >= average else 0.0)
    return weights
'''
