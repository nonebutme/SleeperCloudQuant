"""Isolated Stage-2 trading-status correction closure/API smoke test."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import time
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


class _NoWriteProvider:
    def sync_symbol(self, *_args, **_kwargs):
        raise AssertionError("closure smoke must not call an upstream provider")


def _dispatch(app, method: str, path: str, body: dict | None = None) -> dict:
    from app.runtime.http_adapter import dispatch_request

    status, payload = dispatch_request(
        app,
        method=method,
        path=path,
        body=(json.dumps(body).encode("utf-8") if body is not None else b""),
    )
    assert status == 200, (status, payload)
    return dict(payload["result"])


def _poll(app, run_id: str) -> dict:
    for _ in range(500):
        task = _dispatch(
            app,
            "GET",
            f"/api/data-center/quality/trading-status-remediation/tasks/{run_id}",
        )
        if task["status"] in {"completed", "authorization_exhausted", "failed"}:
            return task
        time.sleep(0.01)
    raise AssertionError(f"remediation did not finish: {run_id}")


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.api.data_center import build_data_center_routes
    from app.main import SimpleApiApp
    from app.services.data_center_service import (
        DataCenterService,
        TRADING_STATUS_CORRECTION_CONFIRMATION,
    )
    from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
    from data_platform.storage.data_center_store import DataCenterStore
    from scripts.apply_trading_status_semantic_remediation import CONFIRMATION_PHRASE

    with tempfile.TemporaryDirectory(
        prefix="scq-stage2-status-closure-",
        ignore_cleanup_errors=True,
    ) as temporary:
        root = Path(temporary)
        database = root / "market.sqlite3"
        task_dir = root / "remediation"
        market = AShareMarketStore(database)
        governance = AShareGovernanceStore(database)
        market.ensure_schema()
        governance.ensure_schema()
        symbols = ("000201", "000202")
        market.upsert_symbols([
            {"symbol": symbol, "name": f"fixture-{symbol}", "source": "smoke"}
            for symbol in symbols
        ])
        for symbol in symbols:
            market.upsert_daily_prices([{
                "symbol": symbol,
                "trade_date": "2026-08-17",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
                "volume": 100,
                "amount": 1_000,
            }], adjustment="qfq", source="smoke")
        governance.upsert_trading_statuses([
            {
                "symbol": symbol,
                "trade_date": "2026-08-17",
                "status": "unknown",
                "is_tradable": None,
                "source": "stage78.3:evidence_gap",
                "evidence": {"fixture": symbol},
            }
            for symbol in symbols
        ])
        scheduler = AShareSyncScheduler(
            database,
            market_store=market,
            governance_store=governance,
            provider=_NoWriteProvider(),
            max_workers=1,
            retry_count=1,
        )
        scheduler.ensure_schema()
        store = DataCenterStore(database)
        service = DataCenterService(
            store,
            scheduler,
            governance,
            trading_status_remediation_dir=task_dir,
        )
        app = SimpleApiApp(
            title="stage2-status-closure-smoke",
            routes=build_data_center_routes(service),
        )

        base_report = governance.save_quality_report(
            quality_report_id="dq-stage2-status-closure-base",
            rule_version="smoke-base-v1",
            status="passed",
            payload={"fixture": "stage2-status-closure-base"},
        )
        base_status = governance.inspect_trading_status_member_content()
        base = governance.publish_data_version(
            as_of_trade_date="2026-08-17",
            quality_report_id=str(base_report["quality_report_id"]),
            members=[
                {
                    "dataset": "market_daily_prices",
                    "adjustment": "qfq",
                    "symbol_scope": "canonical_all",
                    "row_count": 2,
                    "symbol_count": 2,
                    "min_date": "2026-08-17",
                    "max_date": "2026-08-17",
                    "source": "smoke",
                    "sync_run_ref": "base-smoke",
                    "content_hash": "1" * 64,
                    "quality_status": "passed",
                    "details": {"fixture": True},
                },
                {
                    **base_status,
                    "symbol_scope": "canonical_all",
                    "source": "smoke-base-status",
                    "sync_run_ref": "base-smoke",
                    "quality_status": "passed",
                    "details": {"fixture": True},
                },
            ],
            notes="isolated closure smoke base",
        )
        store.set_default_version(str(base["data_version_id"]))

        first_preview = _dispatch(
            app,
            "POST",
            "/api/data-center/quality/trading-status-remediation/preview",
            {"scope": "current_symbols"},
        )
        assert first_preview["candidate_count"] == 2
        first_run = "legacy-partial-smoke"
        _dispatch(
            app,
            "POST",
            "/api/data-center/quality/trading-status-remediation/tasks",
            {
                "expected_candidate_set_hash": first_preview["candidate_set_hash"],
                "run_id": first_run,
                "operator": "qa-admin",
                "confirmation": CONFIRMATION_PHRASE,
                "scope": "current_symbols",
                "authorized_total_writes": 1,
                "commit_batch_size": 1,
                "authorization_reference": "legacy-partial-smoke-write",
            },
        )
        assert _poll(app, first_run)["status"] == "authorization_exhausted"
        legacy_checkpoint = task_dir / f"{first_run}.json"
        legacy_state = json.loads(legacy_checkpoint.read_text(encoding="utf-8"))
        legacy_state["checkpoint_version"] = "1"
        legacy_state["status"] = "paused_max_writes"
        legacy_state["scope"] = "current_symbols"
        legacy_checkpoint.write_text(
            json.dumps(legacy_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        second_preview = _dispatch(
            app,
            "POST",
            "/api/data-center/quality/trading-status-remediation/preview",
            {"scope": "all_symbols"},
        )
        assert second_preview["candidate_count"] == 1
        second_run = "all-symbols-completed-smoke"
        _dispatch(
            app,
            "POST",
            "/api/data-center/quality/trading-status-remediation/tasks",
            {
                "expected_candidate_set_hash": second_preview["candidate_set_hash"],
                "run_id": second_run,
                "operator": "qa-admin",
                "confirmation": CONFIRMATION_PHRASE,
                "scope": "all_symbols",
                "authorized_total_writes": 1,
                "commit_batch_size": 1,
                "authorization_reference": "all-symbols-smoke-write",
            },
        )
        completed = _poll(app, second_run)
        assert completed["status"] == "completed"
        assert completed["completion_consistency"] == "matched"

        route_paths = {route.path for route in build_data_center_routes(service)}
        assert {
            "/api/data-center/quality/trading-status-remediation/closure",
            "/api/data-center/quality/trading-status-remediation/closure/quick-recheck",
            "/api/data-center/versions/corrections/publish",
        } <= route_paths
        closure = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert closure["status"] == "ready", closure["blockers"]
        assert closure["change_set"]["key_count"] == 2
        assert closure["change_set"]["run_ids"] == sorted([first_run, second_run])
        assert any(
            item["evidence_status"] == "sealed_legacy_partial"
            for item in closure["change_set"]["run_bindings"]
        )
        assert "exact_keys" not in closure["change_set"]

        # Windows can briefly deny readers while the worker atomically replaces
        # a checkpoint.  GET, list and closure binding reads must all survive
        # that bounded sharing window, while unrelated permission errors fail.
        retry_checkpoint = (task_dir / f"{second_run}.json").resolve()
        original_path_read_bytes = Path.read_bytes
        read_fault = {"remaining": 0, "winerror": 32, "calls": 0}

        def flaky_checkpoint_read(path: Path) -> bytes:
            if path.resolve() == retry_checkpoint:
                read_fault["calls"] += 1
                if int(read_fault["remaining"]) > 0:
                    read_fault["remaining"] -= 1
                    error = PermissionError(
                        13, "simulated checkpoint sharing conflict", str(path)
                    )
                    error.winerror = int(read_fault["winerror"])
                    raise error
            return original_path_read_bytes(path)

        Path.read_bytes = flaky_checkpoint_read
        try:
            before_calls = int(read_fault["calls"])
            read_fault["remaining"] = 1
            detail_after_retry = _dispatch(
                app,
                "GET",
                (
                    "/api/data-center/quality/trading-status-remediation/tasks/"
                    f"{second_run}"
                ),
            )
            assert detail_after_retry["run_id"] == second_run
            assert int(read_fault["calls"]) - before_calls >= 2

            before_calls = int(read_fault["calls"])
            read_fault["remaining"] = 1
            from app.runtime.http_adapter import (
                dispatch_request as dispatch_list_request,
            )

            list_status, _list_payload = dispatch_list_request(
                app,
                method="GET",
                path=(
                    "/api/data-center/quality/trading-status-remediation/tasks"
                ),
            )
            assert list_status == 200
            assert int(read_fault["calls"]) - before_calls >= 2

            cached_tasks = service.list_trading_status_batch_remediations()
            original_task_list = service.list_trading_status_batch_remediations
            service.list_trading_status_batch_remediations = lambda: cached_tasks
            try:
                before_calls = int(read_fault["calls"])
                read_fault["remaining"] = 1
                closure_after_retry = _dispatch(
                    app,
                    "GET",
                    "/api/data-center/quality/trading-status-remediation/closure",
                )
                assert closure_after_retry["status"] == "ready", (
                    closure_after_retry["blockers"]
                )
                assert int(read_fault["calls"]) - before_calls >= 2
            finally:
                service.list_trading_status_batch_remediations = original_task_list

            before_calls = int(read_fault["calls"])
            read_fault["remaining"] = 1
            read_fault["winerror"] = 99
            try:
                service._read_trading_status_checkpoint_bytes(retry_checkpoint)
            except PermissionError:
                pass
            else:
                raise AssertionError("non-sharing checkpoint error was retried")
            assert int(read_fault["calls"]) - before_calls == 1
        finally:
            Path.read_bytes = original_path_read_bytes

        # A completed all-symbol run cannot seal work whose checkpoint finished
        # after that sealer's immutable candidate manifest was authorized/frozen.
        sealer_checkpoint = task_dir / f"{second_run}.json"
        original_sealer_checkpoint = sealer_checkpoint.read_text(encoding="utf-8")
        old_sealer_state = json.loads(original_sealer_checkpoint)
        old_sealer_state["authorization_created_at"] = "2000-01-01T00:00:00+00:00"
        sealer_checkpoint.write_text(
            json.dumps(old_sealer_state, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        old_sealer = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert old_sealer["status"] == "blocked"
        assert any(
            item["check_id"] == "completed_remediation_task"
            for item in old_sealer["blockers"]
        )
        sealer_checkpoint.write_text(original_sealer_checkpoint, encoding="utf-8")

        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            admin_rows = connection.execute(
                """
                SELECT symbol, trade_date, status, is_tradable,
                       suspension_reason, expected_resume_date, source,
                       source_observed_at, source_payload_hash, evidence_json
                FROM security_trading_status_daily
                WHERE source='admin_batch_remediation:canonical_positive_bar'
                ORDER BY symbol, trade_date
                """
            ).fetchall()
        admin_by_run = {
            str(json.loads(str(row["evidence_json"]))["run_id"]): dict(row)
            for row in admin_rows
        }
        legacy_row = admin_by_run[first_run]
        completed_row = admin_by_run[second_run]

        # Same-key overwrite without an explicit hashed supersession lineage keeps
        # the older checkpoint in the run universe and must fail the bidirectional
        # checkpoint/manifest/physical comparison.
        overwritten_evidence = json.loads(str(legacy_row["evidence_json"]))
        completed_evidence = json.loads(str(completed_row["evidence_json"]))
        overwritten_evidence["run_id"] = second_run
        overwritten_evidence["candidate_fingerprint"] = completed_evidence[
            "candidate_fingerprint"
        ]
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE security_trading_status_daily SET evidence_json=?
                WHERE symbol=? AND trade_date=?
                """,
                (
                    json.dumps(
                        overwritten_evidence,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    legacy_row["symbol"],
                    legacy_row["trade_date"],
                ),
            )
        overwritten = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert first_run in overwritten["change_set"]["run_ids"]
        assert overwritten["status"] == "blocked"
        assert any(
            item["check_id"] == "remediation_run_evidence_consistency"
            for item in overwritten["blockers"]
        )
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE security_trading_status_daily SET evidence_json=?
                WHERE symbol=? AND trade_date=?
                """,
                (
                    legacy_row["evidence_json"],
                    legacy_row["symbol"],
                    legacy_row["trade_date"],
                ),
            )

        # A disappeared physical row is equally non-consumable: checkpoint-only
        # runs remain in the unpublished universe instead of silently vanishing.
        with sqlite3.connect(database) as connection:
            connection.execute(
                "DELETE FROM security_trading_status_daily WHERE symbol=? AND trade_date=?",
                (legacy_row["symbol"], legacy_row["trade_date"]),
            )
        disappeared = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert first_run in disappeared["change_set"]["run_ids"]
        assert disappeared["status"] == "blocked"
        assert any(
            item["check_id"] == "remediation_run_evidence_consistency"
            for item in disappeared["blockers"]
        )
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                INSERT INTO security_trading_status_daily (
                    symbol, trade_date, status, is_tradable,
                    suspension_reason, expected_resume_date, source,
                    source_observed_at, source_payload_hash, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(legacy_row[column] for column in (
                    "symbol", "trade_date", "status", "is_tradable",
                    "suspension_reason", "expected_resume_date", "source",
                    "source_observed_at", "source_payload_hash", "evidence_json",
                )),
            )

        # A physical candidate fingerprint that no longer belongs to its immutable
        # manifest must block closure before any quality report or release is created.
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                """
                SELECT evidence_json FROM security_trading_status_daily
                WHERE source='admin_batch_remediation:canonical_positive_bar'
                  AND evidence_json LIKE ? LIMIT 1
                """,
                (f'%"run_id":"{second_run}"%',),
            ).fetchone()
            assert row is not None
            original_evidence_json = str(row[0])
            tampered = json.loads(original_evidence_json)
            tampered["candidate_fingerprint"] = "f" * 64
            connection.execute(
                """
                UPDATE security_trading_status_daily SET evidence_json=?
                WHERE source='admin_batch_remediation:canonical_positive_bar'
                  AND evidence_json=?
                """,
                (
                    json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    original_evidence_json,
                ),
            )
        tampered_closure = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert tampered_closure["status"] == "blocked"
        assert any(
            item["check_id"] == "remediation_run_evidence_consistency"
            for item in tampered_closure["blockers"]
        )
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE security_trading_status_daily SET evidence_json=?
                WHERE source='admin_batch_remediation:canonical_positive_bar'
                  AND evidence_json LIKE ?
                """,
                (original_evidence_json, f'%"run_id":"{second_run}"%'),
            )

        closure = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert closure["status"] == "ready", closure["blockers"]
        expected = {
            "expected_base_version_id": closure["base_version"]["data_version_id"],
            "expected_base_manifest_hash": closure["base_version"]["manifest_hash"],
            "expected_change_set_hash": closure["change_set"]["change_set_hash"],
        }
        drifted = _dispatch(
            app,
            "POST",
            "/api/data-center/quality/trading-status-remediation/closure/quick-recheck",
            {**expected, "expected_change_set_hash": "0" * 64},
        )
        assert drifted["status"] == "blocked"
        assert any(
            item["check_id"] == "change_set_drift" for item in drifted["blockers"]
        )
        recheck = _dispatch(
            app,
            "POST",
            "/api/data-center/quality/trading-status-remediation/closure/quick-recheck",
            expected,
        )
        assert recheck["status"] == "passed", recheck["blockers"]
        assert recheck["recheck"]["candidate_count"] == 0
        assert recheck["release"]["status"] == "ready"
        publish_request = {
            **expected,
            "expected_quality_report_id": recheck["recheck"]["quality_report_id"],
            "expected_quality_report_hash": recheck["recheck"]["quality_report_hash"],
            "operator": "qa-release-admin",
            "authorization_reference": "isolated-stage2-correction-release",
            "confirmation": TRADING_STATUS_CORRECTION_CONFIRMATION,
        }

        # Simulate a report mutation after the service's final quick recheck but
        # before the atomic store transaction.  The transaction must compare the
        # expected payload hash and leave the parent published.
        from app.runtime.http_adapter import DispatchError, dispatch_request

        original_atomic_publish = governance.publish_trading_status_correction_version

        def publish_after_report_hash_drift(**kwargs):
            from data_platform.maintenance_transaction import transaction_connection
            with transaction_connection(database) as connection:
                connection.execute(
                    """
                    UPDATE data_quality_reports SET payload_hash=?
                    WHERE quality_report_id=?
                    """,
                    ("f" * 64, kwargs["quality_report_id"]),
                )
            return original_atomic_publish(**kwargs)

        governance.publish_trading_status_correction_version = (
            publish_after_report_hash_drift
        )
        try:
            try:
                dispatch_request(
                    app,
                    method="POST",
                    path="/api/data-center/versions/corrections/publish",
                    body=json.dumps(publish_request).encode("utf-8"),
                )
            except DispatchError as error:
                assert error.status_code == 400
                assert "quality report" in error.message
            else:
                raise AssertionError("quality-report hash drift was not blocked")
            assert governance.fetch_data_version(
                str(base["data_version_id"])
            )["status"] == "published"
            assert (
                governance.fetch_trading_status_remediation_release_bindings()
                == []
            )
        finally:
            governance.publish_trading_status_correction_version = original_atomic_publish
            with sqlite3.connect(database) as connection:
                connection.execute(
                    """
                    UPDATE data_quality_reports SET payload_hash=?
                    WHERE quality_report_id=?
                    """,
                    (
                        recheck["recheck"]["quality_report_hash"],
                        recheck["recheck"]["quality_report_id"],
                    ),
                )

        published = _dispatch(
            app,
            "POST",
            "/api/data-center/versions/corrections/complete",
            {key: value for key, value in publish_request.items() if not key.startswith('expected_quality_')},
        )
        assert published["status"] == "published"
        correction_id = str(published["data_version_id"])
        assert correction_id != base["data_version_id"]
        assert published["release"]["default_changed"] is True
        versions = store.list_versions()
        assert versions["default_version_id"] == correction_id
        assert governance.fetch_data_version(str(base["data_version_id"]))["status"] == "superseded"
        correction = governance.fetch_data_version(correction_id)
        assert correction["status"] == "published"
        release_bindings = (
            governance.fetch_trading_status_remediation_release_bindings()
        )
        assert [item["run_id"] for item in release_bindings] == sorted(
            [first_run, second_run]
        )
        assert all(
            item["consuming_data_version_id"] == correction_id
            and item["change_set_hash"] == expected["expected_change_set_hash"]
            and item["quality_report_id"]
            == recheck["recheck"]["quality_report_id"]
            for item in release_bindings
        )
        base_members = {
            (item["dataset"], item["adjustment"]): item for item in base["members"]
        }
        correction_members = {
            (item["dataset"], item["adjustment"]): item
            for item in correction["members"]
        }
        assert (
            correction_members[("market_daily_prices", "qfq")]["content_hash"]
            == base_members[("market_daily_prices", "qfq")]["content_hash"]
        )
        assert len(
            correction_members[("security_trading_status_daily", "")]["content_hash"]
        ) == 64

        idempotent = _dispatch(
            app,
            "POST",
            "/api/data-center/versions/corrections/publish",
            publish_request,
        )
        assert idempotent["status"] == "already_published"
        assert idempotent["data_version_id"] == correction_id
        assert governance.fetch_data_version(str(base["data_version_id"]))["status"] == "superseded"
        assert store.list_versions()["default_version_id"] == correction_id
        assert (
            governance.fetch_trading_status_remediation_release_bindings()
            == release_bindings
        )

        # The ledger is append-only: a duplicate run with different release
        # evidence conflicts, and an in-place mutation is rejected by a trigger.
        first_binding = release_bindings[0]
        binding_columns = [
            "run_id", "consuming_data_version_id", "change_set_hash",
            "quality_report_id", "run_binding_hash", "checkpoint_hash",
            "candidate_manifest_hash", "written_key_hashes_hash",
            "physical_key_count", "physical_key_fingerprint_hash",
            "physical_row_content_hash", "bound_at",
        ]
        conflicting_binding = dict(first_binding)
        conflicting_binding["change_set_hash"] = "e" * 64
        with sqlite3.connect(database) as connection:
            try:
                connection.execute(
                    f"""
                    INSERT INTO trading_status_remediation_release_bindings (
                        {','.join(binding_columns)}
                    ) VALUES ({','.join('?' for _ in binding_columns)})
                    """,
                    tuple(conflicting_binding[column] for column in binding_columns),
                )
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("conflicting remediation binding was accepted")
            try:
                connection.execute(
                    """
                    UPDATE trading_status_remediation_release_bindings
                    SET change_set_hash=? WHERE run_id=?
                    """,
                    ("d" * 64, first_binding["run_id"]),
                )
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("append-only remediation binding was mutable")

        conflict_change_set_hash = "c" * 64
        conflict_report = governance.save_quality_report(
            quality_report_id="dq-stage2-conflicting-run-consumption",
            rule_version="smoke-conflict-v1",
            status="passed",
            payload={
                "change_set": {
                    "change_set_hash": conflict_change_set_hash,
                    "run_bindings": recheck["change_set"]["run_bindings"],
                },
            },
        )
        conflict_members = []
        for raw_member in correction["members"]:
            details = json.loads(str(raw_member.get("details_json") or "{}"))
            if (
                raw_member["dataset"] == "security_trading_status_daily"
                and raw_member["adjustment"] == ""
            ):
                details = {**details, "conflicting_reconsumption": True}
            conflict_members.append({
                "dataset": raw_member["dataset"],
                "adjustment": raw_member["adjustment"],
                "symbol_scope": raw_member["symbol_scope"],
                "row_count": raw_member["row_count"],
                "symbol_count": raw_member["symbol_count"],
                "min_date": raw_member["min_date"],
                "max_date": raw_member["max_date"],
                "source": raw_member["source"],
                "sync_run_ref": raw_member["sync_run_ref"],
                "content_hash": raw_member["content_hash"],
                "quality_status": raw_member["quality_status"],
                "details": details,
            })
        try:
            governance.publish_trading_status_correction_version(
                as_of_trade_date=str(correction["as_of_trade_date"]),
                quality_report_id=str(conflict_report["quality_report_id"]),
                expected_quality_report_hash=str(conflict_report["payload_hash"]),
                change_set_hash=conflict_change_set_hash,
                run_bindings=recheck["change_set"]["run_bindings"],
                members=conflict_members,
                expected_parent_version_id=correction_id,
                expected_parent_manifest_hash=str(correction["manifest_hash"]),
                expected_trading_status_content_hash=str(
                    correction_members[
                        ("security_trading_status_daily", "")
                    ]["content_hash"]
                ),
                notes="must conflict because the runs were already consumed",
            )
        except ValueError as error:
            assert "already consumed" in str(error)
        else:
            raise AssertionError("different correction re-consumed bound runs")
        assert governance.fetch_current_published_data_version()[
            "data_version_id"
        ] == correction_id
        assert (
            governance.fetch_trading_status_remediation_release_bindings()
            == release_bindings
        )

        # A previously consumed sealer cannot seal a new run universe.  This
        # zero-write terminal run also proves checkpoint lineage is consumable
        # even when the physical key count is zero.
        zero_run_id = "post-release-zero-run-smoke"
        zero_manifest = task_dir / f"{zero_run_id}.json.candidates.jsonl"
        zero_manifest.parent.mkdir(parents=True, exist_ok=True)
        zero_manifest.write_bytes(b"")
        empty_hash = hashlib.sha256(b"").hexdigest()
        zero_checkpoint = task_dir / f"{zero_run_id}.json"
        zero_state = {
            "checkpoint_version": "2",
            "status": "authorization_exhausted",
            "run_id": zero_run_id,
            "operator": "qa-admin",
            "authorized_by": "qa-admin",
            "authorization_reference": "zero-run-lineage-smoke",
            "authorization_created_at": "2099-01-01T00:00:00+00:00",
            "authorized_total_writes": 1,
            "commit_batch_size": 1,
            "database": str(database.resolve()),
            "scope": "all_symbols",
            "expected_candidate_set_hash": empty_hash,
            "expected_candidate_count": 0,
            "candidate_manifest": str(zero_manifest.resolve()),
            "candidate_manifest_file_hash": empty_hash,
            "candidate_manifest_byte_offset": 0,
            "cursor": {"symbol": "", "trade_date": ""},
            "scanned_candidates": 0,
            "auto_candidates_seen": 0,
            "authorization_consumed": 0,
            "manual_candidates_seen": 0,
            "written": 0,
            "newly_written": 0,
            "recovered_written": 0,
            "skipped": 0,
            "evidence_mismatch_skipped": 0,
            "batch_count": 0,
            "batches": [],
            "updated_at": "2099-01-01T00:00:01+00:00",
            "finished_at": "2099-01-01T00:00:01+00:00",
        }
        zero_checkpoint.write_text(
            json.dumps(zero_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        reused_old_sealer = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert reused_old_sealer["change_set"]["run_ids"] == [zero_run_id]
        assert reused_old_sealer["change_set"]["key_count"] == 0
        assert reused_old_sealer["change_set"]["run_count"] == 1
        assert reused_old_sealer["status"] == "blocked"
        assert any(
            item["check_id"] == "completed_remediation_task"
            for item in reused_old_sealer["blockers"]
        )

        zero_state["status"] = "completed"
        zero_state["completion_consistency"] = "matched"
        zero_checkpoint.write_text(
            json.dumps(zero_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        zero_ready = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert zero_ready["status"] == "ready", zero_ready["blockers"]
        assert zero_ready["change_set"]["key_count"] == 0
        assert zero_ready["change_set"]["run_count"] == 1
        zero_recheck = _dispatch(
            app,
            "POST",
            "/api/data-center/quality/trading-status-remediation/closure/quick-recheck",
            {
                "expected_base_version_id": zero_ready["base_version"][
                    "data_version_id"
                ],
                "expected_base_manifest_hash": zero_ready["base_version"][
                    "manifest_hash"
                ],
                "expected_change_set_hash": zero_ready["change_set"][
                    "change_set_hash"
                ],
            },
        )
        assert zero_recheck["status"] == "passed", zero_recheck["blockers"]
        assert zero_recheck["change_set"]["key_count"] == 0
        assert zero_recheck["change_set"]["run_count"] == 1
        zero_checkpoint.unlink()

        after = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert after["status"] == "no_changes", after["blockers"]
        assert after["release"]["status"] == "published"
        store.set_default_version(correction_id)
        assert store.list_versions()["default_version_id"] == correction_id

        # Raw filename inventory must not silently discard an unreadable
        # checkpoint merely because it has no current physical rows.
        damaged_run_id = "damaged-zero-physical-smoke"
        damaged_checkpoint = task_dir / f"{damaged_run_id}.json"
        damaged_checkpoint.write_text("{not-valid-json", encoding="utf-8")
        damaged = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert damaged_run_id in damaged["change_set"]["run_ids"]
        assert damaged["status"] == "blocked"
        assert any(
            item["check_id"] == "remediation_checkpoint_unreadable"
            for item in damaged["blockers"]
        )
        damaged_checkpoint.unlink()

        # A later ordinary data release intentionally removes the correction's
        # member-detail audit copy.  The durable ledger must still prevent the
        # already-consumed remediation runs from being revived.
        generic_report = governance.save_quality_report(
            quality_report_id="dq-stage2-generic-after-correction",
            rule_version="smoke-generic-v1",
            status="passed",
            payload={"fixture": "generic-release-after-status-correction"},
        )
        generic_members = []
        for raw_member in correction["members"]:
            details = json.loads(str(raw_member.get("details_json") or "{}"))
            if (
                raw_member["dataset"] == "security_trading_status_daily"
                and raw_member["adjustment"] == ""
            ):
                details = {"fixture": "generic-release-without-closure-copy"}
            generic_members.append({
                "dataset": raw_member["dataset"],
                "adjustment": raw_member["adjustment"],
                "symbol_scope": raw_member["symbol_scope"],
                "row_count": raw_member["row_count"],
                "symbol_count": raw_member["symbol_count"],
                "min_date": raw_member["min_date"],
                "max_date": raw_member["max_date"],
                "source": raw_member["source"],
                "sync_run_ref": "generic-after-correction-smoke",
                "content_hash": raw_member["content_hash"],
                "quality_status": "passed",
                "details": details,
            })
        generic = governance.publish_data_version(
            as_of_trade_date="2026-08-17",
            quality_report_id=str(generic_report["quality_report_id"]),
            members=generic_members,
            notes="ordinary release after status correction",
        )
        assert generic["data_version_id"] != correction_id
        ledger_after_generic = _dispatch(
            app,
            "GET",
            "/api/data-center/quality/trading-status-remediation/closure",
        )
        assert ledger_after_generic["status"] == "no_changes", (
            ledger_after_generic["blockers"]
        )
        assert ledger_after_generic["base_closure_details"] == {}
        assert ledger_after_generic["consumed_run_ids"] == sorted(
            [first_run, second_run]
        )
        assert ledger_after_generic["change_set"]["run_ids"] == []
        assert ledger_after_generic["change_set"]["run_count"] == 0
        assert (
            governance.fetch_trading_status_remediation_release_bindings()
            == release_bindings
        )

    print("stage2 status remediation closure API smoke passed")


if __name__ == "__main__":
    main()
