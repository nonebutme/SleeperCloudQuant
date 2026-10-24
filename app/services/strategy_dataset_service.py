"""QuantConnect-inspired read-only strategy Dataset product service."""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any, Protocol

from data_platform.data_center_catalog import DATA_LAYERS
from data_platform.dataset_examples import get_dataset_example, list_dataset_examples
from data_platform.dataset_registry import DatasetRegistry
from app.services.strategy_dataset_resolver import SUPPORTED_RUNTIME_DATASETS
from app.services.strategy_dataset_validation import validate_strategy_data_contract
from domain.dataset.product_models import DatasetExample, DatasetProduct, DatasetSchemaField


class StrategyDatasetCatalogReader(Protocol):
    def list_datasets(self) -> Sequence[Mapping[str, Any]]: ...


_STRATEGY_DATASETS = {
    "a_share_daily",
    "factor_values",
    "trade_calendar",
    "a_share_catalog",
    "corporate_actions",
    "industry_classification",
    "index_components",
}
_GOVERNANCE_DATASETS = {"quality_issues", "data_versions"}


class StrategyDatasetService:
    """Expose one governed catalog as documentation, research and strategy examples."""

    def __init__(self, catalog_reader: StrategyDatasetCatalogReader, runtime_resolver: Any | None = None) -> None:
        self._catalog_reader = catalog_reader
        self._runtime_resolver = runtime_resolver

    def list_categories(self) -> dict[str, Any]:
        products = self.list_products()["items"]
        counts: dict[str, int] = {}
        for product in products:
            layer_id = str(product.get("layer_id") or "")
            counts[layer_id] = counts.get(layer_id, 0) + 1
        return {
            "items": [
                {"layer_id": "", "name": "全部数据集", "description": "全部受治理的数据产品", "count": len(products)},
                *[
                    {
                        "layer_id": item["layer_id"],
                        "name": item["display_name"],
                        "description": item["description"],
                        "count": counts.get(item["layer_id"], 0),
                    }
                    for item in DATA_LAYERS
                ],
            ]
        }

    def list_products(
        self,
        *,
        status: str = "",
        layer_id: str = "",
        search: str = "",
        consumer_scope: str = "",
    ) -> dict[str, Any]:
        normalized_status = status.strip()
        normalized_layer = layer_id.strip().upper()
        normalized_search = search.strip().lower()
        normalized_scope = consumer_scope.strip()
        items: list[dict[str, Any]] = []
        for record in self._records():
            product = self._product(record)
            if normalized_status and product["status"] != normalized_status:
                continue
            if normalized_layer and str(product["layer_id"]).upper() != normalized_layer:
                continue
            if normalized_scope and normalized_scope not in product["consumer_scopes"]:
                continue
            haystack = " ".join(
                (
                    str(product["dataset_id"]),
                    str(product["name"]),
                    str(product["description"]),
                    str(product.get("source_name") or ""),
                )
            ).lower()
            if normalized_search and normalized_search not in haystack:
                continue
            items.append(product)
        return {
            "items": items,
            "summary": {
                "total": len(items),
                "connected": sum(item["status"] == "connected" for item in items),
                "strategy_ready": sum(item["strategy_access"] == "executable" for item in items),
                "template_only": sum(item["strategy_access"] == "template_only" for item in items),
                "catalog_authority": "data_center",
                "write_capability": False,
            },
        }

    def get_product(self, dataset_id: str) -> dict[str, Any]:
        normalized = dataset_id.strip()
        record = next(
            (item for item in self._records() if str(item.get("dataset_id") or "") == normalized),
            None,
        )
        if record is None:
            raise KeyError(f"unknown dataset_id: {dataset_id}")
        product = self._product(record)
        examples = [asdict(item) for item in list_dataset_examples(normalized)]
        product.update(
            {
                "about": self._about(product),
                "documentation": self._documentation(product, examples),
                "examples": examples,
                "research": self.get_research(normalized),
            }
        )
        return product

    def get_research(self, dataset_id: str) -> dict[str, Any]:
        self._require_definition(dataset_id)
        version = self._version_context(dataset_id)
        example = next(
            (asdict(item) for item in list_dataset_examples(dataset_id) if item.kind == "research"),
            None,
        )
        return {
            "dataset_id": dataset_id,
            "version": version,
            "profile": {
                "member_count": len(version.get("members") or []),
                "coverage_start": version.get("coverage_start"),
                "coverage_end": version.get("coverage_end"),
                "symbol_count": version.get("symbol_count"),
                "row_count": version.get("row_count"),
                "quality_status": version.get("quality_status", "unknown"),
            },
            "recipe": example,
            "execution_boundary": "read_only_published_snapshot",
        }

    def list_examples(self, dataset_id: str) -> dict[str, Any]:
        self._require_definition(dataset_id)
        items = [asdict(item) for item in list_dataset_examples(dataset_id)]
        return {"dataset_id": dataset_id, "items": items, "total": len(items)}

    def get_example(self, dataset_id: str, example_id: str) -> dict[str, Any]:
        self._require_definition(dataset_id)
        return asdict(get_dataset_example(dataset_id, example_id))

    def preview(
        self,
        dataset_id: str,
        *,
        symbol: str = "000001.XSHE",
        start_date: str = "",
        end_date: str = "",
        adjustment: str = "raw",
        limit: int = 100,
    ) -> dict[str, Any]:
        self._require_definition(dataset_id)
        if self._runtime_resolver is None:
            raise RuntimeError("dataset preview resolver is not configured")
        return self._runtime_resolver.preview(
            dataset_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjustment=adjustment,
            limit=limit,
        )

    def validate_requirements(self, source_code: str, dataset_ids: Sequence[str] = ()) -> dict[str, Any]:
        result = validate_strategy_data_contract(
            source_code,
            dataset_ids=list(dataset_ids) or None,
            registry=self._registry(),
        )
        products = {item["dataset_id"]: item for item in self.list_products()["items"]}
        runtime = [
            {
                "dataset_id": dataset_id,
                "strategy_access": products.get(dataset_id, {}).get("strategy_access", "not_available"),
            }
            for dataset_id in result["requirements"]["dataset_ids"]
        ]
        result["runtime"] = runtime
        indicator_ids = result["requirements"].get("indicator_ids", [])
        if indicator_ids:
            try:
                if self._runtime_resolver is None:
                    raise ValueError("指标库未接入策略解析器")
                self._runtime_resolver.validate_indicator_configs(indicator_ids)
            except (ValueError, RuntimeError) as error:
                result["issues"].append({"code":"indicator_config_unavailable", "message":str(error)})
                result["ok"] = False
        result["runtime_ready"] = result["ok"] and all(
            item["strategy_access"] == "executable" for item in runtime
        )
        return result

    def instantiate_example(self, dataset_id: str, example_id: str) -> dict[str, Any]:
        example = get_dataset_example(dataset_id, example_id)
        if example.kind != "strategy":
            raise ValueError("only strategy examples can be instantiated")
        validation = self._validate_example(example)
        strategy_id = re.sub(r"[^0-9A-Za-z_]+", "_", example.example_id).strip("_").lower()
        source_sha256 = hashlib.sha256(example.source_code.encode("utf-8")).hexdigest()
        requirements = []
        registry = self._registry()
        for required_dataset_id in example.dataset_ids:
            definition = registry.require(required_dataset_id)
            fields = example.required_fields if required_dataset_id == dataset_id else tuple(
                field.name for field in definition.fields
            )
            requirements.append(
                {
                    "dataset_id": required_dataset_id,
                    "required_fields": list(fields),
                    "minimum_history": 20 if required_dataset_id == "a_share_daily" else 0,
                    "adjustment": "qfq" if required_dataset_id == "a_share_daily" else None,
                    "point_in_time_required": True,
                    "missing_data_policy": "unavailable",
                    "version_policy": "global_default_or_explicit_immutable",
                }
            )
        return {
            "example": asdict(example),
            "strategy_draft": {
                "strategy_id": strategy_id,
                "name": example.title,
                "category": "数据集策略",
                "description": example.description,
                "source_code": example.source_code,
                "source_sha256": source_sha256,
                "parameters": dict(example.parameters),
                "assets": dict(example.assets),
                "dataset_requirements": requirements,
                "execution_contract": example.execution_contract,
                "runtime_status": example.runtime_status,
                "example_id": example.example_id,
                "example_version": example.example_version,
            },
            "validation": validation,
            "writes": 0,
        }

    def _product(self, record: Mapping[str, Any]) -> dict[str, Any]:
        definition = self._registry().require(str(record.get("dataset_id") or ""))
        layer = next((item for item in DATA_LAYERS if item["layer_id"] == definition.layer_id), None)
        source = self._source_context(definition.dataset_id, record)
        scopes = self._consumer_scopes(definition.dataset_id)
        examples = list_dataset_examples(definition.dataset_id)
        readiness = self._runtime_readiness(definition.dataset_id)
        product = DatasetProduct(
            dataset_id=definition.dataset_id,
            name=definition.name,
            layer_id=definition.layer_id,
            category_name=str((layer or {}).get("display_name") or definition.layer_id),
            description=definition.description,
            producer_type=str(record.get("producer_type") or "external_source"),
            producer_id=str(source.get("source_id") or record.get("producer_id") or ""),
            market_scope=("CN",),
            asset_types=definition.security_types,
            frequencies=(definition.frequency,),
            supported_adjustments=definition.supported_adjustments,
            point_in_time_policy=definition.point_in_time_policy,
            fields=tuple(
                DatasetSchemaField(
                    name=field.name,
                    data_type=field.data_type,
                    description=field.description,
                    unit=field.unit,
                    nullable=field.nullable,
                )
                for field in definition.fields
            ),
            consumer_scopes=scopes,
            strategy_access=self._strategy_access(definition.dataset_id, definition.availability_status, readiness),
            status=definition.availability_status,
            schema_version=definition.schema_version,
        )
        view = asdict(product)
        view.update(
            {
                "source_name": source.get("display_name") or source.get("source_id") or "内部规范数据",
                "upstream_name": source.get("upstream_name") or "现有受控数据路由",
                "schema_status": "available" if product.fields else "metadata_pending",
                "has_documentation": bool(product.fields),
                "has_research": any(item.kind == "research" for item in examples),
                "example_count": len(examples),
                "published_version": self._version_context(definition.dataset_id),
                "catalog_authority": "data_center",
                "readiness": readiness,
            }
        )
        return view

    def _records(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._catalog_reader.list_datasets()]

    def _registry(self) -> DatasetRegistry:
        return DatasetRegistry(self._records())

    def _require_definition(self, dataset_id: str):
        return self._registry().require(dataset_id)

    def _source_context(self, dataset_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
        routes = []
        if hasattr(self._catalog_reader, "list_routes"):
            routes = [
                dict(item)
                for item in self._catalog_reader.list_routes()
                if str(item.get("dataset_id") or "") == dataset_id and bool(item.get("enabled", True))
            ]
        source_id = str((routes[0] if routes else {}).get("source_id") or record.get("producer_id") or "")
        if source_id and hasattr(self._catalog_reader, "get_source"):
            try:
                return dict(self._catalog_reader.get_source(source_id))
            except KeyError:
                pass
        return {"source_id": source_id, "display_name": source_id}

    def _version_context(self, dataset_id: str) -> dict[str, Any]:
        if not hasattr(self._catalog_reader, "list_versions"):
            return {"status": "unavailable", "reason": "version_reader_not_configured", "members": []}
        versions = dict(self._catalog_reader.list_versions())
        version = dict(versions.get("default_version") or {})
        version_id = str(versions.get("default_version_id") or "")
        members: list[dict[str, Any]] = []
        if version_id and hasattr(self._catalog_reader, "list_assets"):
            assets = dict(self._catalog_reader.list_assets(version_id=version_id))
            members = [
                dict(item)
                for item in assets.get("items") or []
                if str(item.get("dataset") or item.get("dataset_id") or "") == dataset_id
            ]
        coverage_starts = [str(item.get("coverage_start") or "") for item in members if item.get("coverage_start")]
        coverage_ends = [str(item.get("coverage_end") or "") for item in members if item.get("coverage_end")]
        return {
            "status": version.get("status") or ("published" if version_id else "unavailable"),
            "version_id": version_id or None,
            "as_of_trade_date": version.get("as_of_trade_date"),
            "quality_report_id": version.get("quality_report_id"),
            "coverage_start": min(coverage_starts) if coverage_starts else None,
            "coverage_end": max(coverage_ends) if coverage_ends else version.get("as_of_trade_date"),
            "symbol_count": max((int(item.get("symbol_count") or 0) for item in members), default=None),
            "row_count": sum(int(item.get("row_count") or 0) for item in members) or None,
            "quality_status": "published" if version_id else "unavailable",
            "members": members,
        }

    @staticmethod
    def _consumer_scopes(dataset_id: str) -> tuple[str, ...]:
        if dataset_id in _GOVERNANCE_DATASETS:
            return ("governance", "data_browser")
        return ("strategy", "factor_research", "data_browser")

    def _runtime_readiness(self, dataset_id: str) -> dict[str, Any]:
        if self._runtime_resolver is not None and hasattr(self._runtime_resolver, "dataset_readiness"):
            return dict(self._runtime_resolver.dataset_readiness(dataset_id))
        return {
            "integration_status": "connected",
            "data_readiness": "unknown",
            "consumer_access": "catalog_policy",
            "reason": "runtime_readiness_not_configured",
        }

    @staticmethod
    def _strategy_access(
        dataset_id: str, availability_status: str, readiness: Mapping[str, Any]
    ) -> str:
        resolved = str(readiness.get("consumer_access") or "")
        if resolved in {"executable", "template_only", "not_available"}:
            return resolved
        if dataset_id in SUPPORTED_RUNTIME_DATASETS and availability_status == "connected":
            return "executable"
        if dataset_id not in _GOVERNANCE_DATASETS and availability_status == "connected":
            return "template_only"
        return "not_available"
    @staticmethod
    def _about(product: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "introduction": product.get("description"),
            "provider": {
                "name": product.get("source_name"),
                "upstream_name": product.get("upstream_name"),
                "license_scope": product.get("license_scope"),
            },
            "data_summary": {
                "market_scope": product.get("market_scope"),
                "asset_types": product.get("asset_types"),
                "frequencies": product.get("frequencies"),
                "adjustments": product.get("supported_adjustments"),
                "point_in_time_policy": product.get("point_in_time_policy"),
            },
            "applications": [
                "作为策略或因子研究的受治理输入",
                "通过 Published 数据版本保证历史研究可复现",
                "在缺少字段或覆盖不足时显式阻断而不是填入演示值",
            ],
        }

    @staticmethod
    def _documentation(product: Mapping[str, Any], examples: list[dict[str, Any]]) -> dict[str, Any]:
        getting_started = next((item for item in examples if item["kind"] == "getting_started"), None)
        return {
            "getting_started": getting_started,
            "request_contract": {
                "dataset_id": product.get("dataset_id"),
                "fields": [item["name"] for item in product.get("fields") or []],
                "supported_adjustments": product.get("supported_adjustments"),
                "version_policy": "global_default_or_explicit_immutable",
                "missing_data_policy": "unavailable",
            },
            "execution_contract": "target-weights-v1",
            "security_boundary": "no_network_no_filesystem_no_direct_database",
        }

    @staticmethod
    def _validate_example(example: DatasetExample) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        try:
            tree = ast.parse(example.source_code)
        except SyntaxError as error:
            return {"ok": False, "issues": [{"code": "syntax_error", "message": str(error)}]}
        entrypoint = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "generate_target_weights"
            ),
            None,
        )
        if entrypoint is None or len(entrypoint.args.args) != 2:
            issues.append({"code": "entrypoint_invalid", "message": "缺少 generate_target_weights(bars, parameters)"})
        if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
            issues.append({"code": "import_forbidden", "message": "示例策略不得导入模块"})
        return {
            "ok": not issues,
            "status": "valid" if not issues else "invalid",
            "issues": issues,
            "execution_contract": example.execution_contract,
            "runtime_status": example.runtime_status,
        }
