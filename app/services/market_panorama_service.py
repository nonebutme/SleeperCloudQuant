"""M4 market-panorama aggregation and free-source synchronization."""

from __future__ import annotations

import json
import math
import queue
import sqlite3
import shutil
import subprocess
import statistics
import threading
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from data_platform.providers.akshare_governance_provider import AkshareGovernanceProvider
from data_platform.providers.akshare_a_share_provider import discover_proxy_url
from data_platform.providers.akshare_ths_board_provider import AkshareThsBoardProvider
from data_platform.task_ids import new_task_id
from data_platform.providers.cninfo_controlled_provider import CninfoControlledProvider
from data_platform.storage.a_share_governance_store import AShareGovernanceStore
from data_platform.storage.market_panorama_store import MarketPanoramaStore


CORE_INDICES = (
    ("000001", "上证指数"), ("399001", "深证成指"), ("899050", "北证50"),
    ("000300", "沪深300"), ("399006", "创业板指"), ("000688", "科创50"),
)

GLOBAL_INDICES = (
    {"code": "SPX", "label": "标普500", "market": "US", "partition": "US", "endpoint": "index_us_stock_sina", "coverage": "较完整历史（上游当前可回溯至2004年）"},
    {"code": "IXIC", "label": "纳斯达克综合指数", "market": "US", "partition": "US", "endpoint": "index_us_stock_sina", "coverage": "较完整历史（上游当前可回溯至2004年）"},
    {"code": "DJI", "label": "道琼斯工业指数", "market": "US", "partition": "US", "endpoint": "index_us_stock_sina", "coverage": "较完整历史（上游当前可回溯至2004年）"},
    {"code": "NDX", "label": "纳斯达克100指数", "market": "US", "partition": "US", "endpoint": "index_us_stock_sina", "coverage": "较完整历史（上游当前可回溯至2014年）"},
    {"code": "FTSE", "label": "英国富时100指数", "market": "GB", "partition": "INTERNATIONAL", "endpoint": "index_global_hist_sina", "coverage": "仅上游最近1000条日线"},
    {"code": "GDAXI", "label": "德国DAX指数", "market": "DE", "partition": "INTERNATIONAL", "endpoint": "index_global_hist_sina", "coverage": "仅上游最近1000条日线"},
    {"code": "N225", "label": "日经225指数", "market": "JP", "partition": "INTERNATIONAL", "endpoint": "index_global_hist_sina", "coverage": "仅上游最近1000条日线"},
)

PANORAMA_DATASETS = (
    "index_daily",
    "industry_board",
    "concept_board",
    "industry_flow",
    "concept_flow",
    "events",
    "industry_classification_repair",
    "global_index_daily",
)


