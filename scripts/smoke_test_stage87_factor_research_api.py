"""Stage 87 end-to-end smoke test for governed factor research APIs."""

from __future__ import annotations

import json
import gc
import math
import sqlite3
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def _weekdays(start: date, end: date) -> list[date]:
    result: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _seed_market_database(database_path: Path) -> list[str]:
    symbols = [f"{index:06d}" for index in range(1, 11)]
    dates = _weekdays(date(2025, 10, 1), date(2026, 4, 30))
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE data_versions (
                data_version_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                as_of_trade_date TEXT NOT NULL,
                quality_report_id TEXT NOT NULL,
                manifest_hash TEXT NOT NULL,
                published_at TEXT NOT NULL
            );
            CREATE TABLE data_version_members (
                data_version_id TEXT NOT NULL,
                dataset TEXT NOT NULL,
                adjustment TEXT,
                symbol_scope TEXT,
                row_count INTEGER,
                symbol_count INTEGER,
                min_date TEXT,
                max_date TEXT,
                source TEXT,
                sync_run_ref TEXT,
                content_hash TEXT,
                quality_status TEXT,
                details_json TEXT
            );
            CREATE TABLE data_quality_reports (
                quality_report_id TEXT PRIMARY KEY, status TEXT NOT NULL
            );
            CREATE TABLE data_center_settings (
                setting_key TEXT PRIMARY KEY, setting_value TEXT, updated_at TEXT
            );            CREATE TABLE market_daily_prices (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                adjustment TEXT NOT NULL,
                close REAL NOT NULL,
                amount REAL NOT NULL
            );
            CREATE TABLE market_trade_calendar (
                market TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                is_open INTEGER NOT NULL
            );
            CREATE TABLE security_trading_status_daily (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                is_tradable INTEGER NOT NULL
            );
            CREATE TABLE security_lifecycle_events (
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                effective_from TEXT,
                effective_to TEXT
            );
            CREATE TABLE security_master_intervals (
                interval_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                listing_status TEXT NOT NULL,
                risk_warning INTEGER NOT NULL,
                available_at TEXT NOT NULL,
                source TEXT NOT NULL,
                source_observed_at TEXT,
                source_payload_hash TEXT,
                evidence_json TEXT NOT NULL
            );
            CREATE INDEX idx_stage87_prices
                ON market_daily_prices(symbol, adjustment, trade_date);
            """
        )
        version_id = "scq-stage87-smoke-v1"
        connection.execute(
            "INSERT INTO data_versions VALUES (?, 'published', ?, ?, ?, ?)",
            (
                version_id,
                dates[-1].isoformat(),
                "stage87-smoke-quality",
                "stage87-smoke-manifest",
                "2026-05-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO data_quality_reports VALUES (?, 'passed')",
            ("stage87-smoke-quality",),
        )
        connection.execute(
            "INSERT INTO data_center_settings VALUES ('default_data_version_id', ?, ?)",
            (version_id, "2026-05-01T00:00:00+00:00"),
        )
        members = [
            ("market_daily_prices", "raw"),
            ("market_daily_prices", "qfq"),
            ("market_trade_calendar", ""),
            ("security_lifecycle_events", ""),
            ("security_trading_status_daily", ""),
            ("security_master_intervals", ""),
        ]
        connection.executemany(
            """
            INSERT INTO data_version_members (
                data_version_id, dataset, adjustment, symbol_scope, row_count,
                symbol_count, min_date, max_date, source, sync_run_ref, content_hash,
                quality_status, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'passed', '{}')
            """,
            [
                (
                    version_id,
                    dataset,
                    adjustment,
                    "all_a",
                    len(dates) * len(symbols) if dataset == "market_daily_prices" else len(dates),
                    len(symbols),
                    dates[0].isoformat(),
                    dates[-1].isoformat(),
                    "stage87_smoke",
                    "stage87-smoke-sync",
                    f"hash-{dataset}-{adjustment or 'none'}",
                )
                for dataset, adjustment in members
            ],
        )
        connection.execute(
            """UPDATE data_version_members
               SET details_json=? WHERE data_version_id=?
                 AND dataset='security_master_intervals' AND adjustment=''""",
            ('{"snapshot_refs":["stage87-security-snapshot"]}', version_id),
        )
        connection.executemany(
            "INSERT INTO market_trade_calendar VALUES ('CN', ?, 1)",
            [(item.isoformat(),) for item in dates],
        )
        price_rows = []
        status_rows = []
        for symbol_index, symbol in enumerate(symbols):
            base = 20.0 + symbol_index
            for day_index, trade_day in enumerate(dates):
                phase = day_index / 8.0 + symbol_index * 0.7
                trend = (symbol_index - 4.5) * 0.00018
                close = base * (1.0 + trend * day_index + 0.025 * math.sin(phase))
                amount = 1_000_000.0 * (1.0 + symbol_index * 0.08) * (
                    1.0 + 0.18 * math.sin(day_index / 5.0 + symbol_index)
                )
                for adjustment, multiplier in (("raw", 1.0), ("qfq", 1.01)):
                    price_rows.append(
                        (symbol, trade_day.isoformat(), adjustment, close * multiplier, amount)
                    )
                status_rows.append((symbol, trade_day.isoformat(), 1))
        connection.executemany(
            "INSERT INTO market_daily_prices VALUES (?, ?, ?, ?, ?)", price_rows
        )
        connection.executemany(
            "INSERT INTO security_trading_status_daily VALUES (?, ?, ?)", status_rows
        )
        connection.executemany(
            "INSERT INTO security_lifecycle_events VALUES (?, 'listed', ?, NULL)",
            [(
                symbol,
                "2026-03-02" if index == len(symbols) - 1 else "2025-01-01",
            ) for index, symbol in enumerate(symbols)],
        )
        security_rows = []
        for index, symbol in enumerate(symbols):
            if index == 0:
                security_rows.extend([
                    (
                        f"risk-{symbol}", symbol, "2025-01-01", "2026-02-27",
                        "listed", 1, "2025-01-01", "stage87_smoke", "2026-05-01",
                        f"risk-hash-{symbol}", '{"job_id":"stage87-security-snapshot"}',
                    ),
                    (
                        f"normal-{symbol}", symbol, "2026-03-02", "2026-04-30",
                        "listed", 0, "2026-03-02", "stage87_smoke", "2026-05-01",
                        f"normal-hash-{symbol}", '{"job_id":"stage87-security-snapshot"}',
                    ),
                ])
            else:
                security_rows.append((
                    f"normal-{symbol}", symbol, "2025-01-01", "2026-04-30",
                    "listed", 0, "2025-01-01", "stage87_smoke", "2026-05-01",
                    f"normal-hash-{symbol}", '{"job_id":"stage87-security-snapshot"}',
                ))
        connection.executemany(
            "INSERT INTO security_master_intervals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            security_rows,
        )
    return symbols


def _dispatch(app, method: str, path: str, *, query: str = "", payload=None):
    from app.runtime.http_adapter import dispatch_request

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    status, response = dispatch_request(
        app,
        method=method,
        path=path,
        query_string=query,
        body=body,
    )
    if status != 200:
        raise SystemExit(f"stage87 API smoke failed: {method} {path} -> {status}")
    return response


def _wait_for_completion(service, task_id: str) -> dict:
    for _ in range(500):
        task = service.get_task(task_id)
        if task["status"] in {"completed", "failed", "partial_completed", "stopped", "interrupted"}:
            if task["status"] != "completed":
                raise SystemExit(
                    f"stage87 API smoke failed: task {task_id} ended as "
                    f"{task['status']}: {task.get('error')}"
                )
            return task
        time.sleep(0.02)
    raise SystemExit(f"stage87 API smoke failed: task {task_id} timed out")


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.api.factor_research import build_factor_research_routes
    from app.main import SimpleApiApp
    from app.services.factor_analysis_service import FactorAnalysisService
    from data_platform import ClassificationHistoryStore, DataCenterStore
    from factor_lab.storage import SqliteFactorResearchStore

    with tempfile.TemporaryDirectory(prefix="scq-stage87-", ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        market_path = root / "market.sqlite3"
        research_path = root / "research.sqlite3"
        classification_path = root / "classification.sqlite3"
        symbols = _seed_market_database(market_path)

        classifications = ClassificationHistoryStore(classification_path)
        classifications.upsert_intervals(
            [
                {
                    "symbol": symbol,
                    "dimension": "industry",
                    "category": "Industry-A" if index < 5 else "Industry-B",
                    "valid_from": "2025-01-01",
                    "source": "stage87_smoke",
                    "source_version": "v1",
                    "observed_at": "2026-05-01T00:00:00+00:00",
                    "evidence": {"fixture": True},
                }
                for index, symbol in enumerate(symbols)
            ]
        )
        index_store = DataCenterStore(market_path)
        index_store.ensure_schema()
        store = SqliteFactorResearchStore(research_path, index_store=index_store)
        service = FactorAnalysisService(
            market_database_path=market_path,
            research_store=store,
            classification_store=classifications,
        )
        app = SimpleApiApp(
            title="Stage 87 Smoke",
            routes=build_factor_research_routes(service),
        )

        definitions = _dispatch(app, "GET", "/api/factor-research/definitions")
        if len(definitions["items"]) != 11:
            raise SystemExit("stage87 API smoke failed: definition count mismatch")
        if definitions["capabilities"]["index_pools"]["status"] != "unavailable":
            raise SystemExit("stage87 API smoke failed: empty index facts must be unavailable")

        custom_payload = {
            "factor_id": "custom_price_bias",
            "name": "Custom price bias",
            "expression": "close / mean(close, 5) - 1",
            "category": "custom",
            "description": "Controlled expression smoke factor",
            "direction": "positive",
        }
        validated = _dispatch(
            app, "POST", "/api/factor-research/definitions/validate", payload=custom_payload
        )
        if validated["validation"]["input_fields"] != ["close"]:
            raise SystemExit("stage87 API smoke failed: expression validation fields mismatch")
        custom_v1 = _dispatch(
            app, "POST", "/api/factor-research/definitions", payload=custom_payload
        )["definition"]
        custom_v2 = _dispatch(
            app, "POST", "/api/factor-research/definitions", payload=custom_payload
        )["definition"]
        if (custom_v1["factor_version"], custom_v2["factor_version"]) != ("v1", "v2"):
            raise SystemExit("stage87 API smoke failed: immutable definition versions mismatch")
        try:
            service.validate_definition(dict(custom_payload, expression="__import__('os')"))
        except ValueError:
            pass
        else:
            raise SystemExit("stage87 API smoke failed: unsafe expression was accepted")

        common = {
            "factor_id": "momentum_20d",
            "start_date": "2026-02-02",
            "end_date": "2026-03-31",
            "symbols": [],
            "symbol_limit": 0,
            "factor_adjustment": "raw",
            "outcome_adjustment": "qfq",
            "forward_horizons": [5],
            "preprocessing": {
                "winsor_mad": 3.0,
                "standardize": True,
                "industry_neutral": True,
            },
            "group_count": 5,
            "cost_assumption": {"one_side_rate": 0.001},
        }
        custom_config = dict(
            common,
            research_mode="exploratory",
            factor_id="custom_price_bias",
            factor_version="v1",
            task_id="stage87-custom-factor-smoke",
            pool_type="all_a",
            symbols=symbols[:5],
            group_count=5,
            preprocessing={
                "winsor_mad": 3.0,
                "standardize": True,
                "industry_neutral": False,
            },
        )
        custom_preflight = _dispatch(
            app, "POST", "/api/factor-research/preflight", payload=custom_config
        )
        if custom_preflight["context"]["factor_version"] != "v1" or not custom_preflight["context"]["expression_hash"]:
            raise SystemExit("stage87 API smoke failed: custom factor version was not frozen")
        custom_task = _dispatch(
            app, "POST", "/api/factor-research/tasks", payload=custom_config
        )
        _dispatch(
            app, "POST", f"/api/factor-research/tasks/{custom_task['task_id']}/start"
        )
        custom_task = _wait_for_completion(service, custom_task["task_id"])
        if not store.fetch_observations(custom_task["task_id"]):
            raise SystemExit("stage87 API smoke failed: custom factor produced no observations")
        custom_report = _dispatch(
            app, "GET", f"/api/factor-research/reports/{custom_task['report_id']}"
        )
        artifact_id = str(custom_report.get("payload", {}).get("artifact", {}).get("artifact_id") or "")
        if not artifact_id.startswith("factor-artifact-"):
            raise SystemExit("stage87 API smoke failed: immutable factor artifact missing")
        artifacts = _dispatch(
            app, "GET", "/api/factor-research/artifacts", query="factor_id=custom_price_bias"
        )
        if artifact_id not in {item["artifact_id"] for item in artifacts.get("items") or []}:
            raise SystemExit("stage87 API smoke failed: factor artifact API mismatch")
        governance = service.get_artifact_governance(artifact_id)["governance"]
        if governance["review_status"] != "pending" or governance["registration_status"] != "unregistered":
            raise SystemExit("stage87 API smoke failed: new artifact governance mismatch")
        rejected = service.review_artifact(
            artifact_id,
            decision="rejected",
            note="exploratory smoke evidence must not enter strategy use",
            reviewer="stage87-smoke",
        )["governance"]
        if rejected["review_status"] != "rejected":
            raise SystemExit("stage87 API smoke failed: rejection was not persisted")
        try:
            service.register_artifact(artifact_id)
        except ValueError:
            pass
        else:
            raise SystemExit("stage87 API smoke failed: rejected artifact was registered")

        unavailable = _dispatch(
            app,
            "POST",
            "/api/factor-research/preflight",
            payload=dict(common, pool_type="index", pool_code="000300.XSHG"),
        )
        if unavailable["status"] != "unavailable" or unavailable["reasons"] != [
            "index_component_facts_unavailable"
        ]:
            raise SystemExit("stage87 API smoke failed: index unavailable semantics mismatch")

        component_rows = []
        for index, symbol in enumerate(symbols):
            component_rows.append(
                {
                    "index_code": "000300.XSHG",
                    "symbol": symbol,
                    "valid_from": "2025-01-01" if index < 5 else "2026-03-02",
                    "valid_to": "2026-02-27" if index < 5 else None,
                    "source": "stage87_smoke",
                    "source_version": "v1",
                    "observed_at": "2026-05-01T00:00:00+00:00",
                    "evidence": {"fixture": True},
                }
            )
        with sqlite3.connect(market_path) as connection:
            connection.executemany(
                """INSERT INTO index_component_intervals (
                       index_code, symbol, valid_from, valid_to, source,
                       source_version, observed_at, evidence_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        row["index_code"], row["symbol"], row["valid_from"],
                        row["valid_to"], row["source"], row["source_version"],
                        row["observed_at"], "{}",
                    )
                    for row in component_rows
                ],
            )
        if index_store.index_component_coverage()["status"] != "ready":
            raise SystemExit("stage87 API smoke failed: data-center index import mismatch")

        all_a_config = dict(common, task_id="stage87-all-a-smoke", pool_type="all_a")
        all_a_preflight = _dispatch(
            app, "POST", "/api/factor-research/preflight", payload=all_a_config
        )
        if all_a_preflight["status"] != "ready":
            raise SystemExit("stage87 API smoke failed: all-A preflight unavailable")
        if all_a_preflight["data_version"]["selection_policy"] != "global_default_version":
            raise SystemExit("stage87 API smoke failed: global-default policy mismatch")
        all_a_task = _dispatch(
            app, "POST", "/api/factor-research/tasks", payload=all_a_config
        )
        _dispatch(
            app,
            "POST",
            f"/api/factor-research/tasks/{all_a_task['task_id']}/start",
        )
        all_a_task = _wait_for_completion(service, all_a_task["task_id"])
        all_a_observations = store.fetch_observations(all_a_task["task_id"])
        if any(
            row["symbol"] == symbols[-1] and row["trade_date"] < "2026-03-02"
            for row in all_a_observations
        ):
            raise SystemExit("stage87 API smoke failed: pre-listing observation leaked")

        second_component_config = dict(
            common,
            task_id="stage87-multi-component-smoke",
            factor_id="volatility_20d",
            pool_type="all_a",
        )
        second_component_task = _dispatch(
            app, "POST", "/api/factor-research/tasks", payload=second_component_config
        )
        _dispatch(
            app, "POST",
            f"/api/factor-research/tasks/{second_component_task['task_id']}/start",
        )
        second_component_task = _wait_for_completion(service, second_component_task["task_id"])
        component_artifact_ids = []
        for component_task in (all_a_task, second_component_task):
            component_report = service.get_report(component_task["report_id"])
            component_artifact_id = component_report["payload"]["artifact"]["artifact_id"]
            store.reveal_out_of_sample(
                component_task["report_id"],
                actor="stage87-smoke-fixture",
                reason="fixture-only reveal for multi-factor plumbing",
            )
            store.review_artifact(
                component_artifact_id,
                decision="approved",
                policy_id="stage87-smoke-fixture",
                reviewer="stage87-smoke-fixture",
                note="fixture-only registration for multi-factor plumbing",
            )
            store.register_artifact(component_artifact_id)
            component_artifact_ids.append(component_artifact_id)
        multi_result = service.create_multi_factor_research({
            "factor_id": "stage87_multi_factor",
            "name": "Stage87 multi-factor",
            "artifact_ids": component_artifact_ids,
            "method": "equal_rank",
            "weights": [],
            "description": "smoke fixture",
        })
        service.reveal_out_of_sample(
            multi_result["report"]["report_id"],
            actor="stage87-smoke",
            reason="verify one-time multi-factor out-of-sample reveal",
        )
        multi_report = service.get_report(multi_result["report"]["report_id"])
        multi_evidence = multi_report["payload"]["analysis"]["multi_factor"]
        if not multi_evidence["correlations"] or len(multi_evidence["ablations"]) != 2:
            raise SystemExit("stage87 API smoke failed: multi-factor evidence incomplete")
        if multi_result["artifact"]["status"] != "research_ready":
            raise SystemExit("stage87 API smoke failed: multi-factor artifact bypassed review")
        monitor_result = service.monitor_artifact(component_artifact_ids[0], lookback_periods=22)
        if monitor_result["status"] not in {"healthy", "review_required", "action_required"}:
            raise SystemExit("stage87 API smoke failed: monitoring status mismatch")
        monitoring_history = service.list_artifact_monitoring(component_artifact_ids[0])
        if not monitoring_history["items"]:
            raise SystemExit("stage87 API smoke failed: monitoring snapshot missing")

        governed_config = dict(
            common,
            task_id="stage87-governed-all-a-smoke",
            pool_type="all_a",
            universe_policy="fujing_v7_point_in_time",
            data_version_id="scq-stage87-smoke-v1",
        )
        governed_preflight = _dispatch(
            app, "POST", "/api/factor-research/preflight", payload=governed_config
        )
        if governed_preflight["pool_snapshot"]["point_in_time_policy"] != "fujing_v7_point_in_time":
            raise SystemExit("stage87 API smoke failed: governed universe policy not frozen")
        governed_task = _dispatch(
            app, "POST", "/api/factor-research/tasks", payload=governed_config
        )
        _dispatch(app, "POST", f"/api/factor-research/tasks/{governed_task['task_id']}/start")
        governed_task = _wait_for_completion(service, governed_task["task_id"])
        governed_observations = store.fetch_observations(governed_task["task_id"])
        if any(
            row["symbol"] == symbols[0] and row["trade_date"] < "2026-03-02"
            for row in governed_observations
        ):
            raise SystemExit("stage87 API smoke failed: historical risk-warning row leaked")

        index_config = dict(
            common,
            task_id="stage87-index-smoke",
            pool_type="index",
            pool_code="000300.XSHG",
        )
        index_preflight = _dispatch(
            app, "POST", "/api/factor-research/preflight", payload=index_config
        )
        if index_preflight["status"] != "ready":
            raise SystemExit("stage87 API smoke failed: index preflight unavailable after import")
        if len(index_preflight["pool_snapshot"]["symbols"]) != 10:
            raise SystemExit("stage87 API smoke failed: point-in-time window must preserve union members")
        index_task = _dispatch(
            app, "POST", "/api/factor-research/tasks", payload=index_config
        )
        _dispatch(
            app,
            "POST",
            f"/api/factor-research/tasks/{index_task['task_id']}/start",
        )
        index_task = _wait_for_completion(service, index_task["task_id"])

        report = _dispatch(
            app,
            "GET",
            f"/api/factor-research/reports/{index_task['report_id']}",
        )
        analysis = report["payload"]["analysis"]
        if analysis["execution_estimate"]["status"] != "estimate_only":
            raise SystemExit("stage87 API smoke failed: execution estimate status mismatch")
        if not analysis["industry_ic"] or not analysis["decay"]:
            raise SystemExit("stage87 API smoke failed: enhanced report sections missing")
        observations = store.fetch_observations(index_task["task_id"])
        if not observations or not any(row["group_no"] is not None for row in observations):
            raise SystemExit("stage87 API smoke failed: eligible observation groups missing")
        unavailable_groups = analysis["group_analysis"]["unavailable_series"]
        if not unavailable_groups or any(
            row["reason"] != "sample_count_below_group_count"
            for row in unavailable_groups
        ):
            raise SystemExit("stage87 API smoke failed: group unavailable evidence missing")
        feb_symbols = {
            row["symbol"] for row in observations if row["trade_date"] <= "2026-02-27"
        }
        march_symbols = {
            row["symbol"] for row in observations if row["trade_date"] >= "2026-03-02"
        }
        if not feb_symbols <= set(symbols[:5]) or not march_symbols <= set(symbols[5:]):
            raise SystemExit("stage87 API smoke failed: point-in-time membership leaked")

        comparison = _dispatch(
            app,
            "GET",
            f"/api/factor-research/reports/{all_a_task['report_id']}/compare",
            query="report_ids=" + index_task["report_id"],
        )
        if len(comparison["items"]) != 2 or comparison["incompatible"]:
            raise SystemExit("stage87 API smoke failed: comparable pool reports mismatch")
        identity_fields = set(comparison["comparison_contract"]["identity_fields"])
        if not {
            "factor_adjustment",
            "outcome_adjustment",
            "group_count",
            "rebalance_frequency",
            "cost_assumption",
        } <= identity_fields:
            raise SystemExit("stage87 API smoke failed: comparison identity contract incomplete")

        dashboard = _dispatch(app, "GET", "/api/factor-research/dashboard")
        if not any(row["latest_report_id"] for row in dashboard["items"]):
            raise SystemExit("stage87 API smoke failed: dashboard did not expose reports")

        stop_config = dict(
            common,
            research_mode="exploratory",
            task_id="stage87-stop-retry-smoke",
            pool_type="all_a",
            symbols=symbols[:2],
            group_count=2,
            preprocessing={
                "winsor_mad": 3.0,
                "standardize": True,
                "industry_neutral": False,
            },
        )
        stop_task = _dispatch(
            app, "POST", "/api/factor-research/tasks", payload=stop_config
        )
        stopped = _dispatch(
            app,
            "POST",
            f"/api/factor-research/tasks/{stop_task['task_id']}/stop",
        )
        if stopped["status"] != "stopped":
            raise SystemExit("stage87 API smoke failed: ready task did not stop")
        retried = _dispatch(
            app,
            "POST",
            f"/api/factor-research/tasks/{stop_task['task_id']}/retry-failed",
        )
        retried = _wait_for_completion(service, retried["task_id"])
        if retried["context_hash"] != stop_task["context_hash"]:
            raise SystemExit("stage87 API smoke failed: retry changed frozen context")

        recovery_config = dict(
            stop_config,
            task_id="stage87-recovery-smoke",
        )
        recovery_task = _dispatch(
            app, "POST", "/api/factor-research/tasks", payload=recovery_config
        )
        store.update_task(recovery_task["task_id"], status="running")
        recovered_store = SqliteFactorResearchStore(research_path)
        if recovered_store.get_task(recovery_task["task_id"])["status"] != "interrupted":
            raise SystemExit("stage87 API smoke failed: running task recovery mismatch")

        try:
            store.save_report(
                report_id=index_task["report_id"],
                task_id=index_task["task_id"],
                context_hash=index_task["context_hash"],
                payload={"status": "changed"},
            )
        except ValueError as error:
            if "immutable" not in str(error):
                raise
        else:
            raise SystemExit("stage87 API smoke failed: immutable report was overwritten")
        print("stage87 factor research API smoke test passed")
        service._threads.clear()
        del app, service, store, recovered_store, classifications, index_store
        gc.collect()
        time.sleep(0.05)


if __name__ == "__main__":
    main()
