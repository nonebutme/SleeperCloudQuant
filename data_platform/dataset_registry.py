"""Read-only adapter from the governed data-center catalog to dataset contracts."""

from __future__ import annotations

from collections.abc import Iterable

from data_platform.data_center_catalog import DATASET_CATALOG
from domain.dataset import DatasetDefinition, DatasetField


_COMMON_FIELDS: dict[str, tuple[DatasetField, ...]] = {
    "a_share_daily": (
        DatasetField("symbol", "string", "证券代码", nullable=False),
        DatasetField("trade_date", "date", "交易日", nullable=False),
        DatasetField("open", "number", "开盘价"),
        DatasetField("high", "number", "最高价"),
        DatasetField("low", "number", "最低价"),
        DatasetField("close", "number", "收盘价"),
        DatasetField("volume", "number", "成交量"),
        DatasetField("amount", "number", "成交额"),
    ),
    "a_share_catalog": (
        DatasetField("symbol", "string", "\u8bc1\u5238\u4ee3\u7801", nullable=False),
        DatasetField("name", "string", "\u8bc1\u5238\u540d\u79f0", nullable=False),
        DatasetField("market", "string", "\u6240\u5c5e\u5e02\u573a", nullable=False),
        DatasetField("listing_status", "string", "\u4e0a\u5e02\u72b6\u6001", nullable=False),
    ),
    "corporate_actions": (
        DatasetField("symbol", "string", "\u8bc1\u5238\u4ee3\u7801", nullable=False),
        DatasetField("event_date", "date", "\u516c\u53f8\u884c\u52a8\u65e5\u671f", nullable=False),
        DatasetField("event_type", "string", "\u516c\u53f8\u884c\u52a8\u7c7b\u578b", nullable=False),
        DatasetField("available_at", "datetime", "\u4fe1\u606f\u53ef\u7528\u65f6\u95f4", nullable=False),
        DatasetField("source_url", "string", "\u6765\u6e90\u94fe\u63a5"),
    ),
    "index_components": (
        DatasetField("index_code", "string", "\u6307\u6570\u4ee3\u7801", nullable=False),
        DatasetField("symbol", "string", "\u8bc1\u5238\u4ee3\u7801", nullable=False),
        DatasetField("valid_from", "date", "\u751f\u6548\u65e5\u671f", nullable=False),
        DatasetField("valid_to", "date", "\u5931\u6548\u65e5\u671f"),
    ),
    "index_daily": (
        DatasetField("symbol", "string", "指数代码", nullable=False),
        DatasetField("trade_date", "date", "交易日", nullable=False),
        DatasetField("close", "number", "收盘点位"),
        DatasetField("volume", "number", "成交量"),
        DatasetField("amount", "number", "成交额"),
    ),
    "trade_calendar": (
        DatasetField("trade_date", "date", "交易日", nullable=False),
        DatasetField("is_open", "boolean", "是否开市", nullable=False),
    ),
    "trading_status": (
        DatasetField("symbol", "string", "证券代码", nullable=False),
        DatasetField("trade_date", "date", "交易日", nullable=False),
        DatasetField("status", "string", "交易状态", nullable=False),
        DatasetField("is_tradable", "boolean", "是否可交易"),
        DatasetField("suspension_reason", "string", "停牌原因"),
        DatasetField("expected_resume_date", "date", "预计复牌日"),
    ),
    "industry_classification": (
        DatasetField("symbol", "string", "证券代码", nullable=False),
        DatasetField("industry_code", "string", "行业代码", nullable=False),
        DatasetField("industry_name", "string", "行业名称", nullable=False),
        DatasetField("valid_from", "date", "分类生效日", nullable=False),
        DatasetField("valid_to", "date", "分类失效日"),
    ),
    "events": (
        DatasetField("symbol", "string", "证券代码", nullable=False),
        DatasetField("event_date", "date", "事件日期", nullable=False),
        DatasetField("event_type", "string", "事件类型", nullable=False),
        DatasetField("source_url", "string", "来源链接"),
    ),
}


class DatasetRegistry:
    """Resolve governed catalog records without changing the existing catalog."""

    def __init__(self, records: Iterable[dict[str, object]] = DATASET_CATALOG) -> None:
        self._definitions = {
            str(record["dataset_id"]): self._to_definition(record)
            for record in records
        }

    def list(self, *, status: str | None = None) -> list[DatasetDefinition]:
        """List definitions in stable catalog order, optionally filtered by status."""

        values = list(self._definitions.values())
        if status is not None:
            values = [item for item in values if item.availability_status == status]
        return values

    def get(self, dataset_id: str) -> DatasetDefinition | None:
        return self._definitions.get(str(dataset_id).strip())

    def require(self, dataset_id: str) -> DatasetDefinition:
        definition = self.get(dataset_id)
        if definition is None:
            raise KeyError(f"unknown dataset_id: {dataset_id}")
        return definition

    def _to_definition(self, record: dict[str, object]) -> DatasetDefinition:
        dataset_id = str(record.get("dataset_id") or "")
        return DatasetDefinition(
            dataset_id=dataset_id,
            name=str(record.get("display_name") or dataset_id),
            layer_id=str(record.get("layer_id") or ""),
            description=str(record.get("description") or ""),
            frequency="daily",
            security_types=("equity",) if dataset_id.startswith("a_share") else (),
            supported_adjustments=("raw", "qfq", "hfq") if dataset_id == "a_share_daily" else (),
            fields=_COMMON_FIELDS.get(dataset_id, ()),
            source_id=(str(record.get("producer_id") or "") or None),
            availability_status=str(record.get("availability_status") or "unavailable"),
            point_in_time_policy=(
                "as_of_trade_date"
                if dataset_id in {"a_share_catalog", "corporate_actions", "industry_classification", "industry_classification_repair", "index_components"}
                else "not_applicable"
            ),
            schema_version=str(record.get("schema_version") or "v1"),
        )

