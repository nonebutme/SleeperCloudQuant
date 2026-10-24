"""Isolated Web/API lifecycle test for trading-status remediation tasks."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


class _NoWriteProvider:
    def sync_symbol(self, *_args, **_kwargs):
        raise AssertionError("Web/API remediation smoke must not call an upstream provider")


def _price(symbol: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "trade_date": "2026-08-17",
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10,
        "volume": 100,
        "amount": 1_000,
    }


def _build_fixture(root: Path, name: str, symbols: tuple[str, ...]):
    from app.api.data_center import build_data_center_routes
    from app.main import SimpleApiApp
    from app.services.data_center_service import DataCenterService
    from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
    from data_platform.storage.data_center_store import DataCenterStore

    database = root / f"{name}.sqlite3"
    market = AShareMarketStore(database)
    governance = AShareGovernanceStore(database)
    market.ensure_schema()
    governance.ensure_schema()
    market.upsert_symbols([
        {"symbol": symbol, "name": f"fixture-{symbol}", "source": "web-api-smoke"}
        for symbol in symbols
    ])
    for symbol in symbols:
        market.upsert_daily_prices(
            [_price(symbol)], adjustment="qfq", source="web-api-smoke",
        )
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
    task_dir = root / f"{name}-tasks"
    service = DataCenterService(
        DataCenterStore(database), scheduler, governance,
        trading_status_remediation_dir=task_dir,
    )
    app = SimpleApiApp(
        title=f"trading-status-remediation-{name}",
        routes=build_data_center_routes(service),
    )
    return database, governance, scheduler, task_dir, service, app


def _poll_task(app, run_id: str) -> dict:
    from app.runtime.http_adapter import dispatch_request

    for _ in range(500):
        status, payload = dispatch_request(
            app,
            method="GET",
            path=(
                "/api/data-center/quality/trading-status-remediation/tasks/"
                f"{run_id}"
            ),
        )
        assert status == 200
        task = payload["result"]
        if task["status"] in {"completed", "authorization_exhausted", "failed"}:
            return task
        time.sleep(0.01)
    raise AssertionError(f"remediation worker did not finish: {run_id}: {task}")


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.api.data_center import build_data_center_routes
    from app.main import SimpleApiApp
    from app.runtime.http_adapter import DispatchError, dispatch_request
    from app.services.data_center_service import DataCenterService
    import app.services.data_center_service as service_module
    from data_platform.storage.data_center_store import DataCenterStore
    from scripts.apply_trading_status_semantic_remediation import (
        CONFIRMATION_PHRASE,
        acquire_trading_status_database_lease,
        inspect_trading_status_database_lease,
        prepare_batch_remediation,
        request_batch_pause,
    )

    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(
        prefix="scq-status-web-api-", dir=project_root / "tmp",
        ignore_cleanup_errors=True,
    ) as temporary:
        root = Path(temporary)

        database, governance, _scheduler, task_dir, service, app = _build_fixture(
            root, "background", ("000101", "000102", "000103"),
        )
        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/data-center/quality/trading-status-remediation/preview",
            body=b"{}",
        )
        assert status == 200
        preview = payload["result"]
        assert preview["scope"] == "all_symbols"
        assert preview["writes"] == 0
        assert preview["apply_supported"] is True
        assert preview["task_start_supported"] is True
        assert preview["task_execution_mode"] == "background_v2"
        assert "authorization_reference" in preview["next_authorization_required"]
        assert preview["max_authorized_total_writes"] == 1_000_000
        assert preview["max_commit_batch_size"] == 1_000

        start_body = {
            "expected_candidate_set_hash": preview["candidate_set_hash"],
            "run_id": "web-background",
            "operator": "qa-admin",
            "confirmation": CONFIRMATION_PHRASE,
            "scope": "all_symbols",
            "authorized_total_writes": 2,
            "commit_batch_size": 1,
            "authorization_reference": "isolated-web-api-smoke",
        }
        status, payload = dispatch_request(
            app,
            method="POST",
            path="/api/data-center/quality/trading-status-remediation/start",
            body=json.dumps(start_body).encode("utf-8"),
        )
        assert status == 200
        assert payload["result"]["execution"]["status"] in {
            "dispatched", "already_running",
        }
        status, immediate = dispatch_request(
            app,
            method="GET",
            path=(
                "/api/data-center/quality/trading-status-remediation/tasks/"
                "web-background"
            ),
        )
        assert status == 200 and immediate["result"]["run_id"] == "web-background"
        finished = _poll_task(app, "web-background")
        assert finished["status"] == "authorization_exhausted"
        assert finished["authorized_total_writes"] == 2
        assert finished["authorization_consumed"] == 2
        assert finished["written"] == 2
        assert finished["commit_batch_size"] == 1
        assert finished["scope"] == "all_symbols"
        assert finished["authorization_reference"] == "isolated-web-api-smoke"
        status, payload = dispatch_request(
            app,
            method="GET",
            path="/api/data-center/quality/trading-status-remediation/tasks",
        )
        assert status == 200
        assert payload["items"][0]["run_id"] == "web-background"
        status, payload = dispatch_request(
            app,
            method="GET",
            path="/api/data-center/quality/trading-status-remediation",
        )
        assert status == 200 and payload["items"][0]["run_id"] == "web-background"

        # A worker failure before the first checkpoint remains a visible failed
        # task and can explicitly retry the frozen request after recovery.
        (
            failure_database,
            failure_governance,
            _,
            failure_dir,
            failure_service,
            failure_app,
        ) = _build_fixture(root, "precheckpoint-failure", ("000151",))
        failure_preview = failure_service.preview_trading_status_batch_remediation()
        failure_body = {
            "expected_candidate_set_hash": failure_preview["candidate_set_hash"],
            "run_id": "precheckpoint-failure",
            "operator": "qa-admin",
            "confirmation": CONFIRMATION_PHRASE,
            "scope": "all_symbols",
            "authorized_total_writes": 1,
            "commit_batch_size": 1,
            "authorization_reference": "precheckpoint-failure-smoke",
        }
        original_failure_prepare = service_module.prepare_batch_remediation
        failure_attempts = 0

        def fail_first_prepare(*args, **kwargs):
            nonlocal failure_attempts
            failure_attempts += 1
            if failure_attempts == 1:
                raise RuntimeError("synthetic pre-checkpoint prepare failure")
            return original_failure_prepare(*args, **kwargs)

        service_module.prepare_batch_remediation = fail_first_prepare
        try:
            status, payload = dispatch_request(
                failure_app,
                method="POST",
                path="/api/data-center/quality/trading-status-remediation/tasks",
                body=json.dumps(failure_body).encode("utf-8"),
            )
            assert status == 200
            failed = _poll_task(failure_app, "precheckpoint-failure")
            assert failed["status"] == "failed"
            assert "synthetic pre-checkpoint prepare failure" in failed["last_error"]
            assert failed["authorized_total_writes"] == 1
            assert failed["commit_batch_size"] == 1
            assert failed["expected_candidate_set_hash"] == (
                failure_preview["candidate_set_hash"]
            )
            assert not (failure_dir / "precheckpoint-failure.json").exists()
            assert failure_governance.fetch_trading_status_history(
                "000151"
            )[0]["is_tradable"] is None
            for _ in range(100):
                if failure_service._trading_status_worker_execution(
                    "precheckpoint-failure"
                )["status"] == "idle":
                    break
                time.sleep(0.01)
            else:
                raise AssertionError("failed pre-checkpoint worker did not exit")

            status, detail = dispatch_request(
                failure_app,
                method="GET",
                path=(
                    "/api/data-center/quality/trading-status-remediation/tasks/"
                    "precheckpoint-failure"
                ),
            )
            assert status == 200
            assert detail["result"]["status"] == "failed"
            assert "synthetic pre-checkpoint prepare failure" in (
                detail["result"]["last_error"]
            )
            status, collection = dispatch_request(
                failure_app,
                method="GET",
                path="/api/data-center/quality/trading-status-remediation/tasks",
            )
            assert status == 200
            listed_failure = next(
                item for item in collection["items"]
                if item["run_id"] == "precheckpoint-failure"
            )
            assert listed_failure["status"] == "failed"
            assert "synthetic pre-checkpoint prepare failure" in (
                listed_failure["last_error"]
            )

            status, payload = dispatch_request(
                failure_app,
                method="POST",
                path=(
                    "/api/data-center/quality/trading-status-remediation/tasks/"
                    "precheckpoint-failure/resume"
                ),
                body=json.dumps({"confirmation": CONFIRMATION_PHRASE}).encode("utf-8"),
            )
            assert status == 200
            assert payload["result"]["execution"]["status"] in {
                "dispatched", "already_running",
            }
            recovered = _poll_task(failure_app, "precheckpoint-failure")
            assert recovered["status"] in {"completed", "authorization_exhausted"}
            assert recovered["written"] == 1
            assert recovered["authorization_consumed"] == 1
            assert (failure_dir / "precheckpoint-failure.json").is_file()
            assert failure_governance.fetch_trading_status_history(
                "000151"
            )[0]["is_tradable"] == 1
            assert Path(failure_database).is_file()
        finally:
            service_module.prepare_batch_remediation = original_failure_prepare
        assert failure_attempts == 2

        for bad_body, expected_message in (
            ({**start_body, "run_id": "missing-reference-small", "authorized_total_writes": 1,
              "authorization_reference": ""}, "authorization_reference"),
            ({**start_body, "run_id": "missing-reference", "authorized_total_writes": 1_001,
              "authorization_reference": ""}, "authorization_reference"),
            ({**start_body, "run_id": "total-too-large", "authorized_total_writes": 1_000_001},
             "between 1 and 1000000"),
            ({**start_body, "run_id": "batch-too-large", "commit_batch_size": 1_001},
             "between 1 and 1000"),
        ):
            try:
                dispatch_request(
                    app,
                    method="POST",
                    path="/api/data-center/quality/trading-status-remediation/tasks",
                    body=json.dumps(bad_body).encode("utf-8"),
                )
            except DispatchError as error:
                assert error.status_code == 400 and expected_message in error.message
            else:
                raise AssertionError(f"invalid task must be rejected: {bad_body['run_id']}")

        # The public /apply alias must never reach the synchronous legacy writer.
        _, _, _, _, legacy_service, legacy_app = _build_fixture(
            root, "legacy", ("000201", "000202"),
        )
        legacy_preview = legacy_service.preview_trading_status_batch_remediation(
            scope="current_symbols",
        )
        try:
            dispatch_request(
                legacy_app,
                method="POST",
                path="/api/data-center/quality/trading-status-remediation/apply",
                body=json.dumps({
                    "expected_candidate_set_hash": legacy_preview["candidate_set_hash"],
                    "run_id": "legacy-apply",
                    "operator": "qa-admin",
                    "confirmation": CONFIRMATION_PHRASE,
                    "max_writes": 1,
                }).encode("utf-8"),
            )
        except DispatchError as error:
            assert error.status_code == 400 and "authorized_total_writes" in error.message
        else:
            raise AssertionError("legacy /apply payload must not authorize a synchronous write")
        assert not legacy_service._trading_status_batch_checkpoint("legacy-apply").exists()
        assert all(
            row["is_tradable"] is None
            for symbol in ("000201", "000202")
            for row in legacy_service.governance_store.fetch_trading_status_history(symbol)
        )

        alias_body = {
            "expected_candidate_set_hash": legacy_preview["candidate_set_hash"],
            "run_id": "apply-alias-v2",
            "operator": "qa-admin",
            "confirmation": CONFIRMATION_PHRASE,
            "scope": "all_symbols",
            "authorized_total_writes": 1,
            "commit_batch_size": 1,
            "authorization_reference": "isolated-apply-alias-smoke",
        }
        status, payload = dispatch_request(
            legacy_app,
            method="POST",
            path="/api/data-center/quality/trading-status-remediation/apply",
            body=json.dumps(alias_body).encode("utf-8"),
        )
        assert status == 200
        assert payload["result"]["execution"]["status"] == "dispatched"
        alias_finished = _poll_task(legacy_app, "apply-alias-v2")
        assert alias_finished["status"] == "authorization_exhausted"
        assert alias_finished["authorized_total_writes"] == 1
        assert alias_finished["written"] == 1
        assert alias_finished["authorization_reference"] == "isolated-apply-alias-smoke"

        # Pause/resume uses the frozen checkpoint and never accepts replacement limits.
        pause_database, _, _, pause_dir, pause_service, pause_app = _build_fixture(
            root, "pause", ("000301", "000302"),
        )
        pause_preview = pause_service.preview_trading_status_batch_remediation()
        pause_checkpoint = pause_dir / "pause-resume.json"
        prepared = prepare_batch_remediation(
            pause_database,
            expected_candidate_set_hash=pause_preview["candidate_set_hash"],
            run_id="pause-resume",
            operator="qa-admin",
            checkpoint_path=pause_checkpoint,
            confirmation=CONFIRMATION_PHRASE,
            current_symbols_only=False,
            authorized_total_writes=2,
            commit_batch_size=1,
            authorization_reference="pause-resume-smoke",
        )
        assert prepared["status"] == "queued"
        checkpoint_before_bad_resume = pause_checkpoint.read_bytes()
        status_before_bad_resume = pause_service.governance_store.fetch_trading_status_history(
            "000301"
        )[0]
        for bad_confirmation in ("", "WRONG_CONFIRMATION"):
            try:
                dispatch_request(
                    pause_app,
                    method="POST",
                    path=(
                        "/api/data-center/quality/trading-status-remediation/tasks/"
                        "pause-resume/resume"
                    ),
                    body=json.dumps({"confirmation": bad_confirmation}).encode("utf-8"),
                )
            except DispatchError as error:
                assert error.status_code == 400 and "confirmation phrase" in error.message
            else:
                raise AssertionError("resume must require the exact confirmation phrase")
        assert pause_checkpoint.read_bytes() == checkpoint_before_bad_resume
        assert pause_service.governance_store.fetch_trading_status_history("000301")[0] == (
            status_before_bad_resume
        )
        status, payload = dispatch_request(
            pause_app,
            method="POST",
            path=(
                "/api/data-center/quality/trading-status-remediation/tasks/"
                "pause-resume/pause"
            ),
        )
        checkpoint_before_pause = pause_checkpoint.read_bytes()
        assert status == 200 and payload["result"]["status"] == "paused_by_user"
        assert pause_checkpoint.read_bytes() == checkpoint_before_pause
        immediate_paused = pause_service.get_trading_status_batch_remediation(
            "pause-resume"
        )
        assert immediate_paused["status"] == "paused_by_user"
        assert immediate_paused["pause_requested"] is True
        listed_paused = {
            item["run_id"]: item
            for item in pause_service.list_trading_status_batch_remediations()
        }["pause-resume"]
        assert listed_paused["status"] == "paused_by_user"
        assert listed_paused["pause_requested"] is True
        status, payload = dispatch_request(
            pause_app,
            method="POST",
            path=(
                "/api/data-center/quality/trading-status-remediation/tasks/"
                "pause-resume/resume"
            ),
            body=json.dumps({"confirmation": CONFIRMATION_PHRASE}).encode("utf-8"),
        )
        assert status == 200
        assert payload["result"]["execution"]["status"] in {
            "dispatched", "already_running",
        }
        assert _poll_task(pause_app, "pause-resume")["status"] == "completed"

        # Pending identity is immutable before the first checkpoint exists, and the
        # same database slot rejects both another background task and legacy apply.
        blocked_resume_preview = service.preview_trading_status_batch_remediation()
        blocked_resume_checkpoint = task_dir / "blocked-resume.json"
        prepare_batch_remediation(
            database,
            expected_candidate_set_hash=blocked_resume_preview["candidate_set_hash"],
            run_id="blocked-resume",
            operator="qa-admin",
            checkpoint_path=blocked_resume_checkpoint,
            confirmation=CONFIRMATION_PHRASE,
            current_symbols_only=False,
            authorized_total_writes=1,
            commit_batch_size=1,
            authorization_reference="blocked-resume-smoke",
        )
        assert request_batch_pause(blocked_resume_checkpoint)["status"] == "paused_by_user"
        blocked_resume_before = blocked_resume_checkpoint.read_bytes()
        worker_started = threading.Event()
        release_worker = threading.Event()
        original_prepare = service_module.prepare_batch_remediation
        original_runner = service_module.run_batch_remediation

        def blocking_prepare(*_args, **_kwargs):
            worker_started.set()
            assert release_worker.wait(5)
            return {"status": "queued"}

        def completed_runner(*_args, **_kwargs):
            return {"status": "completed"}

        service_module.prepare_batch_remediation = blocking_prepare
        service_module.run_batch_remediation = completed_runner
        try:
            first_hash = "a" * 64
            first = service.start_trading_status_batch_remediation(
                expected_candidate_set_hash=first_hash,
                run_id="single-worker-a",
                operator="qa-admin",
                confirmation=CONFIRMATION_PHRASE,
                scope="all_symbols",
                authorized_total_writes=1,
                commit_batch_size=1,
                authorization_reference="single-worker-smoke",
            )
            assert first["execution"]["status"] == "dispatched"
            assert worker_started.wait(5)
            assert not service._trading_status_batch_checkpoint("single-worker-a").exists()
            precheckpoint_lease = inspect_trading_status_database_lease(database)
            assert precheckpoint_lease["status"] == "busy"
            assert precheckpoint_lease["owner"]["run_id"] == "single-worker-a"
            frozen_pending = service.get_trading_status_batch_remediation("single-worker-a")
            assert frozen_pending["status"] == "initializing"
            assert frozen_pending["expected_candidate_set_hash"] == first_hash
            assert frozen_pending["authorized_total_writes"] == 1
            assert frozen_pending["commit_batch_size"] == 1
            assert "single-worker-a" in {
                item["run_id"] for item in service.list_trading_status_batch_remediations()
            }
            try:
                service.start_trading_status_batch_remediation(
                    expected_candidate_set_hash="b" * 64,
                    run_id="single-worker-a",
                    operator="other-admin",
                    confirmation=CONFIRMATION_PHRASE,
                    scope="current_symbols",
                    authorized_total_writes=2,
                    commit_batch_size=2,
                    authorization_reference="must-not-replace-first",
                )
            except ValueError as error:
                assert "already initializing" in str(error)
            else:
                raise AssertionError("same run_id must not replace pending frozen parameters")
            unchanged_pending = service.get_trading_status_batch_remediation("single-worker-a")
            assert unchanged_pending["expected_candidate_set_hash"] == first_hash
            assert unchanged_pending["authorized_total_writes"] == 1
            assert unchanged_pending["operator"] == "qa-admin"
            assert unchanged_pending["scope"] == "all_symbols"
            try:
                service.start_trading_status_batch_remediation(
                    expected_candidate_set_hash="c" * 64,
                    run_id="single-worker-b",
                    operator="qa-admin",
                    confirmation=CONFIRMATION_PHRASE,
                    scope="all_symbols",
                    authorized_total_writes=1,
                    commit_batch_size=1,
                    authorization_reference="single-worker-smoke",
                )
            except ValueError as error:
                assert "another trading status remediation task" in str(error)
            else:
                raise AssertionError("one database must not dispatch two remediation workers")
            assert "single-worker-b" not in service._trading_status_pending_tasks
            try:
                service.resume_trading_status_batch_remediation(
                    "blocked-resume", confirmation=CONFIRMATION_PHRASE,
                )
            except ValueError as error:
                assert "another trading status remediation task" in str(error)
            else:
                raise AssertionError("a rejected resume must not clear its durable pause")
            assert blocked_resume_checkpoint.read_bytes() == blocked_resume_before
            assert service.get_trading_status_batch_remediation(
                "blocked-resume"
            )["status"] == "paused_by_user"
            try:
                service.apply_trading_status_batch_remediation(
                    expected_candidate_set_hash="d" * 64,
                    run_id="legacy-during-background",
                    operator="qa-admin",
                    confirmation=CONFIRMATION_PHRASE,
                    max_writes=1,
                )
            except ValueError as error:
                assert "another trading status remediation task" in str(error)
            else:
                raise AssertionError("legacy apply must not overlap a background worker")
        finally:
            release_worker.set()
            service_module.prepare_batch_remediation = original_prepare
            service_module.run_batch_remediation = original_runner
        for _ in range(100):
            if service._trading_status_worker_execution("single-worker-a")["status"] == "idle":
                break
            time.sleep(0.01)

        # The inverse direction is also protected: a synchronous legacy apply owns
        # the database worker slot until it returns.
        _, _, _, _, legacy_slot_service, _ = _build_fixture(
            root, "legacy-slot", ("000351",),
        )
        legacy_slot_preview = legacy_slot_service.preview_trading_status_batch_remediation(
            scope="current_symbols",
        )
        legacy_started = threading.Event()
        release_legacy = threading.Event()
        legacy_result: dict[str, object] = {}

        def blocking_legacy_runner(*_args, **kwargs):
            legacy_started.set()
            assert release_legacy.wait(5)
            return {
                "checkpoint_version": "2",
                "status": "authorization_exhausted",
                "run_id": kwargs["run_id"],
                "database": str(legacy_slot_service.governance_store.database_path),
                "scope": "current_symbols",
                "authorized_total_writes": 1,
                "authorization_consumed": 1,
                "written": 1,
            }

        def run_blocked_legacy() -> None:
            try:
                legacy_result["result"] = (
                    legacy_slot_service.apply_trading_status_batch_remediation(
                        expected_candidate_set_hash=legacy_slot_preview["candidate_set_hash"],
                        run_id="legacy-owns-slot",
                        operator="qa-admin",
                        confirmation=CONFIRMATION_PHRASE,
                        max_writes=1,
                    )
                )
            except Exception as error:  # pragma: no cover - asserted below
                legacy_result["error"] = error

        service_module.run_batch_remediation = blocking_legacy_runner
        legacy_thread = threading.Thread(target=run_blocked_legacy, daemon=True)
        try:
            legacy_thread.start()
            assert legacy_started.wait(5)
            try:
                legacy_slot_service.start_trading_status_batch_remediation(
                    expected_candidate_set_hash=legacy_slot_preview["candidate_set_hash"],
                    run_id="background-during-legacy",
                    operator="qa-admin",
                    confirmation=CONFIRMATION_PHRASE,
                    scope="current_symbols",
                    authorized_total_writes=1,
                    commit_batch_size=1,
                    authorization_reference="legacy-slot-smoke",
                )
            except ValueError as error:
                assert "another trading status remediation task" in str(error)
            else:
                raise AssertionError("background start must not overlap legacy apply")
            assert "background-during-legacy" not in (
                legacy_slot_service._trading_status_pending_tasks
            )
        finally:
            release_legacy.set()
            legacy_thread.join(5)
            service_module.run_batch_remediation = original_runner
        assert not legacy_thread.is_alive()
        assert "error" not in legacy_result

        # A worker exception is still diagnosed when its pending entry vanished;
        # cleanup must release the lease instead of raising a secondary TypeError.
        no_pending_database, _, _, no_pending_dir, no_pending_service, _ = _build_fixture(
            root, "no-pending", ("000399",),
        )
        no_pending_run_id = "no-pending-worker"
        no_pending_lease = acquire_trading_status_database_lease(
            no_pending_database,
            run_id=no_pending_run_id,
            holder_kind="web_api_no_pending_smoke",
        )

        def fail_without_pending(*_args, **_kwargs):
            raise RuntimeError("synthetic no-pending failure")

        service_module.prepare_batch_remediation = fail_without_pending
        try:
            no_pending_service._run_trading_status_worker(
                str(no_pending_database.resolve()),
                {
                    "expected_candidate_set_hash": "e" * 64,
                    "run_id": no_pending_run_id,
                    "operator": "qa-admin",
                    "confirmation": CONFIRMATION_PHRASE,
                    "scope": "all_symbols",
                    "authorized_total_writes": 1,
                    "commit_batch_size": 1,
                    "authorization_reference": "no-pending-smoke",
                },
                no_pending_lease,
            )
        finally:
            service_module.prepare_batch_remediation = original_prepare
        assert no_pending_lease.active is False
        assert no_pending_service._trading_status_worker_errors[no_pending_run_id] == (
            "RuntimeError: synthetic no-pending failure"
        )
        assert not (no_pending_dir / f"{no_pending_run_id}.json").exists()
        assert inspect_trading_status_database_lease(no_pending_database)[
            "status"
        ] == "available"

        # Startup recovery marks only stale v2 state failed and performs no data write.
        recovery_database, recovery_governance, recovery_scheduler, recovery_dir, recovery_service, _ = (
            _build_fixture(root, "recovery", ("000401",))
        )
        recovery_preview = recovery_service.preview_trading_status_batch_remediation()
        recovery_checkpoint = recovery_dir / "stale-queued.json"
        prepare_batch_remediation(
            recovery_database,
            expected_candidate_set_hash=recovery_preview["candidate_set_hash"],
            run_id="stale-queued",
            operator="qa-admin",
            checkpoint_path=recovery_checkpoint,
            confirmation=CONFIRMATION_PHRASE,
            current_symbols_only=False,
            authorized_total_writes=1,
            commit_batch_size=1,
            authorization_reference="startup-recovery-smoke",
        )
        paused_checkpoint = recovery_dir / "persisted-pause.json"
        prepare_batch_remediation(
            recovery_database,
            expected_candidate_set_hash=recovery_preview["candidate_set_hash"],
            run_id="persisted-pause",
            operator="qa-admin",
            checkpoint_path=paused_checkpoint,
            confirmation=CONFIRMATION_PHRASE,
            current_symbols_only=False,
            authorized_total_writes=1,
            commit_batch_size=1,
            authorization_reference="startup-paused-smoke",
        )
        assert request_batch_pause(paused_checkpoint)["status"] == "paused_by_user"
        paused_before = paused_checkpoint.read_bytes()
        legacy_checkpoint = recovery_dir / "legacy-v1.json"
        legacy_checkpoint.write_text(json.dumps({
            "checkpoint_version": "1",
            "run_id": "legacy-v1",
            "status": "paused_max_writes",
            "database": str(recovery_database.resolve()),
        }), encoding="utf-8")
        legacy_before = legacy_checkpoint.read_bytes()
        stale_before_external_start = recovery_checkpoint.read_bytes()
        external_ready = root / "external-recovery-ready.json"
        external_holder = subprocess.Popen(
            [
                sys.executable, "-B",
                str(project_root / "scripts" / "smoke_test_trading_status_semantic_repair.py"),
                "--hold-database-lease", str(recovery_database),
                "stale-queued", str(external_ready),
            ],
            cwd=str(project_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            for _ in range(500):
                if external_ready.is_file():
                    break
                if external_holder.poll() is not None:
                    _, child_error = external_holder.communicate(timeout=1)
                    raise AssertionError(
                        f"external recovery holder exited before ready: {child_error}"
                    )
                time.sleep(0.01)
            assert external_ready.is_file()
            live_peer = DataCenterService(
                DataCenterStore(recovery_database),
                recovery_scheduler,
                recovery_governance,
                trading_status_remediation_dir=recovery_dir,
            )
            assert recovery_checkpoint.read_bytes() == stale_before_external_start
            live_state = live_peer.get_trading_status_batch_remediation("stale-queued")
            assert live_state["status"] == "queued"
            assert live_state["execution"]["status"] == "running"
            assert live_state["execution"]["process_scope"] == "external"
            try:
                live_peer.resume_trading_status_batch_remediation(
                    "persisted-pause", confirmation=CONFIRMATION_PHRASE,
                )
            except ValueError as error:
                assert "database lease is busy" in str(error)
            else:
                raise AssertionError("an external holder must block another run resume")
            assert paused_checkpoint.read_bytes() == paused_before
            assert live_peer.get_trading_status_batch_remediation(
                "persisted-pause"
            )["status"] == "paused_by_user"
        finally:
            if external_holder.poll() is None:
                external_holder.kill()
            external_holder.wait(timeout=10)
        for _ in range(500):
            if inspect_trading_status_database_lease(recovery_database)[
                "status"
            ] == "available":
                break
            time.sleep(0.01)
        assert inspect_trading_status_database_lease(recovery_database)[
            "status"
        ] == "available"

        restarted = DataCenterService(
            DataCenterStore(recovery_database),
            recovery_scheduler,
            recovery_governance,
            trading_status_remediation_dir=recovery_dir,
        )
        interrupted = restarted.get_trading_status_batch_remediation("stale-queued")
        assert interrupted["status"] == "failed"
        assert interrupted["interruption_count"] == 1
        assert interrupted["last_interruption"]["prior_status"] == "queued"
        assert paused_checkpoint.read_bytes() == paused_before
        assert restarted.get_trading_status_batch_remediation(
            "persisted-pause"
        )["status"] == "paused_by_user"
        assert legacy_checkpoint.read_bytes() == legacy_before
        assert restarted.get_trading_status_batch_remediation("legacy-v1")["read_only"] is True
        history = recovery_governance.fetch_trading_status_history("000401")
        assert history[0]["is_tradable"] is None

        # Both detail aliases are registered and resolve to the same frozen state.
        recovery_app = SimpleApiApp(
            title="trading-status-recovery",
            routes=build_data_center_routes(restarted),
        )
        status, payload = dispatch_request(
            recovery_app,
            method="GET",
            path="/api/data-center/quality/trading-status-remediation/stale-queued",
        )
        assert status == 200 and payload["result"]["status"] == "failed"

    print("trading status remediation Web/API smoke passed")


if __name__ == "__main__":
    main()
