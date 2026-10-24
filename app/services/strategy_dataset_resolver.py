"""Resolve declared strategy datasets into point-in-time bar attachments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from data_platform.maintenance_transaction import guarded_research

from app.services.strategy_dataset_validation import validate_strategy_data_contract
from app.services.strategy_research_preflight import (
    parse_strategy_dataset_contracts,
    require_strategy_runtime_adjustment,
    validate_prepared_research_window,
)

SUPPORTED_RUNTIME_DATASETS = frozenset({
    "a_share_daily",
    "index_daily",
    "a_share_catalog",
    "trade_calendar",
    "trading_status",
    "corporate_actions",
    "factor_values",
    "indicator_values",
})


class IndexDatasetReader(Protocol):
    def fetch_index_price_history(
        self,
        index_symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]: ...


class StrategyDatasetResolver:
    """Attach supported governed datasets without changing target-weights-v1."""

    def __init__(
        self,
        index_reader: IndexDatasetReader,
        market_reader: Any | None = None,
        factor_store: Any | None = None,
        indicator_service: Any | None = None,
    ) -> None:
        self._index_reader = index_reader
        self._market_reader = market_reader
        self._factor_store = factor_store
        self._indicators = indicator_service
        self._maintenance_database_path = getattr(indicator_service, 'market_path', None)

    def validate_indicator_configs(self, config_ids):
        for config_id in config_ids:
            if self._indicators is None:
                raise RuntimeError("指标库未接入策略解析器")
            self._indicators.get_config(config_id)

    def freeze_parameters(
        self, source_code: str, parameters: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Validate and freeze explicitly supplied immutable factor artifacts."""

        validation = validate_strategy_data_contract(source_code)
        if not validation["ok"]:
            raise ValueError(f"strategy dataset requirements are invalid: {validation['issues']}")
        result = dict(parameters)
        self.validate_indicator_configs(validation["requirements"].get("indicator_ids", []))
        requested = dict(result.get("factor_artifacts") or {})
        frozen: dict[str, str] = {}
        for factor_id in validation["requirements"]["factor_ids"]:
            if self._factor_store is None:
                raise RuntimeError("factor artifact store is not configured")
            explicit = str(requested.get(factor_id) or "") or None
            if explicit is None:
                raise RuntimeError(f"factor artifact binding is required: {factor_id}")
            artifact = dict(self._factor_store.resolve_artifact(factor_id, explicit))
            if artifact.get("status") != "ready":
                raise RuntimeError(
                    f"factor artifact unavailable: {factor_id}:{artifact.get('reason') or 'not_found'}"
                )
            require_registration = getattr(
                self._factor_store, "require_artifact_registration", None
            )
            if callable(require_registration):
                try:
                    require_registration(str(artifact.get("artifact_id") or explicit))
                except ValueError as error:
                    raise RuntimeError(
                        f"factor artifact is not approved and registered: {factor_id}:{explicit}"
                    ) from error
            if self._indicators is not None:
                self._indicators.require_factor_registration(artifact)
            frozen[factor_id] = str(artifact["artifact_id"])
        if frozen:
            result["factor_artifacts"] = frozen
        return result

    def dataset_readiness(self, dataset_id: str) -> dict[str, Any]:
        """Separate integration state from current data and consumer readiness."""

        if dataset_id == "indicator_values":
            configured = self._indicators is not None and any(
                item["enabled"] for item in self._indicators.list_configs()["items"]
            )
            return {
                "integration_status": "connected" if self._indicators else "unavailable",
                "data_readiness": "registered_compute_on_demand" if configured else "empty",
                "consumer_access": "executable" if configured else "not_available",
                "reason": "" if configured else "no_registered_indicator",
            }

        if dataset_id == "factor_values":
            artifacts = (
                self._factor_store.list_artifacts(limit=1)
                if self._factor_store is not None else []
            )
            ready = any(
                str(item.get("status") or "") == "ready"
                and str(
                    item.get("governance", {}).get("registration_status") or ""
                ) == "registered"
                for item in artifacts
            )
            return {
                "integration_status": (
                    "connected" if self._factor_store is not None else "unavailable"
                ),
                "data_readiness": "ready" if ready else "empty",
                "consumer_access": "executable" if ready else "not_available",
                "reason": "" if ready else "no_ready_factor_artifact",
            }

        if dataset_id == "index_components":
            coverage = (
                self._index_reader.index_component_coverage()
                if hasattr(self._index_reader, "index_component_coverage") else {}
            )
            items = list(coverage.get("items") or [])
            ready = any(
                int(item.get("interval_count") or item.get("row_count") or 0) > 0
                for item in items
            )
            return {
                "integration_status": "connected",
                "data_readiness": "ready" if ready else "empty",
                "consumer_access": "template_only" if ready else "not_available",
                "reason": "" if ready else "index_component_facts_unavailable",
            }

        if dataset_id == "a_share_catalog" and self._market_reader is not None:
            coverage_reader = getattr(
                self._market_reader, "security_master_history_coverage", None
            )
            coverage = dict(coverage_reader()) if callable(coverage_reader) else {}
            has_candidate = int(coverage.get("interval_count") or 0) > 0
            ready = coverage.get("published_binding_status") == "bound"
            return {
                "integration_status": "connected",
                "data_readiness": (
                    "ready" if ready else ("candidate" if has_candidate else "empty")
                ),
                "consumer_access": "executable" if ready else "not_available",
                "reason": "" if ready else (
                    "point_in_time_security_master_not_published"
                    if has_candidate else "point_in_time_security_master_unavailable"
                ),
                "data_version_id": coverage.get("data_version_id"),
                "coverage": coverage,
            }

        return {
            "integration_status": "connected",
            "data_readiness": "catalog_declared",
            "consumer_access": "catalog_policy",
            "reason": "",
        }

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
        bounded_limit = min(max(int(limit), 1), 200)
        if dataset_id == "a_share_daily" and self._market_reader is not None:
            rows = self._market_reader.fetch_price_history(
                symbol, start_date, end_date, adjustment=adjustment
            )
        elif dataset_id == "index_daily":
            rows = self._index_reader.fetch_index_price_history(
                symbol or "000300.XSHG", start_date=start_date or None, end_date=end_date or None
            )
        elif dataset_id == "a_share_catalog" and self._market_reader is not None:
            history_reader = getattr(self._market_reader, "fetch_symbol_history", None)
            if callable(history_reader) and (start_date or end_date):
                rows = history_reader(symbol, start_date or None, end_date or None)
            else:
                item = self._market_reader.fetch_symbol(symbol)
                rows = [item] if item else []
        elif dataset_id == "trade_calendar":
            rows = self._index_reader.fetch_trade_calendar(start_date or None, end_date or None)
        elif dataset_id == "trading_status":
            rows = self._index_reader.fetch_trading_status_history(
                symbol, start_date=start_date or None, end_date=end_date or None
            )
        elif dataset_id == "corporate_actions":
            rows = self._index_reader.fetch_corporate_action_history(
                symbol, start_date=start_date or None, end_date=end_date or None
            )
        elif dataset_id == "indicator_values" and self._indicators is not None:
            rows = self._indicators.list_configs()['items']
        elif dataset_id == "factor_values" and self._factor_store is not None:
            rows = self._factor_store.list_artifacts(limit=bounded_limit)
        else:
            raise RuntimeError(f"dataset preview adapter is unavailable: {dataset_id}")
        normalized = [dict(row) for row in rows[:bounded_limit]]
        return {
            "dataset_id": dataset_id,
            "status": "ready",
            "read_only": True,
            "rows": normalized,
            "row_count": len(normalized),
            "limit": bounded_limit,
        }

    @guarded_research
    def resolve(
        self,
        source_code: str,
        bars: Sequence[Mapping[str, Any]],
        parameters: Mapping[str, Any],
        run_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        validation = validate_strategy_data_contract(source_code)
        if not validation["ok"]:
            raise ValueError(f"strategy dataset requirements are invalid: {validation['issues']}")
        dataset_ids = list(validation["requirements"]["dataset_ids"])
        strict_contracts = (
            parse_strategy_dataset_contracts(source_code)
            if validation.get("strict_contract") is not None
            else ()
        )
        coverage_modes = {item.dataset_id: item.coverage_mode for item in strict_contracts}
        context = dict(run_context or {})
        adjustment_binding = require_strategy_runtime_adjustment(
            source_code,
            str(context.get("adjustment") or parameters.get("adjustment") or ""),
        )
        data_version_id = str(
            context.get("data_version_id")
            or context.get("data_version")
            or ""
        )
        normalized = [dict(row) for row in bars]
        evidence: list[dict[str, Any]] = []
        if adjustment_binding is not None:
            evidence.append(dict(adjustment_binding))
        for dataset_id in dataset_ids:
            if dataset_id == "indicator_values":
                self._attach_indicators(normalized, parameters, context, validation, evidence)
                continue
            if dataset_id == "a_share_daily":
                for row in normalized:
                    row.setdefault("datasets", {})[dataset_id] = dict(row)
                evidence.append({"dataset_id": dataset_id, "status": "bound", "mode": "base_bars"})
                continue
            if dataset_id == "index_daily":
                self._attach_index_daily(normalized, parameters, evidence)
                continue
            if dataset_id == "a_share_catalog":
                if coverage_modes.get(dataset_id) == "as_of_trade_date":
                    if not data_version_id:
                        raise RuntimeError(
                            "point_in_time_a_share_catalog_requires_data_version"
                        )
                    self._attach_catalog_point_in_time(
                        normalized,
                        evidence,
                        data_version_id=data_version_id,
                    )
                else:
                    self._attach_catalog(normalized, evidence)
                continue
            if dataset_id == "trade_calendar":
                self._attach_trade_calendar(normalized, evidence)
                continue
            if dataset_id == "trading_status":
                self._attach_trading_status(normalized, evidence)
                continue
            if dataset_id == "corporate_actions":
                self._attach_corporate_actions(normalized, evidence)
                continue
            if dataset_id == "factor_values":
                factor_contract = next(
                    (item for item in strict_contracts if item.dataset_id == "factor_values"),
                    None,
                )
                self._attach_factor_values(
                    normalized,
                    parameters,
                    validation,
                    evidence,
                    evaluation_start_date=str(context.get("evaluation_start_date") or "")[:10],
                    evaluation_end_date=str(context.get("evaluation_end_date") or "")[:10],
                    required_warmup_rows=max(
                        0, int(getattr(factor_contract, "minimum_history", 1) or 1) - 1
                    ),
                    decision_minimum_rows=max(
                        (
                            int(item.minimum_history or 0)
                            for item in strict_contracts
                            if item.dataset_id == "a_share_daily"
                        ),
                        default=0,
                    ),
                    data_version_id=data_version_id,
                )
                continue
            raise RuntimeError(f"dataset runtime adapter is unavailable: {dataset_id}")
        research_window = None
        if validation.get("strict_contract") is not None:
            evaluation_start = str(context.get("evaluation_start_date") or "")[:10]
            evaluation_end = str(context.get("evaluation_end_date") or "")[:10]
            if not evaluation_start or not evaluation_end:
                raise RuntimeError("strict strategy contract requires an explicit evaluation window")
            research_window = validate_prepared_research_window(
                normalized,
                evaluation_start_date=evaluation_start,
                evaluation_end_date=evaluation_end,
                contracts=strict_contracts,
            )
            if not research_window["ok"]:
                raise RuntimeError(
                    f"strategy research window preflight failed: {research_window['issues']}"
                )
            evidence.append(
                {
                    "dataset_id": "research_window",
                    "status": "bound",
                    "mode": "warmup_separated_from_evaluation",
                    "warmup_rows": research_window["warmup"]["row_count"],
                    "evaluation_rows": research_window["evaluation"]["row_count"],
                }
            )
        return {
            "bars": normalized,
            "evidence": evidence,
            "validation": validation,
            "research_window": research_window,
        }

    def _attach_indicators(self, bars, parameters, context, validation, evidence):
        if self._indicators is None:
            raise RuntimeError("指标库未接入策略解析器")
        if not bars:
            return
        adjustment = str(context.get('adjustment') or parameters.get('adjustment') or '')
        version = str(context.get('data_version_id') or context.get('data_version') or '')
        groups = {}
        for row in bars:
            symbol = str(row.get('symbol') or context.get('symbol') or parameters.get('symbol') or '')
            groups.setdefault(symbol, []).append(row)
        for config_id in validation['requirements']['indicator_ids']:
            config = self._indicators.get_config(config_id)
            if not adjustment or adjustment != config['adjustment']:
                raise ValueError("策略运行复权口径与指标注册配置不一致")
            for symbol, group in groups.items():
                dates = [str(r.get('date') or r.get('trade_date') or '')[:10] for r in group]
                result = self._indicators.values(config_id, symbol=symbol, start_date=min(dates), end_date=max(dates),
                                                  limit=None, expected_version=version)
                mapping = {r['trade_date']:r for r in result['rows']}
                for row, day in zip(group, dates):
                    value = mapping.get(day)
                    if value is None or value['status'] != 'ready':
                        raise ValueError(f"指标 {config_id} 在 {symbol}/{day} 预热不足或输入不可用")
                    for field, expected in value['source_values'].items():
                        if field in row and row[field] != expected:
                            raise ValueError("策略行情与指标计算输入不一致")
                    dataset = row.setdefault('datasets',{}).setdefault('indicator_values',
                        {'items':{}, 'trade_date':day, 'available_at':value['available_at'], 'status':'ready'})
                    dataset['items'][config_id] = value
                evidence.append({'dataset_id':'indicator_values','config_id':config_id,'symbol':symbol,
                    'data_version_id':result['data_version_id'],'input_hash':result['input_hash'],
                    'definition_hash':config['definition_hash'],'status':'bound','mode':'canonical_prefix_causal'})

    def _attach_factor_values(
        self,
        bars: list[dict[str, Any]],
        parameters: Mapping[str, Any],
        validation: Mapping[str, Any],
        evidence: list[dict[str, Any]],
        *,
        evaluation_start_date: str = "",
        evaluation_end_date: str = "",
        required_warmup_rows: int = 0,
        decision_minimum_rows: int = 0,
        data_version_id: str = "",
    ) -> None:
        if self._factor_store is None:
            raise RuntimeError("factor artifact store is not configured")
        bindings = dict(parameters.get("factor_artifacts") or {})
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        evaluation_dates = [
            item
            for item in dates
            if evaluation_start_date <= item <= evaluation_end_date
        ] if evaluation_start_date and evaluation_end_date else []
        warmup_dates = [item for item in dates if item < evaluation_start_date]
        required_dates = set(evaluation_dates)
        if required_warmup_rows:
            required_dates.update(warmup_dates[-required_warmup_rows:])
        symbol = _bar_symbol(bars)
        for factor_id in validation["requirements"]["factor_ids"]:
            artifact_id = str(bindings.get(factor_id) or "")
            if not artifact_id:
                raise RuntimeError(f"factor artifact binding is not frozen: {factor_id}")
            artifact = dict(self._factor_store.resolve_artifact(factor_id, artifact_id))
            if self._indicators is not None:
                self._indicators.require_factor_registration(artifact)
            if artifact.get("status") != "ready":
                raise RuntimeError(f"factor artifact unavailable: {factor_id}:{artifact_id}")
            artifact_data_version_id = str(artifact.get("data_version_id") or "")
            if data_version_id and artifact_data_version_id != data_version_id:
                raise RuntimeError(
                    f"factor artifact data version mismatch for {factor_id}: "
                    f"artifact={artifact_data_version_id or 'missing'} run={data_version_id}"
                )
            rows = self._factor_store.fetch_artifact_values(
                artifact_id, symbol=symbol,
                start_date=min(dates) if dates else "",
                end_date=max(dates) if dates else "",
            )
            by_date = {str(row["trade_date"]): dict(row) for row in rows}
            matched = 0
            required = 0
            required_matched = 0
            ineligible_rows = 0
            missing_required_dates: list[str] = []
            for row_index, bar in enumerate(bars):
                trade_date = _bar_date(bar)
                value = by_date.get(trade_date)
                bar.setdefault("datasets", {}).setdefault("factor_values", {})[factor_id] = (
                    {"factor_id": factor_id, "artifact_id": artifact_id,
                     "value": value.get("value"), "aligned_value": value.get("aligned_value")}
                    if value is not None else None
                )
                matched += value is not None
                decision_eligible = _factor_value_required_for_bar(
                    bar,
                    row_index=row_index,
                    decision_minimum_rows=decision_minimum_rows,
                )
                if trade_date in required_dates and decision_eligible:
                    required += 1
                    required_matched += value is not None
                    if value is None:
                        missing_required_dates.append(trade_date)
                elif trade_date in required_dates:
                    ineligible_rows += 1
            if not evaluation_start_date or not evaluation_end_date:
                required_rows = [
                    bar for row_index, bar in enumerate(bars)
                    if _factor_value_required_for_bar(
                        bar,
                        row_index=row_index,
                        decision_minimum_rows=decision_minimum_rows,
                    )
                ]
                required = len(required_rows)
                required_matched = sum(
                    by_date.get(_bar_date(bar)) is not None for bar in required_rows
                )
                ineligible_rows = len(bars) - required
                missing_required_dates = [
                    _bar_date(bar) for bar in required_rows
                    if by_date.get(_bar_date(bar)) is None
                ]
            evidence.append({
                "dataset_id": "factor_values", "factor_id": factor_id,
                "artifact_id": artifact_id,
                "data_version_id": artifact.get("data_version_id"),
                "quality_report_id": artifact.get("quality_report_id"),
                "status": "bound" if matched else "unavailable",
                "mode": "same_trade_date_immutable_artifact",
                "matched_rows": matched, "requested_rows": len(bars),
                "required_rows": required,
                "required_matched_rows": required_matched,
                "decision_ineligible_rows": ineligible_rows,
                "required_warmup_rows": min(required_warmup_rows, len(warmup_dates)),
                "decision_minimum_rows": decision_minimum_rows,
                "coverage_policy": (
                    "evaluation_and_declared_factor_warmup_complete"
                    if required_warmup_rows
                    else "evaluation_complete_warmup_optional"
                    if evaluation_start_date and evaluation_end_date
                    else "all_requested_rows"
                ),
            })
            if required_matched < required:
                raise RuntimeError(
                    f"factor artifact evaluation coverage is incomplete for {factor_id}: "
                    f"matched {required_matched} of {required} required rows; "
                    f"missing dates={missing_required_dates[:10]}"
                )
    def _attach_catalog(self, bars: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        symbol = _bar_symbol(bars)
        item = self._market_reader.fetch_symbol(symbol) if self._market_reader is not None else None
        if item is None:
            raise RuntimeError(f"a_share_catalog has no security-master row for {symbol}")
        for bar in bars:
            bar.setdefault("datasets", {})["a_share_catalog"] = dict(item)
        evidence.append({"dataset_id": "a_share_catalog", "status": "bound", "mode": "security_master", "symbol": symbol, "matched_rows": 1})

    def _attach_catalog_point_in_time(
        self,
        bars: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        *,
        data_version_id: str,
    ) -> None:
        symbol = _bar_symbol(bars)
        reader = getattr(self._market_reader, "fetch_symbol_history", None)
        if not callable(reader):
            raise RuntimeError(
                "point_in_time_a_share_catalog_unavailable: fetch_symbol_history adapter is required"
            )
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        rows = [
            dict(row)
            for row in reader(
                symbol,
                min(dates) if dates else None,
                max(dates) if dates else None,
                data_version_id=data_version_id,
            )
        ]
        matched = 0
        for bar in bars:
            trade_date = _bar_date(bar)
            candidates = [
                row
                for row in rows
                if str(row.get("valid_from") or "")[:10] <= trade_date
                and (
                    not str(row.get("valid_to") or "")[:10]
                    or str(row.get("valid_to") or "")[:10] >= trade_date
                )
                and str(row.get("available_at") or "")[:10] <= trade_date
            ]
            if len(candidates) != 1:
                raise RuntimeError(
                    f"point_in_time_a_share_catalog_ambiguous: {symbol} {trade_date} matched {len(candidates)} rows"
                )
            value = candidates[0]
            if value.get("risk_warning") is None or not value.get("listing_status"):
                raise RuntimeError(
                    f"point_in_time_a_share_catalog_incomplete: {symbol} {trade_date}"
                )
            bar.setdefault("datasets", {})["a_share_catalog"] = value
            matched += 1
        evidence.append(
            {
                "dataset_id": "a_share_catalog",
                "status": "bound",
                "mode": "point_in_time_security_interval",
                "symbol": symbol,
                "matched_rows": matched,
                "requested_rows": len(bars),
                "data_version_id": data_version_id,
            }
        )

    def _attach_trade_calendar(self, bars: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        rows = self._index_reader.fetch_trade_calendar(min(dates) if dates else None, max(dates) if dates else None)
        self._attach_rows_by_date(bars, "trade_calendar", rows, evidence, required=True)

    def _attach_trading_status(self, bars: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        rows = self._index_reader.fetch_trading_status_history(_bar_symbol(bars), min(dates) if dates else None, max(dates) if dates else None)
        self._attach_rows_by_date(bars, "trading_status", rows, evidence, required=True)
        for bar in bars:
            trade_date = _bar_date(bar)
            status = (bar.get("datasets") or {}).get("trading_status")
            tradable = status.get("is_tradable") if isinstance(status, Mapping) else None
            if not isinstance(tradable, bool):
                raise RuntimeError(
                    f"trading_status_value_incomplete: {_bar_symbol(bars)} {trade_date}"
                )
            try:
                volume = float(bar.get("volume") or 0.0)
            except (TypeError, ValueError):
                volume = 0.0
            if tradable is False and volume > 0:
                raise RuntimeError(
                    "trading_status_price_conflict: "
                    f"{_bar_symbol(bars)} {trade_date} is_tradable=false volume={volume}"
                )

    def _attach_corporate_actions(self, bars: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        rows = self._index_reader.fetch_corporate_action_history(_bar_symbol(bars), min(dates) if dates else None, max(dates) if dates else None)
        by_date: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_date.setdefault(_bar_date(row), []).append(dict(row))
        for bar in bars:
            bar.setdefault("datasets", {})["corporate_actions"] = by_date.get(_bar_date(bar), [])
        evidence.append({"dataset_id": "corporate_actions", "status": "bound", "mode": "announced_point_in_time_events", "matched_rows": len(rows), "requested_rows": len(bars)})

    @staticmethod
    def _attach_rows_by_date(
        bars: list[dict[str, Any]],
        dataset_id: str,
        rows: Sequence[Mapping[str, Any]],
        evidence: list[dict[str, Any]],
        *,
        required: bool,
    ) -> None:
        by_date = {_bar_date(row): dict(row) for row in rows if _bar_date(row)}
        matched = 0
        for bar in bars:
            value = by_date.get(_bar_date(bar))
            bar.setdefault("datasets", {})[dataset_id] = value
            matched += value is not None
        evidence.append({"dataset_id": dataset_id, "status": "bound" if matched else "unavailable", "mode": "point_in_time_same_trade_date", "matched_rows": matched, "requested_rows": len(bars)})
        if required and bars and matched < len(bars):
            raise RuntimeError(f"{dataset_id} coverage is incomplete: matched {matched} of {len(bars)} rows")

    def _attach_index_daily(
        self,
        bars: list[dict[str, Any]],
        parameters: Mapping[str, Any],
        evidence: list[dict[str, Any]],
    ) -> None:
        dates = [_bar_date(row) for row in bars if _bar_date(row)]
        index_symbol = str(parameters.get("index_symbol") or "000300.XSHG")
        rows = self._index_reader.fetch_index_price_history(
            index_symbol,
            start_date=min(dates) if dates else None,
            end_date=max(dates) if dates else None,
        )
        by_date = {_bar_date(row): dict(row) for row in rows if _bar_date(row)}
        matched = 0
        for bar in bars:
            value = by_date.get(_bar_date(bar))
            bar.setdefault("datasets", {})["index_daily"] = value
            matched += value is not None
        evidence.append(
            {
                "dataset_id": "index_daily",
                "status": "bound" if matched else "unavailable",
                "mode": "point_in_time_same_trade_date",
                "index_symbol": index_symbol,
                "matched_rows": matched,
                "requested_rows": len(bars),
            }
        )
        if bars and not matched:
            raise RuntimeError(f"index_daily has no rows for {index_symbol} in requested window")


def _bar_date(row: Mapping[str, Any]) -> str:
    return str(row.get("date") or row.get("trade_date") or row.get("event_date") or "")[:10]


def _bar_symbol(bars: Sequence[Mapping[str, Any]]) -> str:
    if not bars:
        return ""
    return str(bars[0].get("symbol") or bars[0].get("order_book_id") or "")


def _factor_value_required_for_bar(
    bar: Mapping[str, Any],
    *,
    row_index: int = 0,
    decision_minimum_rows: int = 0,
) -> bool:
    """Require factor coverage only when the row can enter a strategy decision.

    Governed research pools intentionally omit factor observations while a
    security is not listed, risk-warning, or not tradable.  Those omissions are
    evidence of point-in-time eligibility rather than values that may be filled.
    If an eligibility dataset is absent or incomplete, remain conservative and
    require the factor value.
    """

    if decision_minimum_rows and row_index + 1 < decision_minimum_rows:
        return False
    datasets = bar.get("datasets") or {}
    catalog = datasets.get("a_share_catalog")
    if isinstance(catalog, Mapping):
        listing_status = str(catalog.get("listing_status") or "").lower()
        if listing_status and listing_status not in {"listed", "active", "normal"}:
            return False
        if catalog.get("risk_warning") is True:
            return False
    calendar = datasets.get("trade_calendar")
    if isinstance(calendar, Mapping) and calendar.get("is_open") is False:
        return False
    trading_status = datasets.get("trading_status")
    if isinstance(trading_status, Mapping) and trading_status.get("is_tradable") is False:
        return False
    return True