class MarketPanoramaService:
    """Build one honest point-in-time panorama from local governed datasets."""

    def __init__(
        self,
        store: MarketPanoramaStore,
        *,
        market_database: str | Path = "var/market/a_share_market.sqlite3",
        classification_database: str | Path = "var/runtime/a_share_classification_history.sqlite3",
        max_workers: int = 4,
        ths_board_provider: AkshareThsBoardProvider | None = None,
        cninfo_provider: CninfoControlledProvider | None = None,
    ) -> None:
        self.store = store
        self.market_database = Path(market_database)
        self.classification_database = Path(classification_database)
        self.max_workers = max(1, min(int(max_workers), 8))
        self.ths_board_provider = ths_board_provider or AkshareThsBoardProvider()
        self.cninfo_provider = cninfo_provider or CninfoControlledProvider()
        self.governance_store = AShareGovernanceStore(self.market_database)
        self.governance_provider = AkshareGovernanceProvider(retry_count=3)
        self._threads: dict[str, threading.Thread] = {}
        self._thread_lock = threading.Lock()
        self._global_route_rate_lock = threading.Lock()
        self._global_route_last_request: dict[str, float] = {}

    def get_panorama(self, *, trade_date: str, symbol: str = "", asset_type: str = "stock") -> dict[str, Any]:
        requested = str(trade_date or "")[:10]
        if not requested:
            raise ValueError("trade_date is required")
        industry = self.store.board_snapshot("industry", requested)
        if not industry["items"]:
            industry = self._local_industry_snapshot(requested)
        concept = self.store.board_snapshot("concept", requested)
        industry_flow = self.store.flow_snapshot("industry", requested)
        concept_flow = self.store.flow_snapshot("concept", requested)
        events = self.store.list_events(requested, symbol=symbol if asset_type == "stock" else "")
        sections = {
            "industry_heatmap": industry,
            "concept_heatmap": concept,
            "industry_fund_flow": industry_flow,
            "concept_fund_flow": concept_flow,
            "events": events,
        }
        ready = sum(section.get("status") in {"ready", "stale"} and bool(section.get("items")) for section in sections.values())
        unavailable = [name for name, section in sections.items() if not section.get("items")]
        effective_dates = sorted({str(section.get("effective_trade_date")) for section in sections.values() if section.get("effective_trade_date")})
        return {
            "status": "ready" if ready == len(sections) else "partial" if ready else "unavailable",
            "requested_trade_date": requested,
            "effective_trade_dates": effective_dates,
            "symbol": symbol,
            "asset_type": asset_type,
            "ready_section_count": ready,
            "section_count": len(sections),
            "unavailable_sections": unavailable,
            "sections": sections,
            "generated_at": _utc_now(),
            "methodology": {
                "industry_fallback": "qfq daily cross-section joined to point-in-time industry intervals",
                "date_policy": "each section uses latest local effective date not after requested date",
                "no_fabrication": True,
            },
        }

    def preview_job(
        self, *, datasets: Iterable[str], target_trade_date: str,
        start_trade_date: str = "", mode: str = "incremental",
        symbols: Iterable[str] = (), selected_shards: Iterable[str] = (),
    ) -> dict[str, Any]:
        normalized = self._datasets(datasets)
        if len(normalized) != 1:
            raise ValueError("stage B only allows one dataset per sync task")
        dataset = normalized[0]
        target = datetime.fromisoformat(str(target_trade_date)[:10]).date().isoformat()
        start = datetime.fromisoformat(str(start_trade_date or target)[:10]).date().isoformat()
        if start > target:
            raise ValueError("start_trade_date must not be later than target_trade_date")
        historical = mode == "historical_gap"
        symbol_list = _symbols(symbols)
        selected = {str(item).strip() for item in selected_shards if str(item).strip()}
        shards: list[dict[str, Any]] = []
        exact_gap_scan = dataset not in {
            "events", "industry_classification_repair", "global_index_daily",
        }
        coverage_strategy = (
            "exact_trading_day_gap" if exact_gap_scan else "range_backfill"
        )
        expected_dates = self._open_dates(start, target) if historical and exact_gap_scan else [target]
        if dataset == "index_daily":
            items = [{"code": code, "label": name} for code, name in CORE_INDICES]
            for item in items:
                if selected and item["code"] not in selected:
                    continue
                covered = self._index_covered_dates(item["code"], start, target)
                missing = [day for day in expected_dates if day not in covered]
                if missing:
                    shards.append(self._gap_shard(item["code"], item["label"], missing))
        elif dataset == "global_index_daily":
            global_calendar_modes: list[str] = []
            for item in GLOBAL_INDICES:
                if selected and item["code"] not in selected:
                    continue
                calendar_ready = historical and self.governance_store.global_index_calendar_covers(
                    market=str(item["market"]), start_trade_date=start,
                    target_trade_date=target,
                )
                if calendar_ready:
                    global_calendar_modes.append("market_session_gap")
                    expected = self.governance_store.global_index_calendar_dates(
                        market=str(item["market"]), start_trade_date=start,
                        target_trade_date=target,
                    )
                    covered = self._index_covered_dates(
                        str(item["code"]), start, target,
                    )
                    missing = [day for day in expected if day not in covered]
                    if missing:
                        shard = self._gap_shard(
                            str(item["code"]), str(item["label"]), missing,
                        )
                        shard.update({
                            "market": item["market"],
                            "partition": item["partition"],
                            "endpoint": item["endpoint"],
                            "coverage": item["coverage"],
                            "coverage_strategy": "market_session_gap",
                        })
                        shards.append(shard)
                else:
                    global_calendar_modes.append("range_backfill")
                    shards.append({
                        "shard_id": item["code"], "label": item["label"],
                        "market": item["market"],
                        "partition": item["partition"],
                        "start_date": start, "end_date": target,
                        "endpoint": item["endpoint"], "coverage": item["coverage"],
                        "coverage_strategy": "range_backfill",
                    })
            if global_calendar_modes and all(
                mode == "market_session_gap" for mode in global_calendar_modes
            ):
                exact_gap_scan = True
                coverage_strategy = "market_session_gap"
            elif any(mode == "market_session_gap" for mode in global_calendar_modes):
                coverage_strategy = "hybrid_market_calendar"
        elif dataset in {"industry_board", "industry_flow", "concept_board", "concept_flow"}:
            dimension = "industry" if dataset.startswith("industry") else "concept"
            catalog = self.store.list_board_catalog(dimension)
            if not catalog:
                shards = [self._gap_shard("__all__", "全部板块（首次运行将同步目录）", expected_dates)]
            else:
                for item in catalog:
                    code = str(item["board_code"])
                    if selected and code not in selected:
                        continue
                    covered = self.store.covered_dates(
                        dataset, dimension=dimension, item_key=code,
                        start_date=start, end_date=target,
                    )
                    missing = [day for day in expected_dates if day not in covered]
                    if missing:
                        shards.append(self._gap_shard(code, str(item.get("board_name") or code), missing))
        elif dataset == "events":
            if not symbol_list:
                raise ValueError("个股公告与新闻需要至少一个证券代码")
            for symbol in symbol_list:
                if not selected or symbol in selected:
                    shards.append({"shard_id": symbol, "label": symbol, "start_date": start, "end_date": target,
                                   "coverage_strategy": "range_backfill"})
        else:
            failed = self._classification_failed_symbols()
            for symbol in failed:
                if not selected or symbol in selected:
                    shards.append({"shard_id": symbol, "label": symbol, "start_date": start, "end_date": target,
                                   "coverage_strategy": "failed_symbol_range_repair"})
        missing_date_count = sum(int(item.get("missing_date_count") or 0) for item in shards)
        return {
            "status": "previewed", "dataset": dataset, "datasets": normalized,
            "mode": mode, "start_trade_date": start, "target_trade_date": target,
            "symbols": symbol_list, "symbol_scope": symbol_list or "all_items",
            "request_count": len(shards), "missing_date_count": missing_date_count,
            "coverage_strategy": coverage_strategy,
            "estimated_seconds": max(1, math.ceil(len(shards) / max(self.max_workers, 1) * 1.2)),
            "writes": 0, "shards": shards[:500], "shards_truncated": len(shards) > 500,
        }

    @staticmethod
    def _gap_shard(item_key: str, label: str, missing: list[str]) -> dict[str, Any]:
        return {
            "shard_id": item_key, "label": label,
            "start_date": missing[0], "end_date": missing[-1],
            "first_missing_date": missing[0], "last_missing_date": missing[-1],
            "missing_date_count": len(missing), "missing_dates": missing[:50],
            "missing_dates_truncated": len(missing) > 50,
        }

    def _open_dates(self, start_date: str, end_date: str) -> list[str]:
        with sqlite3.connect(f"file:{self.market_database.resolve().as_posix()}?mode=ro", uri=True, timeout=30) as connection:
            rows = connection.execute(
                """SELECT trade_date FROM market_trade_calendar
                   WHERE market='CN' AND is_open=1 AND trade_date BETWEEN ? AND ?
                   ORDER BY trade_date""", (start_date, end_date),
            ).fetchall()
        if not rows:
            raise ValueError("规范交易日历在所选日期范围内没有开放日，无法检查历史缺口")
        return [str(row[0]) for row in rows]

    def _index_covered_dates(self, symbol: str, start_date: str, end_date: str) -> set[str]:
        with sqlite3.connect(f"file:{self.market_database.resolve().as_posix()}?mode=ro", uri=True, timeout=30) as connection:
            rows = connection.execute(
                """SELECT trade_date FROM market_index_daily_prices
                   WHERE index_symbol=? AND trade_date BETWEEN ? AND ?""",
                (symbol, start_date, end_date),
            ).fetchall()
        return {str(row[0]) for row in rows}
    def create_job(
        self, *, datasets: Iterable[str], target_trade_date: str,
        start_trade_date: str = "", mode: str = "incremental",
        symbols: Iterable[str] = (), selected_shards: Iterable[str] = (),
    ) -> dict[str, Any]:
        preview = self.preview_job(
            datasets=datasets, target_trade_date=target_trade_date,
            start_trade_date=start_trade_date, mode=mode,
            symbols=symbols, selected_shards=selected_shards,
        )
        job_id = new_task_id("panorama-sync")
        task_shards = [item["shard_id"] for item in preview["shards"]]
        stored_symbols = task_shards
        job = self.store.create_job(
            job_id, preview["datasets"], preview["target_trade_date"], stored_symbols,
            mode=mode, start_trade_date=preview["start_trade_date"],
        )
        self.store.set_job_total(job_id, int(preview["request_count"]))
        return self.store.get_job(job_id)

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_jobs(limit)

    def get_job_items(self, job_id: str) -> list[dict[str, Any]]:
        return self.store.list_job_items(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job.get("status") == "not_found":
            return job
        failed_items = self.store.list_job_items(job_id, status="failed")
        payload = {**job, **self._failure_diagnostics(failed_items)}
        if "global_index_daily" in job.get("datasets", []):
            payload["global_index_release"] = (
                self.governance_store.get_global_index_release(job_id=job_id)
            )
        return payload

    @staticmethod
    def _failure_diagnostics(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"failure_summary": {"failed_item_count": 0, "groups": []}, "resolution": None}
        counts = Counter(str(item.get("error_message") or "unknown item failure") for item in items)
        groups = [
            {"error": message, "count": count}
            for message, count in counts.most_common(10)
        ]
        combined = " ".join(counts).lower()
        if "curl transport failed (56)" in combined or "failure when receiving data from the peer" in combined:
            resolution = {
                "code": "upstream_connection_interrupted",
                "title": "上游连接在接收数据时中断",
                "cause": "免费上游或当前网络在响应过程中断开连接；本地尚未写入这些失败分片。",
                "retryable": True,
                "retry_scope": "failed_items_only",
                "steps": [
                    "确认当前网络可访问数据源，并等待 1—3 分钟避开上游限流或短暂抖动。",
                    "点击“仅重试失败项”；系统只恢复失败分片，不重跑已经成功的分片。",
                    "若连续三次仍全部失败，到“数据源与路由”执行只读探测，再检查代理、防火墙或切换可用数据源。",
                ],
            }
        elif "timed out" in combined or "timeout" in combined:
            resolution = {
                "code": "upstream_timeout",
                "title": "上游响应超时",
                "cause": "上游响应速度低于当前任务等待窗口。",
                "retryable": True,
                "retry_scope": "failed_items_only",
                "steps": [
                    "等待上游恢复后点击“仅重试失败项”。",
                    "若重复超时，减少单次分片范围或到“数据源与路由”执行只读探测。",
                ],
            }
        elif "no fund-flow rows" in combined or "no board rows" in combined:
            resolution = {
                "code": "target_date_has_no_upstream_rows",
                "title": "目标日期没有可用上游记录",
                "cause": "目标日期可能不是开放交易日，或上游尚未发布对应板块数据。",
                "retryable": False,
                "retry_scope": "new_task_required",
                "steps": [
                    "核对目标日期是否为开放交易日。",
                    "改用最近开放交易日重新预检并创建任务；不要反复重试同一无数据日期。",
                ],
            }
        else:
            resolution = {
                "code": "inspect_failed_items",
                "title": "需要根据失败项处理",
                "cause": "任务包含可定位的分片错误，请先查看下方失败项和错误分组。",
                "retryable": True,
                "retry_scope": "failed_items_only",
                "steps": [
                    "查看失败原因分组和具体分片。",
                    "确认配置或数据源恢复后点击“仅重试失败项”。",
                    "若同一错误连续出现三次，到“数据源与路由”执行只读探测。",
                ],
            }
        return {
            "failure_summary": {"failed_item_count": len(items), "groups": groups},
            "resolution": resolution,
        }

    def start_job(
        self, job_id: str, *, routes: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job.get("status") == "not_found":
            return job
        with self._thread_lock:
            existing = self._threads.get(job_id)
            if existing and existing.is_alive():
                return job
            frozen_routes = None if routes is None else [dict(item) for item in routes]
            thread = threading.Thread(
                target=self.run_job, args=(job_id,), kwargs={"routes": frozen_routes},
                name=f"panorama-{job_id[-8:]}", daemon=True,
            )
            self._threads[job_id] = thread
            thread.start()
        return {**self.store.get_job(job_id), "launch": {"status": "background_started", "thread": thread.name}}

    def stop_job(self, job_id: str) -> dict[str, Any]:
        return self.store.request_stop(job_id)

    def delete_job(self, job_id: str) -> dict[str, Any]:
        with self._thread_lock:
            active = self._threads.get(job_id)
            if active is not None and active.is_alive():
                raise ValueError("running panorama task cannot be deleted")
        return self.store.delete_job(job_id)
    def retry_job(
        self, job_id: str, *, run_now: bool = False,
        routes: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.store.reset_job(job_id)
        return self.start_job(job_id, routes=routes) if run_now else self.get_job(job_id)

    def run_job(
        self, job_id: str, *, routes: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run one persisted panorama job synchronously for worker processes."""

        self._run_job(job_id, routes=routes)
        return self.get_job(job_id)
    def _run_job(
        self, job_id: str, *, routes: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        self.store.start_job(job_id)
        job = self.store.get_job(job_id)
        release_id = f"global-index-release-{job_id}"
        has_global_index = "global_index_daily" in job.get("datasets", [])
        route_plan = None if routes is None else sorted(
            (dict(item) for item in routes),
            key=lambda item: (int(item.get("priority") or 0), str(item.get("route_id") or "")),
        )
        try:
            if has_global_index:
                self.governance_store.begin_global_index_release(
                    release_id=release_id, job_id=job_id,
                    start_trade_date=job["start_trade_date"],
                    target_trade_date=job["target_trade_date"],
                )
            for dataset in job["datasets"]:
                if self.store.should_stop(job_id):
                    break
                try:
                    if dataset == "index_daily":
                        self._sync_index_daily(job_id, job["start_trade_date"], job["target_trade_date"], job["symbols"])
                    elif dataset == "global_index_daily":
                        self._sync_global_index_daily(
                            job_id, job["start_trade_date"], job["target_trade_date"],
                            job["symbols"], routes=route_plan,
                        )
                    elif dataset == "industry_board":
                        self._sync_board_dimension(job_id, "industry", job["start_trade_date"], job["target_trade_date"], job["symbols"], routes=route_plan)
                    elif dataset == "concept_board":
                        self._sync_board_dimension(job_id, "concept", job["start_trade_date"], job["target_trade_date"], job["symbols"], routes=route_plan)
                    elif dataset == "industry_flow":
                        self._sync_flow_dimension(job_id, "industry", job["start_trade_date"], job["target_trade_date"], job["symbols"])
                    elif dataset == "concept_flow":
                        self._sync_flow_dimension(job_id, "concept", job["start_trade_date"], job["target_trade_date"], job["symbols"])
                    elif dataset == "events":
                        self._sync_events(job_id, job["symbols"], job["start_trade_date"], job["target_trade_date"])
                    elif dataset == "industry_classification_repair":
                        self._repair_classification(job_id, job["start_trade_date"], job["target_trade_date"])
                except (Exception, SystemExit) as dataset_error:
                    self.store.mark_item(
                        job_id, dataset, "__dataset__", status="failed",
                        error=f"{type(dataset_error).__name__}: {dataset_error}",
                    )
            finished = self.store.finish_job(job_id)
            if has_global_index:
                self.governance_store.finalize_global_index_release(
                    release_id=release_id, status=str(finished["status"]),
                )
        except Exception as error:  # keep background task observable
            finished = self.store.finish_job(
                job_id, error=f"{type(error).__name__}: {error}"
            )
            if has_global_index:
                release = self.governance_store.get_global_index_release(
                    job_id=job_id
                )
                if release.get("status") != "not_found":
                    self.governance_store.finalize_global_index_release(
                        release_id=release_id, status=str(finished["status"]),
                    )

    def _sync_index_daily(
        self, job_id: str, start_date: str, target_date: str,
        selected_shards: Iterable[str] = (),
    ) -> None:
        selected = {str(item) for item in selected_shards if str(item)}
        completed = self.store.completed_item_keys(job_id, "index_daily")
        items = [(code, name) for code, name in CORE_INDICES if (not selected or code in selected) and code not in completed]
        for code, _name in items:
            if self.store.should_stop(job_id):
                return
            try:
                rows = self.governance_provider.fetch_index_daily_prices(
                    index_symbol=code, start_date=start_date, end_date=target_date,
                )
                count = self.governance_store.upsert_index_prices(rows)
                self.store.mark_item(job_id, "index_daily", code, status="completed", row_count=count)
            except Exception as error:
                self.store.mark_item(
                    job_id, "index_daily", code, status="failed",
                    error=f"{type(error).__name__}: {error}",
                )

    def _sync_global_index_daily(
        self, job_id: str, start_date: str, target_date: str,
        selected_shards: Iterable[str] = (),
        *, routes: list[dict[str, Any]] | None = None,
    ) -> None:
        selected = {str(item) for item in selected_shards if str(item)}
        completed = self.store.completed_item_keys(job_id, "global_index_daily")
        route_plan = list(routes or self._default_global_index_routes())
        items = [
            item for item in GLOBAL_INDICES
            if (not selected or item["code"] in selected)
            and item["code"] not in completed
        ]
        for item in items:
            code = str(item["code"])
            if self.store.should_stop(job_id):
                return
            try:
                endpoint = str(item["endpoint"])
                route = next((
                    route for route in route_plan
                    if str(route.get("endpoint") or "") == endpoint
                    and str(route.get("partition_key") or item["partition"])
                    == str(item["partition"])
                ), None)
                if route is None:
                    raise RuntimeError(
                        "frozen route snapshot does not include required partition: "
                        f"{item['partition']} / {endpoint}"
                    )
                rows, runtime = self._fetch_global_index_with_controls(
                    item=item, route=route,
                    start_date=start_date, target_date=target_date,
                )
                calendar_start = start_date
                returned_dates = sorted(
                    str(row.get("trade_date") or "") for row in rows
                    if row.get("trade_date")
                )
                if (
                    endpoint == "index_global_hist_sina"
                    and len(returned_dates) >= 990
                    and returned_dates[0] > start_date
                ):
                    calendar_start = returned_dates[0]
                runtime["calendar_range_start"] = calendar_start
                runtime["calendar_range_end"] = target_date
                appended = self.governance_store.append_global_index_prices(
                    rows,
                    release_id=f"global-index-release-{job_id}",
                    index_symbol=code, market=str(item["market"]),
                    start_trade_date=start_date,
                    target_trade_date=target_date,
                    runtime_config=runtime,
                    calendar_range_start=calendar_start,
                    calendar_range_end=target_date,
                )
                self.store.mark_item(
                    job_id, "global_index_daily", code,
                    status="completed",
                    row_count=int(appended["inserted_rows"]),
                )
            except Exception as error:
                self.store.mark_item(
                    job_id, "global_index_daily", code, status="failed",
                    error=f"{type(error).__name__}: {error}",
                )

    @staticmethod
    def _default_global_index_routes() -> list[dict[str, Any]]:
        return [
            {
                "route_id": "global-index-us-sina",
                "partition_key": "US", "endpoint": "index_us_stock_sina",
                "requests_per_minute": 20, "timeout_seconds": 60,
                "retry_count": 2, "backoff_seconds": 3.0,
            },
            {
                "route_id": "global-index-international-sina",
                "partition_key": "INTERNATIONAL",
                "endpoint": "index_global_hist_sina",
                "requests_per_minute": 20, "timeout_seconds": 60,
                "retry_count": 2, "backoff_seconds": 3.0,
            },
        ]

    def _fetch_global_index_with_controls(
        self, *, item: Mapping[str, Any], route: Mapping[str, Any],
        start_date: str, target_date: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        route_id = str(route.get("route_id") or route.get("endpoint") or "global")
        requests_per_minute = max(1, int(route.get("requests_per_minute") or 1))
        timeout_seconds = max(1, int(route.get("timeout_seconds") or 60))
        retry_count = max(0, int(route.get("retry_count") or 0))
        backoff_seconds = max(0.0, float(route.get("backoff_seconds") or 0))
        method = self.governance_provider.fetch_global_index_daily_prices
        native_method = (
            getattr(method, "__func__", None)
            is AkshareGovernanceProvider.fetch_global_index_daily_prices
        )
        attempts = 0
        previous_errors: list[str] = []
        for attempt in range(1, retry_count + 2):
            attempts = attempt
            self._acquire_global_route_slot(route_id, requests_per_minute)

            def operation() -> list[dict[str, Any]]:
                kwargs = {
                    "index_symbol": str(item["code"]),
                    "endpoint": str(item["endpoint"]),
                    "start_date": start_date,
                    "end_date": target_date,
                }
                if native_method:
                    return method(
                        **kwargs, retry_count=1, retry_delay_seconds=0,
                        request_gate=lambda: None,
                    )
                return method(**kwargs)

            try:
                rows = self._call_with_timeout(operation, timeout_seconds)
                runtime = {
                    "route_id": route_id,
                    "partition_key": str(route.get("partition_key") or ""),
                    "requests_per_minute": requests_per_minute,
                    "timeout_seconds": timeout_seconds,
                    "retry_count": retry_count,
                    "backoff_seconds": backoff_seconds,
                    "attempts": attempts,
                    "previous_errors": previous_errors,
                }
                return list(rows), runtime
            except Exception as error:
                previous_errors.append(f"{type(error).__name__}: {error}")
                if attempt > retry_count:
                    raise RuntimeError(
                        f"route {route_id} failed after {attempts} attempt(s): "
                        + previous_errors[-1]
                    ) from error
                if backoff_seconds:
                    time.sleep(backoff_seconds * attempt)
        raise AssertionError("unreachable global-index retry loop")

    def _acquire_global_route_slot(
        self, route_id: str, requests_per_minute: int,
    ) -> None:
        interval = 60.0 / max(1, int(requests_per_minute))
        with self._global_route_rate_lock:
            now = time.monotonic()
            previous = self._global_route_last_request.get(route_id)
            if previous is not None:
                remaining = interval - (now - previous)
                if remaining > 0:
                    time.sleep(remaining)
            self._global_route_last_request[route_id] = time.monotonic()

    @staticmethod
    def _call_with_timeout(
        operation: Callable[[], list[dict[str, Any]]], timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def invoke() -> None:
            try:
                result_queue.put(("result", operation()))
            except BaseException as error:
                result_queue.put(("error", error))

        worker = threading.Thread(
            target=invoke, name="global-index-read", daemon=True,
        )
        worker.start()
        worker.join(max(0.01, float(timeout_seconds)))
        if worker.is_alive():
            raise TimeoutError(
                f"global-index read exceeded {float(timeout_seconds):g}s"
            )
        kind, value = result_queue.get_nowait()
        if kind == "error":
            raise value
        return list(value)

    def _sync_board_dimension(self, job_id: str, dimension: str, start_date: str, target_date: str, selected_shards: Iterable[str] = (), *, routes: list[dict[str, Any]] | None = None) -> None:
        catalog = self._fetch_catalog(dimension) if routes is None else self._fetch_catalog_routed(dimension, routes)
        self.store.upsert_board_catalog(dimension, catalog)
        self.store.mark_item(job_id, f"{dimension}_catalog", "catalog", status="completed", row_count=len(catalog))
        self._parallel_items(
            job_id,
            f"{dimension}_board",
            self._selected_boards(dimension, selected_shards),
            lambda item: self.store.upsert_board_daily(
                dimension, item["board_code"],
                self._fetch_board_daily_range(dimension, item, start_date, target_date)
                if routes is None else self._fetch_board_daily_routed(
                    dimension, item, start_date, target_date, routes,
                )
            ),
        )

        if not self.store.board_snapshot(dimension, target_date).get("items"):
            self.store.mark_item(job_id, f"{dimension}_board", "__dataset__", status="failed", error="no board rows were available for the target date")

    def _sync_flow_dimension(self, job_id: str, dimension: str, start_date: str, target_date: str, selected_shards: Iterable[str] = ()) -> None:
        if not self.store.list_board_catalog(dimension):
            self.store.upsert_board_catalog(dimension, self._fetch_catalog(dimension))
        self._parallel_items(
            job_id,
            f"{dimension}_flow",
            self._selected_boards(dimension, selected_shards),
            lambda item: self.store.upsert_fund_flows(
                dimension, item["board_code"], [row for row in self._fetch_fund_flow(dimension, item, target_date) if start_date <= str(row.get("trade_date") or "") <= target_date]
            ),
        )

        if not self.store.flow_snapshot(dimension, target_date).get("items"):
            self.store.mark_item(job_id, f"{dimension}_flow", "__dataset__", status="failed", error="no fund-flow rows were available not after the target date")

    def _selected_boards(self, dimension: str, selected_shards: Iterable[str]) -> list[dict[str, Any]]:
        items = self.store.list_board_catalog(dimension)
        selected = {str(item) for item in selected_shards if str(item)}
        if "__all__" in selected:
            return items
        return [item for item in items if str(item["board_code"]) in selected] if selected else items

    def _parallel_items(self, job_id: str, dataset: str, items: list[dict[str, Any]], loader: Callable[[dict[str, Any]], int]) -> None:
        completed = self.store.completed_item_keys(job_id, dataset)
        pending_items = [item for item in items if str(item["board_code"]) not in completed]
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix=dataset) as executor:
            futures = {executor.submit(_retry, loader, item): item for item in pending_items}
            for future in as_completed(futures):
                item = futures[future]
                key = str(item["board_code"])
                if self.store.should_stop(job_id):
                    for pending in futures:
                        pending.cancel()
                    return
                try:
                    count = int(future.result())
                    self.store.mark_item(job_id, dataset, key, status="completed", row_count=count)
                except Exception as error:
                    self.store.mark_item(job_id, dataset, key, status="failed", error=f"{type(error).__name__}: {error}")

    def _sync_events(self, job_id: str, symbols: list[str], start_date: str, target_date: str) -> None:
        completed = self.store.completed_item_keys(job_id, "events")
        for symbol in (item for item in symbols if item not in completed):
            if self.store.should_stop(job_id):
                return
            try:
                rows = _retry(lambda value: self._fetch_events(value, target_date, start_date=start_date), symbol)
                count = self.store.upsert_events(rows)
                self.store.mark_item(job_id, "events", symbol, status="completed", row_count=count)
            except Exception as error:
                self.store.mark_item(job_id, "events", symbol, status="failed", error=f"{type(error).__name__}: {error}")

    def _repair_classification(self, job_id: str, start_date: str, target_date: str) -> None:
        from data_platform import ClassificationHistoryStore
        from scripts.sync_a_share_classification_history import _fetch_cninfo_industries

        symbols = self._classification_failed_symbols()
        store = ClassificationHistoryStore(self.classification_database)
        for symbol in symbols:
            if self.store.should_stop(job_id):
                return
            try:
                rows = _retry(lambda value: _fetch_cninfo_industries([value], start_date.replace("-", ""), target_date.replace("-", "")), symbol)
                count = store.upsert_intervals(rows)
                status = "completed" if count else "completed"
                store.mark_sync_state("stage65-a-share-industry-history-v1", symbol, status="completed" if count else "completed_empty",
                                      attempt_count=1, interval_count=count, updated_at=_utc_now())
                self.store.mark_item(job_id, "industry_classification_repair", symbol, status=status, row_count=count)
            except (Exception, SystemExit) as error:
                self.store.mark_item(job_id, "industry_classification_repair", symbol, status="failed", error=f"{type(error).__name__}: {error}")

    def _local_industry_snapshot(self, requested_date: str) -> dict[str, Any]:
        if not self.market_database.is_file() or not self.classification_database.is_file():
            return {"status": "unavailable", "requested_trade_date": requested_date, "effective_trade_date": None, "items": []}
        with sqlite3.connect(f"file:{self.market_database.resolve().as_posix()}?mode=ro", uri=True, timeout=30) as market:
            market.row_factory = sqlite3.Row
            effective = market.execute(
                "SELECT MAX(trade_date) FROM market_daily_prices WHERE adjustment='qfq' AND trade_date<=?",
                (requested_date,),
            ).fetchone()[0]
            if not effective:
                return {"status": "unavailable", "requested_trade_date": requested_date, "effective_trade_date": None, "items": []}
            prices = [dict(row) for row in market.execute(
                """SELECT p.symbol, s.name, p.change_pct, p.amount, p.turnover_rate
                   FROM market_daily_prices p LEFT JOIN market_symbols s ON s.symbol=p.symbol
                   WHERE p.adjustment='qfq' AND p.trade_date=? AND p.change_pct IS NOT NULL""",
                (effective,),
            ).fetchall()]
        categories, standards = self._classification_as_of(effective)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in prices:
            category = categories.get(str(row["symbol"]).split(".")[0])
            if category:
                grouped[category].append(row)
        items = []
        for category, rows in grouped.items():
            changes = [float(row["change_pct"]) for row in rows]
            amounts = [float(row["amount"] or 0) for row in rows]
            leader = max(rows, key=lambda row: float(row["change_pct"]))
            items.append({
                "board_code": category,
                "board_name": category,
                "trade_date": effective,
                "change_pct": statistics.fmean(changes),
                "median_change_pct": statistics.median(changes),
                "member_count": len(rows),
                "up_count": sum(value > 0 for value in changes),
                "down_count": sum(value < 0 for value in changes),
                "flat_count": sum(value == 0 for value in changes),
                "amount": sum(amounts),
                "leader_symbol": leader["symbol"],
                "leader_name": leader.get("name") or leader["symbol"],
                "leader_change_pct": leader["change_pct"],
                "classification_standard": standards.get(str(leader["symbol"]).split(".")[0]),
                "source": "canonical_qfq_plus_point_in_time_classification",
            })
        items.sort(key=lambda row: (float(row["change_pct"]), row["board_name"]), reverse=True)
        classified = sum(len(rows) for rows in grouped.values())
        return {
            "status": "ready" if effective == requested_date else "stale",
            "requested_trade_date": requested_date,
            "effective_trade_date": effective,
            "items": items,
            "source": "canonical_a_share_sqlite+classification_history_sqlite",
            "coverage": {
                "price_symbols": len(prices),
                "classified_symbols": classified,
                "coverage_ratio": classified / len(prices) if prices else 0,
                "category_count": len(items),
            },
            "taxonomy_note": "one latest point-in-time category per symbol; standards are retained per evidence and not hidden",
        }

    def _classification_as_of(self, target_date: str) -> tuple[dict[str, str], dict[str, str]]:
        with sqlite3.connect(f"file:{self.classification_database.resolve().as_posix()}?mode=ro", uri=True, timeout=30) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT symbol, category, valid_from, source,
                          json_extract(evidence_json, '$.classification_standard') standard
                   FROM classification_intervals
                   WHERE dimension='industry' AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?)
                   ORDER BY symbol, valid_from DESC""",
                (target_date, target_date),
            ).fetchall()
        priorities = {
            "中国上市公司协会上市公司行业分类标准": 0,
            "中证行业分类标准": 1,
            "申银万国行业分类标准": 2,
            "巨潮行业分类标准": 3,
        }
        selected: dict[str, sqlite3.Row] = {}
        for row in rows:
            symbol = str(row["symbol"])
            current = selected.get(symbol)
            rank = (str(row["valid_from"]), -priorities.get(str(row["standard"] or ""), 99))
            if current is None:
                selected[symbol] = row
                continue
            current_rank = (str(current["valid_from"]), -priorities.get(str(current["standard"] or ""), 99))
            if rank > current_rank:
                selected[symbol] = row
        return ({symbol: str(row["category"]) for symbol, row in selected.items()},
                {symbol: str(row["standard"] or row["source"]) for symbol, row in selected.items()})

    def _classification_failed_symbols(self) -> list[str]:
        if not self.classification_database.is_file():
            return []
        with sqlite3.connect(f"file:{self.classification_database.resolve().as_posix()}?mode=ro", uri=True) as connection:
            return [str(row[0]) for row in connection.execute(
                "SELECT symbol FROM classification_sync_state WHERE job_id='stage65-a-share-industry-history-v1' AND status='failed' ORDER BY symbol"
            ).fetchall()]

    def _classification_failed_count(self) -> int:
        return len(self._classification_failed_symbols())

    @staticmethod
    def _datasets(values: Iterable[str]) -> list[str]:
        normalized = []
        for value in values:
            text = str(value or "").strip().lower()
            expanded = list(PANORAMA_DATASETS[:4]) if text == "panorama_all" else [text]
            for item in expanded:
                if item not in PANORAMA_DATASETS:
                    raise ValueError(f"unsupported panorama dataset: {item}")
                if item not in normalized:
                    normalized.append(item)
        if not normalized:
            raise ValueError("at least one panorama dataset is required")
        return normalized

    @staticmethod
    def _akshare():
        import akshare as ak
        return ak

    def _fetch_catalog(self, dimension: str) -> list[dict[str, Any]]:
        try:
            return self._fetch_catalog_curl(dimension)
        except Exception:
            return [
                {**row, "source": f"akshare.stock_board_{dimension}_name_ths"}
                for row in self.ths_board_provider.fetch_catalog(dimension)
            ]

    def _fetch_catalog_routed(
        self, dimension: str, routes: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        errors: list[str] = []
        for route in routes:
            endpoint = str(route.get("endpoint") or "")
            try:
                if endpoint.endswith("_hist_em"):
                    return self._fetch_catalog_curl(dimension)
                if endpoint.endswith("_index_ths"):
                    rows = list(self.ths_board_provider.fetch_catalog(dimension))
                    if rows:
                        return [
                            {**row, "source": f"akshare.stock_board_{dimension}_name_ths"}
                            for row in rows
                        ]
                    raise RuntimeError(f"empty THS {dimension} board catalog")
                errors.append(f"unsupported route endpoint: {endpoint}")
            except Exception as error:
                errors.append(f"{route.get('route_id')}: {type(error).__name__}: {error}")
        raise RuntimeError("; ".join(errors) or f"no usable {dimension} board route")

    def _fetch_board_daily_routed(
        self, dimension: str, item: Mapping[str, Any], start_date: str,
        target_date: str, routes: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        errors: list[str] = []
        for route in routes:
            endpoint = str(route.get("endpoint") or "")
            try:
                if endpoint.endswith("_hist_em"):
                    rows = self._fetch_board_daily_range(
                        dimension, item, start_date, target_date,
                        allow_fallback=False,
                    )
                elif endpoint.endswith("_index_ths"):
                    rows = self._fetch_board_daily_range_ths(
                        dimension, item, start_date, target_date,
                    )
                else:
                    errors.append(f"unsupported route endpoint: {endpoint}")
                    continue
                if rows:
                    return rows
                errors.append(f"{route.get('route_id')}: empty response")
            except Exception as error:
                errors.append(f"{route.get('route_id')}: {type(error).__name__}: {error}")
        raise RuntimeError("; ".join(errors) or f"no usable {dimension} board route")

    def _fetch_catalog_curl(self, dimension: str) -> list[dict[str, Any]]:
        url = "https://17.push2.eastmoney.com/api/qt/clist/get" if dimension == "industry" else "https://79.push2.eastmoney.com/api/qt/clist/get"
        sector_filter = "m:90 t:2 f:!50" if dimension == "industry" else "m:90 t:3 f:!50"
        result: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = _curl_json(url, {
                "pn": page, "pz": 100, "po": 1, "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": 2,
                "invt": 2, "fid": "f12", "fs": sector_filter, "fields": "f12,f14",
            })
            data = dict(payload.get("data") or {})
            rows = list(data.get("diff") or [])
            result.extend({"board_code": str(row.get("f12") or ""), "board_name": str(row.get("f14") or ""), "source": f"eastmoney.{dimension}_board_curl"} for row in rows if row.get("f12") and row.get("f14"))
            if not rows or page * 100 >= int(data.get("total") or len(result)):
                break
            page += 1
        if not result:
            raise RuntimeError(f"empty {dimension} board catalog from eastmoney")
        return result

    def _fetch_board_daily_range(
        self, dimension: str, item: Mapping[str, Any], start_date: str, target_date: str,
        *, allow_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        if start_date == target_date:
            return self._fetch_board_daily(
                dimension, item, target_date, allow_fallback=allow_fallback,
            )
        code = str(item["board_code"])
        try:
            payload = _curl_json("https://91.push2his.eastmoney.com/api/qt/stock/kline/get", {
                "secid": f"90.{code}", "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101, "fqt": 0, "beg": start_date.replace("-", ""),
                "end": target_date.replace("-", ""), "smplmt": 10000, "lmt": 1000000,
            })
            rows = []
            for raw in list((payload.get("data") or {}).get("klines") or []):
                values = str(raw).split(",")
                if len(values) >= 11:
                    rows.append({"trade_date": values[0], "open": values[1], "close": values[2],
                                 "high": values[3], "low": values[4], "volume": values[5],
                                 "amount": values[6], "amplitude": values[7], "change_pct": values[8],
                                 "change_amount": values[9], "turnover_rate": values[10],
                                 "source": f"eastmoney.{dimension}_board_kline_curl"})
            if rows:
                return rows
        except Exception:
            if not allow_fallback:
                raise
        if not allow_fallback:
            raise RuntimeError(f"empty {dimension} board history response")
        return self._fetch_board_daily_range_ths(
            dimension, item, start_date, target_date,
        )

    def _fetch_board_daily_range_ths(
        self, dimension: str, item: Mapping[str, Any], start_date: str,
        target_date: str,
    ) -> list[dict[str, Any]]:
        code = str(item["board_code"])
        frame = self.ths_board_provider.fetch_index(
            dimension, board_name=str(item["board_name"]), board_code=code,
            start_date=start_date.replace("-", ""), end_date=target_date.replace("-", ""),
        )
        records = sorted(frame.to_dict("records"), key=lambda row: str(_pick(row, "日期") or ""))
        rows = []
        for index, row in enumerate(records):
            trade_date = str(_pick(row, "日期") or "")[:10]
            if not trade_date or not start_date <= trade_date <= target_date:
                continue
            close = _number(_pick(row, "收盘价", "收盘"))
            previous = _number(_pick(records[index - 1], "收盘价", "收盘")) if index else None
            rows.append({"trade_date": trade_date, "open": _pick(row, "开盘价", "开盘"),
                         "high": _pick(row, "最高价", "最高"), "low": _pick(row, "最低价", "最低"),
                         "close": close, "volume": _pick(row, "成交量"), "amount": _pick(row, "成交额"),
                         "change_pct": ((close / previous - 1) * 100) if close is not None and previous not in {None, 0} else None,
                         "source": f"akshare.stock_board_{dimension}_index_ths"})
        return rows
    def _fetch_board_daily(
        self, dimension: str, item: Mapping[str, Any], target_date: str,
        *, allow_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        code = str(item["board_code"])
        compact = target_date.replace("-", "")
        try:
            payload = _curl_json("https://91.push2his.eastmoney.com/api/qt/stock/kline/get", {
                "secid": f"90.{code}", "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101, "fqt": 0, "beg": compact, "end": compact,
                "smplmt": 10000, "lmt": 1000000,
            })
            rows = []
            for raw in list((payload.get("data") or {}).get("klines") or []):
                values = str(raw).split(",")
                if len(values) < 11:
                    continue
                rows.append({"trade_date": values[0], "open": values[1], "close": values[2], "high": values[3], "low": values[4], "volume": values[5], "amount": values[6], "amplitude": values[7], "change_pct": values[8], "change_amount": values[9], "turnover_rate": values[10], "source": f"eastmoney.{dimension}_board_kline_curl"})
            if not rows:
                raise RuntimeError("empty board daily response")
            return rows
        except Exception:
            if not allow_fallback:
                raise
            return self._fetch_board_daily_ths(dimension, item, target_date)

    def _fetch_board_daily_ths(self, dimension: str, item: Mapping[str, Any], target_date: str) -> list[dict[str, Any]]:
        end = datetime.fromisoformat(target_date)
        start = (end - timedelta(days=12)).strftime("%Y%m%d")
        frame = self.ths_board_provider.fetch_index(
            dimension,
            board_name=str(item["board_name"]),
            board_code=str(item["board_code"]),
            start_date=start,
            end_date=end.strftime("%Y%m%d"),
        )
        records = sorted(frame.to_dict("records"), key=lambda row: str(_pick(row, "日期") or ""))
        for index, row in enumerate(records):
            if str(_pick(row, "日期") or "")[:10] != target_date:
                continue
            close = _number(_pick(row, "收盘价", "收盘"))
            previous = _number(_pick(records[index - 1], "收盘价", "收盘")) if index else None
            change_pct = ((close / previous - 1) * 100) if close is not None and previous not in {None, 0} else None
            return [{
                "trade_date": target_date, "open": _pick(row, "开盘价", "开盘"),
                "high": _pick(row, "最高价", "最高"), "low": _pick(row, "最低价", "最低"),
                "close": close, "volume": _pick(row, "成交量"), "amount": _pick(row, "成交额"),
                "change_pct": change_pct, "source": f"akshare.stock_board_{dimension}_index_ths",
            }]
        return []
    def _fetch_fund_flow(self, dimension: str, item: Mapping[str, Any], target_date: str) -> list[dict[str, Any]]:
        payload = _curl_json("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get", {
            "lmt": 0, "klt": 101, "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "secid": f"90.{item['board_code']}",
        })
        rows = []
        for raw in list((payload.get("data") or {}).get("klines") or []):
            values = str(raw).split(",")
            if len(values) < 11 or values[0] > target_date:
                continue
            rows.append({
                "trade_date": values[0], "main_net_inflow": values[1], "small_net_inflow": values[2],
                "medium_net_inflow": values[3], "large_net_inflow": values[4], "super_large_net_inflow": values[5],
                "main_net_ratio": values[6], "small_net_ratio": values[7], "medium_net_ratio": values[8],
                "large_net_ratio": values[9], "super_large_net_ratio": values[10],
                "source": f"eastmoney.{dimension}_fund_flow_curl",
            })
        return rows

    def _fetch_events(self, symbol: str, target_date: str, *, start_date: str = "") -> list[dict[str, Any]]:
        ak = self._akshare()
        compact = target_date.replace("-", "")
        compact_start = (start_date or target_date).replace("-", "")
        result: list[dict[str, Any]] = []
        errors: list[str] = []
        try:
            result.extend(self.cninfo_provider.fetch_announcements(symbol, compact_start, compact))
        except Exception as error:
            errors.append(f"cninfo_controlled:{type(error).__name__}:{error}")
        try:
            news = ak.stock_news_em(symbol=symbol)
            for row in news.to_dict("records"):
                published = str(_pick(row, "发布时间") or "")
                event_date = published[:10]
                if not (start_date or target_date) <= event_date <= target_date:
                    continue
                result.append({"event_date": event_date, "published_at": published, "symbol": symbol,
                               "event_type": "news", "title": str(_pick(row, "新闻标题") or "新闻"),
                               "url": str(_pick(row, "新闻链接") or ""), "source": str(_pick(row, "文章来源") or "eastmoney"),
                               "evidence": {"content": str(_pick(row, "新闻内容") or "")[:1000]}})
        except Exception as error:
            errors.append(f"eastmoney_news:{type(error).__name__}:{error}")
        if not result and len(errors) >= 2:
            raise RuntimeError("; ".join(errors))
        return result


def _curl_json(url: str, params: Mapping[str, Any], *, method: str = "GET") -> dict[str, Any]:
    executable = shutil.which("curl.exe") or shutil.which("curl")
    if not executable:
        raise RuntimeError("system curl is unavailable")
    command = [executable, "-sS", "--fail", "--max-time", "30"]
    proxy_url = discover_proxy_url()
    if proxy_url:
        command.extend(["--proxy", proxy_url])
    else:
        command.extend(["--noproxy", "*"])
    command.extend(["--get"] if method.upper() == "GET" else ["--request", "POST"])
    for key, value in params.items():
        command.extend(["--data-urlencode", f"{key}={value}"])
    command.append(url)
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=40, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"curl transport failed ({completed.returncode}): {completed.stderr.strip()[:300]}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("curl endpoint did not return a JSON object")
    return payload

def _retry(loader: Callable[[Any], Any], value: Any, attempts: int = 3) -> Any:
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            return loader(value)
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(min(1.5 * (2 ** attempt), 6.0))
    raise error or RuntimeError("panorama upstream request failed")


def _symbols(values: Iterable[str]) -> list[str]:
    return sorted({str(value or "").strip().split(".")[0].zfill(6) for value in values if str(value or "").strip()})


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

def _pick(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _normalize_board_row(row: Mapping[str, Any], source: str) -> dict[str, Any]:
    return {
        "trade_date": str(_pick(row, "日期", "date") or "")[:10],
        "open": _pick(row, "开盘", "open"), "high": _pick(row, "最高", "high"),
        "low": _pick(row, "最低", "low"), "close": _pick(row, "收盘", "close"),
        "change_pct": _pick(row, "涨跌幅", "change_pct"), "change_amount": _pick(row, "涨跌额", "change_amount"),
        "volume": _pick(row, "成交量", "volume"), "amount": _pick(row, "成交额", "amount"),
        "amplitude": _pick(row, "振幅", "amplitude"), "turnover_rate": _pick(row, "换手率", "turnover_rate"),
        "source": source,
    }


def _normalize_flow_row(row: Mapping[str, Any], source: str) -> dict[str, Any]:
    return {
        "trade_date": str(_pick(row, "日期") or "")[:10],
        "main_net_inflow": _pick(row, "主力净流入-净额"), "main_net_ratio": _pick(row, "主力净流入-净占比"),
        "super_large_net_inflow": _pick(row, "超大单净流入-净额"), "super_large_net_ratio": _pick(row, "超大单净流入-净占比"),
        "large_net_inflow": _pick(row, "大单净流入-净额"), "large_net_ratio": _pick(row, "大单净流入-净占比"),
        "medium_net_inflow": _pick(row, "中单净流入-净额"), "medium_net_ratio": _pick(row, "中单净流入-净占比"),
        "small_net_inflow": _pick(row, "小单净流入-净额"), "small_net_ratio": _pick(row, "小单净流入-净占比"),
        "source": source,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
