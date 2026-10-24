"""Deterministic suspension mapping and governed status-repair smoke test."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

from _project_bootstrap import ensure_project_root_on_sys_path


class _Frame:
    def __init__(self, rows):
        self._rows = list(rows)

    def to_dict(self, _orient):
        return list(self._rows)


class _NoWriteProvider:
    def sync_symbol(self, *_args, **_kwargs):
        raise AssertionError("status repair smoke must not call an upstream provider")


def _hold_database_lease_child(
    database: Path, run_id: str, ready_path: Path,
) -> None:
    ensure_project_root_on_sys_path()
    from scripts.apply_trading_status_semantic_remediation import (
        acquire_trading_status_database_lease,
    )

    lease = acquire_trading_status_database_lease(
        database, run_id=run_id, holder_kind="subprocess_smoke",
    )
    try:
        ready_path.write_text(
            json.dumps(lease.owner, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        sys.stdin.readline()
    finally:
        lease.release()


def _price(symbol: str, trade_date: str) -> dict[str, object]:
    return {
        "symbol": symbol, "trade_date": trade_date,
        "open": 10, "high": 11, "low": 9, "close": 10,
        "volume": 100, "amount": 1_000,
    }


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.api.data_center import build_data_center_routes
    from app.main import SimpleApiApp
    from app.runtime.http_adapter import DispatchError, dispatch_request
    from app.services.data_center_service import DataCenterService
    from data_platform import AShareGovernanceStore, AShareMarketStore, AShareSyncScheduler
    from data_platform.providers.akshare_governance_provider import AkshareGovernanceProvider
    from data_platform.storage.data_center_store import DataCenterStore
    import scripts.apply_trading_status_semantic_remediation as remediation_runner
    from scripts.apply_trading_status_semantic_remediation import (
        CONFIRMATION_PHRASE,
        MAX_AUTHORIZED_TOTAL_WRITES,
        TradingStatusDatabaseLeaseBusyError,
        acquire_trading_status_database_lease,
        clear_batch_pause,
        inspect_trading_status_database_lease,
        mark_batch_interrupted,
        prepare_batch_remediation,
        request_batch_pause,
        run_batch_remediation,
    )
    from scripts.preview_trading_status_semantic_remediation import build_preview_report

    # 上游返回列表可能同时含未来停牌和已复牌记录；只保留目标日确实处于区间内的记录。
    provider = AkshareGovernanceProvider(retry_count=1, retry_delay_seconds=0)
    provider._retry = lambda _operation: _Frame([
        {
            "代码": "000001", "名称": "future", "停牌时间": "2026-08-20",
            "停牌截止时间": "2026-08-26", "预计复牌时间": "2026-08-27",
        },
        {
            "代码": "000002", "名称": "resumed", "停牌时间": "2026-08-03",
            "停牌截止时间": "2026-08-09", "预计复牌时间": "2026-08-10",
        },
        {
            "代码": "000003", "名称": "active", "停牌时间": "2026-08-15",
            "停牌截止时间": "2026-08-19", "预计复牌时间": "2026-08-20",
        },
    ])
    suspension_rows = provider.fetch_suspensions(trade_date="2026-08-17")
    assert [row["symbol"] for row in suspension_rows] == ["000003"]
    assert suspension_rows[0]["trade_date"] == "2026-08-17"
    assert suspension_rows[0]["evidence"]["source_suspension_start_date"] == "2026-08-15"

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(
        prefix="scq-status-repair-", dir=root / "tmp", ignore_cleanup_errors=True,
    ) as temporary:
        database = Path(temporary) / "market.sqlite3"
        market = AShareMarketStore(database)
        governance = AShareGovernanceStore(database)
        scheduler = AShareSyncScheduler(
            database, market_store=market, governance_store=governance,
            provider=_NoWriteProvider(), max_workers=1, retry_count=1,
        )
        scheduler.ensure_schema()
        store = DataCenterStore(database)
        service = DataCenterService(store, scheduler, governance)
        app = SimpleApiApp(
            title="trading-status-repair-smoke",
            routes=build_data_center_routes(service),
        )
        market.upsert_symbols([
            {"symbol": "000001", "name": "unknown", "source": "smoke"},
            {"symbol": "000002", "name": "mapped future", "source": "smoke"},
            {"symbol": "000003", "name": "explicit conflict", "source": "smoke"},
        ])
        for symbol in ("000001", "000002", "000003"):
            market.upsert_daily_prices(
                [_price(symbol, "2026-08-17")], adjustment="qfq", source="smoke",
            )
        governance.upsert_trading_statuses([
            {
                "symbol": "000001", "trade_date": "2026-08-17",
                "status": "unknown", "is_tradable": None,
                "source": "stage78.3:evidence_gap", "evidence": {"fixture": True},
            },
            {
                "symbol": "000002", "trade_date": "2026-08-17",
                "status": "suspended", "is_tradable": False,
                "source": "akshare:stock_tfp_em:eastmoney",
                "evidence": {
                    "source_suspension_start_date": "2026-08-17",
                    "停牌时间": "2026-08-20", "预计复牌时间": "2026-08-27",
                },
            },
            {
                "symbol": "000003", "trade_date": "2026-08-17",
                "status": "suspended", "is_tradable": False,
                "source": "akshare:stock_tfp_em:eastmoney",
                "evidence": {
                    "停牌时间": "2026-08-15", "停牌截止时间": "2026-08-19",
                    "预计复牌时间": "2026-08-20",
                },
            },
        ])
        preview_report = build_preview_report(
            database, current_symbols_only=True, page_size=2, sample_limit=1,
        )
        assert preview_report["mode"] == "read_only_preview"
        assert preview_report["writes"] == 0
        assert preview_report["apply_supported"] is False
        assert preview_report["candidate_count"] == 3
        assert preview_report["repairability_counts"] == {
            "auto_repairable": 2, "manual_evidence_required": 1,
        }

        def issue(symbol: str) -> dict:
            return store.create_issue({
                "dataset": "trading_status", "symbol": symbol,
                "observation_at": "2026-08-17",
                "rule_id": "trading_status_semantics", "severity": "error",
                "source": "quality_scan_engine", "field_name": "is_tradable",
            })

        unknown_issue = issue("000001")
        mapped_issue = issue("000002")
        explicit_issue = issue("000003")
        for target_issue, expected_reason in (
            (unknown_issue, "positive_bar_resolves_unknown_tradability"),
            (mapped_issue, "source_suspension_interval_excludes_trade_date"),
        ):
            status, payload = dispatch_request(
                app, method="POST",
                path=(
                    f"/api/data-center/quality/issues/{target_issue['issue_id']}"
                    "/trading-status-repair/preview"
                ),
                body=json.dumps({"operator": "qa-lead"}).encode("utf-8"),
            )
            assert status == 200
            preview = payload["result"]
            assert preview["writes"] == 0
            assert preview["repairability"] == "auto_repairable"
            assert preview["reason"] == expected_reason
            status, payload = dispatch_request(
                app, method="POST",
                path=(
                    f"/api/data-center/quality/issues/{target_issue['issue_id']}"
                    "/trading-status-repair/apply"
                ),
                body=json.dumps({
                    "preview_token": preview["preview_token"], "operator": "qa-lead",
                }).encode("utf-8"),
            )
            assert status == 200 and payload["result"]["writes"] == 1
            history = store.get_issue_history(target_issue["issue_id"])
            assert history["issue"]["workflow_status"] == "awaiting_recheck"
            assert history["remediations"][0]["status"] == "awaiting_recheck"

        manual = service.preview_trading_status_repair(
            explicit_issue["issue_id"], operator="qa-lead",
        )
        assert manual["repairability"] == "manual_evidence_required"
        assert manual["reason"] == "explicit_suspension_conflicts_with_positive_bar"
        assert manual["preview_token"] == "" and manual["writes"] == 0
        try:
            service.refetch_quality_issue(explicit_issue["issue_id"])
        except ValueError as error:
            assert "governed preview/apply" in str(error)
        else:
            raise AssertionError("generic refetch must reject trading status semantic issues")

        try:
            dispatch_request(
                app, method="POST",
                path=(
                    f"/api/data-center/quality/issues/{unknown_issue['issue_id']}"
                    "/trading-status-repair/apply"
                ),
                body=json.dumps({
                    "preview_token": preview["preview_token"], "operator": "qa-lead",
                }).encode("utf-8"),
            )
        except DispatchError as error:
            assert error.status_code == 400
        else:
            raise AssertionError("repair preview token must be one-time and issue-bound")

        # 管理员批处理必须先校验集合哈希，并支持限量执行和检查点续跑。
        batch_database = Path(temporary) / "batch-market.sqlite3"
        batch_market = AShareMarketStore(batch_database)
        batch_governance = AShareGovernanceStore(batch_database)
        batch_market.ensure_schema()
        batch_governance.ensure_schema()
        batch_market.upsert_symbols([
            {"symbol": symbol, "name": f"batch-{symbol}", "source": "smoke"}
            for symbol in ("000010", "000011", "000012")
        ])
        for symbol in ("000010", "000011", "000012"):
            batch_market.upsert_daily_prices(
                [_price(symbol, "2026-08-17")], adjustment="qfq", source="smoke",
            )
        batch_governance.upsert_trading_statuses([
            {
                "symbol": "000010", "trade_date": "2026-08-17",
                "status": "unknown", "is_tradable": None,
                "source": "stage78.3:evidence_gap", "evidence": {"fixture": 10},
            },
            {
                "symbol": "000011", "trade_date": "2026-08-17",
                "status": "suspended", "is_tradable": False,
                "source": "akshare:stock_tfp_em:eastmoney",
                "evidence": {"停牌时间": "2026-08-20"},
            },
            {
                "symbol": "000012", "trade_date": "2026-08-17",
                "status": "suspended", "is_tradable": False,
                "source": "akshare:stock_tfp_em:eastmoney",
                "evidence": {
                    "停牌时间": "2026-08-17", "停牌截止时间": "2026-08-17",
                },
            },
        ])
        batch_scheduler = AShareSyncScheduler(
            batch_database, market_store=batch_market,
            governance_store=batch_governance, provider=_NoWriteProvider(),
            max_workers=1, retry_count=1,
        )
        batch_scheduler.ensure_schema()
        batch_service = DataCenterService(
            DataCenterStore(batch_database), batch_scheduler, batch_governance,
        )
        batch_app = SimpleApiApp(
            title="trading-status-batch-smoke",
            routes=build_data_center_routes(batch_service),
        )
        status, payload = dispatch_request(
            batch_app, method="POST",
            path="/api/data-center/quality/trading-status-remediation/preview",
            body=b"{}",
        )
        assert status == 200
        batch_preview = payload["result"]
        assert batch_preview["writes"] == 0
        assert batch_preview["candidate_count"] == 3
        assert batch_preview["max_writes_per_request"] == 1_000
        checkpoint = Path(temporary) / "batch-checkpoint.json"
        try:
            run_batch_remediation(
                batch_database,
                expected_candidate_set_hash=batch_preview["candidate_set_hash"],
                run_id="status-batch-smoke", operator="qa-lead",
                checkpoint_path=checkpoint, confirmation="not-confirmed",
                page_size=2, max_writes=1,
            )
        except ValueError as error:
            assert "confirmation phrase" in str(error)
        else:
            raise AssertionError("batch apply must require the exact confirmation phrase")
        assert not checkpoint.exists()

        # The fixed sidecar excludes another Windows process before any checkpoint,
        # and a killed holder releases the OS lock without deleting the sidecar.
        lease_database = Path(temporary) / "lease-only.sqlite3"
        lease_database.touch()
        lease_ready = Path(temporary) / "lease-holder-ready.json"
        lease_checkpoint = Path(temporary) / "lease-cli-checkpoint.json"
        holder = subprocess.Popen(
            [
                sys.executable, "-B", str(Path(__file__).resolve()),
                "--hold-database-lease", str(lease_database),
                "external-lease-holder", str(lease_ready),
            ],
            cwd=str(root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            for _ in range(500):
                if lease_ready.is_file():
                    break
                if holder.poll() is not None:
                    _, child_error = holder.communicate(timeout=1)
                    raise AssertionError(
                        f"lease holder exited before ready: {child_error}"
                    )
                time.sleep(0.01)
            assert lease_ready.is_file()
            lease_status = inspect_trading_status_database_lease(lease_database)
            assert lease_status["status"] == "busy"
            assert lease_status["owner"]["run_id"] == "external-lease-holder"
            try:
                acquire_trading_status_database_lease(
                    lease_database,
                    run_id="competing-python-api",
                    holder_kind="subprocess_parent_smoke",
                )
            except TradingStatusDatabaseLeaseBusyError as error:
                assert error.owner["run_id"] == "external-lease-holder"
            else:
                raise AssertionError("a second process must not acquire the database lease")

            cli_without_reference = subprocess.run(
                [
                    sys.executable, "-B",
                    str(root / "scripts" / "apply_trading_status_semantic_remediation.py"),
                    "--database", str(lease_database),
                    "--expected-candidate-set-hash", "0" * 64,
                    "--run-id", "cli-no-reference",
                    "--operator", "qa-lead",
                    "--checkpoint", str(lease_checkpoint),
                    "--confirm", CONFIRMATION_PHRASE,
                    "--authorized-total-writes", "1",
                ],
                cwd=str(root), capture_output=True, text=True, encoding="utf-8",
                timeout=10,
            )
            assert cli_without_reference.returncode == 2
            assert "--authorization-reference is required" in cli_without_reference.stderr
            cli_busy = subprocess.run(
                [
                    sys.executable, "-B",
                    str(root / "scripts" / "apply_trading_status_semantic_remediation.py"),
                    "--database", str(lease_database),
                    "--expected-candidate-set-hash", "0" * 64,
                    "--run-id", "cli-busy",
                    "--operator", "qa-lead",
                    "--checkpoint", str(lease_checkpoint),
                    "--confirm", CONFIRMATION_PHRASE,
                    "--authorized-total-writes", "1",
                    "--authorization-reference", "lease-smoke",
                ],
                cwd=str(root), capture_output=True, text=True, encoding="utf-8",
                timeout=10,
            )
            assert cli_busy.returncode == 3
            assert "database writer busy" in cli_busy.stderr
            assert not lease_checkpoint.exists()
        finally:
            if holder.poll() is None:
                holder.kill()
            holder.wait(timeout=10)

        lease_path = Path(str(lease_status["lock_path"]))
        assert lease_path.is_file()
        released_lease = None
        for _ in range(500):
            try:
                released_lease = acquire_trading_status_database_lease(
                    lease_database,
                    run_id="post-crash-holder",
                    holder_kind="subprocess_parent_smoke",
                )
                break
            except TradingStatusDatabaseLeaseBusyError:
                time.sleep(0.01)
        assert released_lease is not None
        released_lease.release()
        assert lease_path.is_file()
        assert inspect_trading_status_database_lease(lease_database)["status"] == "available"

        # 核心层同时约束总授权和单事务上限，绕过 Web 也不能扩大边界。
        for invalid_limits, expected_message in (
            (
                {"authorized_total_writes": MAX_AUTHORIZED_TOTAL_WRITES + 1},
                "must not exceed",
            ),
            (
                {"authorized_total_writes": 1, "commit_batch_size": 1_001},
                "between 1 and 1000",
            ),
        ):
            limit_checkpoint = Path(temporary) / (
                f"invalid-limit-{len(list(Path(temporary).glob('invalid-limit-*')))}.json"
            )
            try:
                prepare_batch_remediation(
                    batch_database,
                    expected_candidate_set_hash=batch_preview["candidate_set_hash"],
                    run_id=f"invalid-limit-{limit_checkpoint.stem}",
                    operator="qa-lead", checkpoint_path=limit_checkpoint,
                    confirmation=CONFIRMATION_PHRASE, **invalid_limits,
                )
            except ValueError as error:
                assert expected_message in str(error)
            else:
                raise AssertionError("invalid authorization limits must be rejected")
            assert not limit_checkpoint.exists()

        # Two concurrent starts serialize at the database lease before checkpoint IO.
        duplicate_checkpoint = Path(temporary) / "duplicate-start.json"
        duplicate_barrier = Barrier(2)

        def prepare_duplicate_start():
            duplicate_barrier.wait(timeout=5)
            return prepare_batch_remediation(
                batch_database,
                expected_candidate_set_hash=batch_preview["candidate_set_hash"],
                run_id="duplicate-start", operator="qa-lead",
                checkpoint_path=duplicate_checkpoint,
                confirmation=CONFIRMATION_PHRASE,
                authorized_total_writes=1, commit_batch_size=1,
                authorization_reference="concurrent-start-smoke",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(prepare_duplicate_start) for _ in range(2)]
            duplicate_results = []
            duplicate_errors = []
            for future in futures:
                try:
                    duplicate_results.append(future.result(timeout=10))
                except ValueError as error:
                    duplicate_errors.append(error)
        assert len(duplicate_results) == 1
        assert len(duplicate_errors) == 1
        assert "database lease is busy" in str(duplicate_errors[0])
        assert duplicate_results[0]["status"] == "queued"
        duplicate_state = json.loads(duplicate_checkpoint.read_text(encoding="utf-8"))
        assert duplicate_state["status"] == "queued"
        assert duplicate_state["authorized_total_writes"] == 1
        assert not list(Path(temporary).glob("*.initializing.tmp"))

        # Windows 上 GET 轮询可能短暂持有目标文件；writer 应有界重试后原子替换。
        reader_opened = Event()

        def hold_checkpoint_reader():
            with duplicate_checkpoint.open("r", encoding="utf-8") as stream:
                reader_opened.set()
                time.sleep(0.08)
                return json.load(stream)

        with ThreadPoolExecutor(max_workers=1) as executor:
            reader_future = executor.submit(hold_checkpoint_reader)
            assert reader_opened.wait(timeout=2)
            duplicate_state["concurrent_reader_sequence"] = 1
            remediation_runner._write_checkpoint(
                duplicate_checkpoint, duplicate_state,
            )
            reader_snapshot = reader_future.result(timeout=2)
        assert reader_snapshot["status"] == "queued"
        assert json.loads(duplicate_checkpoint.read_text(encoding="utf-8"))[
            "concurrent_reader_sequence"
        ] == 1
        assert not list(Path(temporary).glob("duplicate-start.json.*.tmp"))

        class NonSharingFailure:
            calls = 0

            def replace(self, _destination):
                self.calls += 1
                error = PermissionError("isolated non-sharing permission failure")
                error.winerror = 123
                raise error

        non_sharing_source = NonSharingFailure()
        try:
            remediation_runner._replace_with_windows_sharing_retry(
                non_sharing_source, duplicate_checkpoint,
            )
        except PermissionError as error:
            assert error.winerror == 123
        else:
            raise AssertionError("non-sharing permission errors must not be retried away")
        assert non_sharing_source.calls == 1

        bad_hash_checkpoint = Path(temporary) / "bad-hash-checkpoint.json"
        try:
            run_batch_remediation(
                batch_database, expected_candidate_set_hash="wrong-hash",
                run_id="status-batch-bad-hash", operator="qa-lead",
                checkpoint_path=bad_hash_checkpoint,
                confirmation=CONFIRMATION_PHRASE,
                page_size=2, authorized_total_writes=1,
                commit_batch_size=1,
            )
        except ValueError as error:
            assert "hash mismatch" in str(error)
        else:
            raise AssertionError("batch apply must reject a stale candidate hash")
        bad_hash_state = json.loads(bad_hash_checkpoint.read_text(encoding="utf-8"))
        assert bad_hash_state["status"] == "failed"
        assert "hash mismatch" in bad_hash_state["last_error"]
        assert bad_hash_state["failed_cursor"] == {"symbol": "", "trade_date": ""}

        # Public /apply keeps max_writes only as a fail-closed compatibility field.
        web_checkpoint = (
            Path(temporary) / "trading_status_remediation"
            / "status-batch-smoke.json"
        )
        try:
            dispatch_request(
                batch_app, method="POST",
                path="/api/data-center/quality/trading-status-remediation/apply",
                body=json.dumps({
                    "expected_candidate_set_hash": batch_preview["candidate_set_hash"],
                    "run_id": "legacy-max-writes-only", "operator": "qa-lead",
                    "confirmation": CONFIRMATION_PHRASE, "max_writes": 1,
                }).encode("utf-8"),
            )
        except DispatchError as error:
            assert error.status_code == 400
            assert "authorized_total_writes" in error.message
        else:
            raise AssertionError("public max_writes-only apply must fail closed")
        assert not (
            web_checkpoint.parent / "legacy-max-writes-only.json"
        ).exists()

        first_batch = run_batch_remediation(
            batch_database,
            expected_candidate_set_hash=batch_preview["candidate_set_hash"],
            run_id="status-batch-smoke", operator="qa-lead",
            checkpoint_path=web_checkpoint,
            confirmation=CONFIRMATION_PHRASE,
            current_symbols_only=False,
            authorized_total_writes=1,
            commit_batch_size=1_000,
            authorization_reference="core-explicit-one",
        )
        assert first_batch["checkpoint_version"] == "2"
        assert first_batch["status"] == "authorization_exhausted"
        assert first_batch["authorized_total_writes"] == 1
        assert first_batch["commit_batch_size"] == 1_000
        assert first_batch["authorization_consumed"] == 1
        assert first_batch["written"] == 1
        assert web_checkpoint.is_file()
        status, payload = dispatch_request(
            batch_app, method="GET",
            path=(
                "/api/data-center/quality/trading-status-remediation/"
                "status-batch-smoke"
            ),
        )
        assert status == 200 and payload["result"]["written"] == 1
        repeated = run_batch_remediation(
            batch_database,
            expected_candidate_set_hash=batch_preview["candidate_set_hash"],
            run_id="status-batch-smoke", operator="qa-lead",
            checkpoint_path=web_checkpoint,
            confirmation=CONFIRMATION_PHRASE,
            current_symbols_only=False,
            authorized_total_writes=1,
            commit_batch_size=1_000,
            authorization_reference="core-explicit-one",
        )
        assert repeated["written"] == 1
        assert repeated["status"] == "authorization_exhausted"
        try:
            run_batch_remediation(
                batch_database,
                expected_candidate_set_hash=batch_preview["candidate_set_hash"],
                run_id="status-batch-smoke", operator="qa-lead",
                checkpoint_path=web_checkpoint, confirmation=CONFIRMATION_PHRASE,
                current_symbols_only=False,
                authorized_total_writes=2, commit_batch_size=1_000,
            )
        except ValueError as error:
            assert "frozen authorization" in str(error)
        else:
            raise AssertionError("a v2 resume must not increase its frozen authorization")
        assert json.loads(web_checkpoint.read_text(encoding="utf-8"))["written"] == 1

        # 完整清单哈希仍须在终态读取时验证。
        manifest_path = Path(first_batch["candidate_manifest"])
        manifest_content = manifest_path.read_bytes()
        manifest_path.write_bytes(manifest_content + b"{}\n")
        try:
            run_batch_remediation(
                batch_database,
                expected_candidate_set_hash=batch_preview["candidate_set_hash"],
                run_id="status-batch-smoke", operator="qa-lead",
                checkpoint_path=web_checkpoint, confirmation=CONFIRMATION_PHRASE,
                current_symbols_only=False,
            )
        except ValueError as error:
            assert "manifest content changed" in str(error)
        else:
            raise AssertionError("terminal v2 reads must reject a changed manifest")
        manifest_path.write_bytes(manifest_content)

        # 新的长任务冻结一份清单、总授权和原子批次大小。
        batch_market.upsert_symbols([
            {"symbol": symbol, "name": f"long-{symbol}", "source": "smoke"}
            for symbol in ("000020", "000021")
        ])
        for symbol in ("000020", "000021"):
            batch_market.upsert_daily_prices(
                [_price(symbol, "2026-08-17")], adjustment="qfq", source="smoke",
            )
            batch_governance.upsert_trading_statuses([{
                "symbol": symbol, "trade_date": "2026-08-17",
                "status": "unknown", "is_tradable": None,
                "source": "stage78.3:evidence_gap", "evidence": {"long": symbol},
            }])
        batch_market.upsert_symbols([
            {"symbol": "999999", "name": "trailing-manual", "source": "smoke"},
        ])
        batch_market.upsert_daily_prices(
            [_price("999999", "2026-08-17")], adjustment="qfq", source="smoke",
        )
        batch_governance.upsert_trading_statuses([{
            "symbol": "999999", "trade_date": "2026-08-17",
            "status": "suspended", "is_tradable": False,
            "source": "akshare:stock_tfp_em:eastmoney",
            "evidence": {
                "停牌时间": "2026-08-17", "停牌截止时间": "2026-08-17",
            },
        }])
        long_preview = build_preview_report(
            batch_database, current_symbols_only=True, page_size=2, sample_limit=0,
        )
        assert long_preview["repairability_counts"] == {
            "auto_repairable": 3, "manual_evidence_required": 2,
        }
        long_checkpoint = Path(temporary) / "long-checkpoint.json"
        original_preview_builder = remediation_runner.build_preview_report

        def observing_preview_builder(*args, **kwargs):
            initializing = json.loads(long_checkpoint.read_text(encoding="utf-8"))
            assert initializing["status"] == "initializing"
            assert initializing["authorized_total_writes"] == 3
            assert initializing["commit_batch_size"] == 2
            return original_preview_builder(*args, **kwargs)

        remediation_runner.build_preview_report = observing_preview_builder
        try:
            prepared = prepare_batch_remediation(
                batch_database,
                expected_candidate_set_hash=long_preview["candidate_set_hash"],
                run_id="status-long-smoke", operator="qa-lead",
                checkpoint_path=long_checkpoint, confirmation=CONFIRMATION_PHRASE,
                page_size=2, authorized_total_writes=3, commit_batch_size=2,
                authorization_reference="smoke-explicit-three",
            )
        finally:
            remediation_runner.build_preview_report = original_preview_builder
        assert prepared["status"] == "queued"
        assert prepared["candidate_manifest_file_hash"]
        checkpoint_before_pause = long_checkpoint.read_bytes()
        paused = request_batch_pause(long_checkpoint)
        assert paused["status"] == "paused_by_user"
        assert long_checkpoint.read_bytes() == checkpoint_before_pause
        paused_run = run_batch_remediation(
            batch_database,
            expected_candidate_set_hash=long_preview["candidate_set_hash"],
            run_id="status-long-smoke", operator="qa-lead",
            checkpoint_path=long_checkpoint, confirmation=CONFIRMATION_PHRASE,
            authorized_total_writes=3, commit_batch_size=2,
            authorization_reference="smoke-explicit-three",
        )
        assert paused_run["status"] == "paused_by_user"
        assert paused_run["written"] == 0
        assert clear_batch_pause(long_checkpoint)["status"] == "queued"

        limited_long = run_batch_remediation(
            batch_database,
            expected_candidate_set_hash=long_preview["candidate_set_hash"],
            run_id="status-long-smoke", operator="qa-lead",
            checkpoint_path=long_checkpoint, confirmation=CONFIRMATION_PHRASE,
            max_writes=1, authorized_total_writes=3, commit_batch_size=2,
            authorization_reference="smoke-explicit-three",
        )
        assert limited_long["status"] == "paused_max_writes"
        assert limited_long["written"] == 1
        assert limited_long["manual_candidates_seen"] == 1
        assert limited_long["batches"][0]["duration_seconds"] >= 0
        assert "throughput_candidates_per_second" in limited_long["batches"][0]

        long_manifest = Path(limited_long["candidate_manifest"])
        long_manifest_content = long_manifest.read_bytes()
        long_manifest.write_bytes(long_manifest_content + b"{}\n")
        try:
            run_batch_remediation(
                batch_database,
                expected_candidate_set_hash=long_preview["candidate_set_hash"],
                run_id="status-long-smoke", operator="qa-lead",
                checkpoint_path=long_checkpoint, confirmation=CONFIRMATION_PHRASE,
            )
        except ValueError as error:
            assert "manifest content changed" in str(error)
        else:
            raise AssertionError("batch resume must reject a changed candidate manifest")
        long_manifest.write_bytes(long_manifest_content)

        # 预演清单冻结后新增的候选不得进入续跑范围。
        batch_market.upsert_symbols([
            {"symbol": "000014", "name": "post-manifest", "source": "smoke"},
        ])
        batch_market.upsert_daily_prices(
            [_price("000014", "2026-08-17")], adjustment="qfq", source="smoke",
        )
        batch_governance.upsert_trading_statuses([{
            "symbol": "000014", "trade_date": "2026-08-17",
            "status": "unknown", "is_tradable": None,
            "source": "stage78.3:evidence_gap", "evidence": {"post_manifest": True},
        }])
        completed_batch = run_batch_remediation(
            batch_database,
            expected_candidate_set_hash=long_preview["candidate_set_hash"],
            run_id="status-long-smoke", operator="qa-lead",
            checkpoint_path=long_checkpoint, confirmation=CONFIRMATION_PHRASE,
            authorized_total_writes=3, commit_batch_size=2,
            authorization_reference="smoke-explicit-three",
        )
        assert completed_batch["status"] == "completed"
        assert completed_batch["completion_consistency"] == "matched"
        assert completed_batch["authorization_consumed"] == 3
        assert completed_batch["written"] == 3
        assert completed_batch["newly_written"] == 3
        assert completed_batch["recovered_written"] == 0
        assert completed_batch["manual_candidates_seen"] == 2
        batch_statuses = {
            symbol: batch_governance.fetch_trading_status_history(symbol)[0]
            for symbol in ("000010", "000011", "000012")
        }
        assert batch_statuses["000010"]["is_tradable"] is True
        assert batch_statuses["000011"]["is_tradable"] is True
        assert batch_statuses["000012"]["is_tradable"] is False
        assert batch_governance.fetch_trading_status_history("000020")[0][
            "is_tradable"
        ] is True
        assert batch_governance.fetch_trading_status_history("000021")[0][
            "is_tradable"
        ] is True
        assert batch_governance.fetch_trading_status_history("000014")[0][
            "is_tradable"
        ] is None

        # 总授权小于自动候选数时到达边界；重复调用不能再写或扩容。
        batch_market.upsert_symbols([
            {"symbol": "000015", "name": "authorization-boundary", "source": "smoke"},
        ])
        batch_market.upsert_daily_prices(
            [_price("000015", "2026-08-17")], adjustment="qfq", source="smoke",
        )
        batch_governance.upsert_trading_statuses([{
            "symbol": "000015", "trade_date": "2026-08-17",
            "status": "unknown", "is_tradable": None,
            "source": "stage78.3:evidence_gap", "evidence": {"boundary": True},
        }])
        boundary_preview = build_preview_report(
            batch_database, current_symbols_only=True, page_size=2, sample_limit=0,
        )
        boundary_checkpoint = Path(temporary) / "boundary-checkpoint.json"
        boundary = run_batch_remediation(
            batch_database,
            expected_candidate_set_hash=boundary_preview["candidate_set_hash"],
            run_id="status-boundary-smoke", operator="qa-lead",
            checkpoint_path=boundary_checkpoint, confirmation=CONFIRMATION_PHRASE,
            authorized_total_writes=1, commit_batch_size=2,
        )
        assert boundary["status"] == "authorization_exhausted"
        assert boundary["written"] == 1
        unchanged = run_batch_remediation(
            batch_database,
            expected_candidate_set_hash=boundary_preview["candidate_set_hash"],
            run_id="status-boundary-smoke", operator="qa-lead",
            checkpoint_path=boundary_checkpoint, confirmation=CONFIRMATION_PHRASE,
        )
        assert unchanged["written"] == 1
        try:
            run_batch_remediation(
                batch_database,
                expected_candidate_set_hash=boundary_preview["candidate_set_hash"],
                run_id="status-boundary-smoke", operator="qa-lead",
                checkpoint_path=boundary_checkpoint, confirmation=CONFIRMATION_PHRASE,
                authorized_total_writes=2,
            )
        except ValueError as error:
            assert "frozen authorization" in str(error)
        else:
            raise AssertionError("authorization-exhausted runs must not be expanded")
        assert batch_governance.fetch_trading_status_history("000015")[0][
            "is_tradable"
        ] is None

        # v1 检查点保留只读兼容，但任何 v2 写路径必须拒绝续跑。
        legacy_checkpoint = Path(temporary) / "legacy-v1.json"
        legacy_checkpoint.write_text(
            json.dumps({"checkpoint_version": "1", "status": "paused_max_writes"}),
            encoding="utf-8",
        )
        legacy_before = legacy_checkpoint.read_bytes()
        try:
            run_batch_remediation(
                batch_database,
                expected_candidate_set_hash=boundary_preview["candidate_set_hash"],
                run_id="legacy-v1", operator="qa-lead",
                checkpoint_path=legacy_checkpoint, confirmation=CONFIRMATION_PHRASE,
                authorized_total_writes=1,
            )
        except ValueError as error:
            assert "v1 is read-only" in str(error)
        else:
            raise AssertionError("v1 checkpoints must not enter the v2 writer")
        assert legacy_checkpoint.read_bytes() == legacy_before
        try:
            mark_batch_interrupted(legacy_checkpoint, reason="legacy shutdown")
        except ValueError as error:
            assert "v1 is read-only" in str(error)
        else:
            raise AssertionError("v1 checkpoints must reject interruption writes")
        assert legacy_checkpoint.read_bytes() == legacy_before

        # 执行异常必须落入可诊断的 failed 检查点。
        batch_market.upsert_symbols([
            {"symbol": "000016", "name": "failure", "source": "smoke"},
        ])
        batch_market.upsert_daily_prices(
            [_price("000016", "2026-08-17")], adjustment="qfq", source="smoke",
        )
        batch_governance.upsert_trading_statuses([{
            "symbol": "000016", "trade_date": "2026-08-17",
            "status": "unknown", "is_tradable": None,
            "source": "stage78.3:evidence_gap", "evidence": {"failure": True},
        }])
        failure_preview = build_preview_report(
            batch_database, current_symbols_only=True, page_size=2, sample_limit=0,
        )
        failure_checkpoint = Path(temporary) / "failure-checkpoint.json"
        original_apply_batch = AShareGovernanceStore.apply_trading_status_repair_batch

        def fail_batch(*_args, **_kwargs):
            raise RuntimeError("injected isolated batch failure")

        AShareGovernanceStore.apply_trading_status_repair_batch = fail_batch
        try:
            try:
                run_batch_remediation(
                    batch_database,
                    expected_candidate_set_hash=failure_preview["candidate_set_hash"],
                    run_id="status-failure-smoke", operator="qa-lead",
                    checkpoint_path=failure_checkpoint,
                    confirmation=CONFIRMATION_PHRASE,
                    authorized_total_writes=1, commit_batch_size=2,
                )
            except RuntimeError as error:
                assert "injected isolated batch failure" in str(error)
            else:
                raise AssertionError("injected failure must escape the runner")
        finally:
            AShareGovernanceStore.apply_trading_status_repair_batch = original_apply_batch
        failed = json.loads(failure_checkpoint.read_text(encoding="utf-8"))
        assert failed["status"] == "failed"
        assert "injected isolated batch failure" in failed["last_error"]
        assert failed["failed_batch_number"] == 1
        assert failed["failed_cursor"] == {"symbol": "", "trade_date": ""}

        # 候选生成后若原状态证据发生变化，条件更新必须跳过。
        batch_market.upsert_symbols([
            {"symbol": "000013", "name": "stale", "source": "smoke"},
        ])
        batch_market.upsert_daily_prices(
            [_price("000013", "2026-08-17")], adjustment="qfq", source="smoke",
        )
        batch_governance.upsert_trading_statuses([{
            "symbol": "000013", "trade_date": "2026-08-17",
            "status": "unknown", "is_tradable": None,
            "source": "stage78.3:evidence_gap", "evidence": {"version": 1},
        }])
        stale_candidate = batch_governance.scan_trading_status_repair_candidates(
            after_symbol="000012", after_trade_date="9999-12-31", limit=10,
        )[0]
        forged_candidate = dict(stale_candidate)
        forged_candidate["evidence_fingerprint"] = "forged"
        try:
            batch_governance.apply_trading_status_repair_batch(
                [forged_candidate], run_id="status-batch-forged", operator="qa-lead",
            )
        except ValueError as error:
            assert "fingerprint is invalid" in str(error)
        else:
            raise AssertionError("batch repair must reject a forged candidate fingerprint")
        try:
            batch_governance.apply_trading_status_repair_batch(
                [stale_candidate] * 1_001,
                run_id="status-batch-too-large", operator="qa-lead",
            )
        except ValueError as error:
            assert "at most 1000" in str(error)
        else:
            raise AssertionError("storage must reject batches larger than 1000 candidates")
        batch_governance.upsert_trading_statuses([{
            "symbol": "000013", "trade_date": "2026-08-17",
            "status": "unknown", "is_tradable": None,
            "source": "stage78.3:evidence_gap", "evidence": {"version": 2},
        }])
        stale_result = batch_governance.apply_trading_status_repair_batch(
            [stale_candidate], run_id="status-batch-stale", operator="qa-lead",
        )
        assert stale_result["written"] == 0 and stale_result["skipped"] == 1

        # 模拟“数据库已提交、检查点尚未推进”的崩溃窗口，续跑应识别为本任务已写。
        recovery_database = Path(temporary) / "recovery-market.sqlite3"
        recovery_market = AShareMarketStore(recovery_database)
        recovery_governance = AShareGovernanceStore(recovery_database)
        recovery_market.ensure_schema()
        recovery_governance.ensure_schema()
        recovery_market.upsert_symbols([
            {"symbol": "000030", "name": "recovery", "source": "smoke"},
        ])
        recovery_market.upsert_daily_prices(
            [_price("000030", "2026-08-17")], adjustment="qfq", source="smoke",
        )
        recovery_governance.upsert_trading_statuses([{
            "symbol": "000030", "trade_date": "2026-08-17",
            "status": "unknown", "is_tradable": None,
            "source": "stage78.3:evidence_gap", "evidence": {"recovery": True},
        }])
        recovery_preview = build_preview_report(
            recovery_database, current_symbols_only=True, page_size=1, sample_limit=0,
        )
        recovery_checkpoint = Path(temporary) / "recovery-checkpoint.json"
        prepared_recovery = prepare_batch_remediation(
            recovery_database,
            expected_candidate_set_hash=recovery_preview["candidate_set_hash"],
            run_id="status-recovery-smoke", operator="qa-lead",
            checkpoint_path=recovery_checkpoint, confirmation=CONFIRMATION_PHRASE,
            authorized_total_writes=1, commit_batch_size=1,
        )
        recovery_manifest_record = json.loads(
            Path(prepared_recovery["candidate_manifest"])
            .read_text(encoding="utf-8").splitlines()[0]
        )
        direct_candidate = recovery_governance.load_trading_status_repair_candidates([
            (recovery_manifest_record["symbol"], recovery_manifest_record["trade_date"]),
        ])[0]
        direct_write = recovery_governance.apply_trading_status_repair_batch(
            [direct_candidate], run_id="status-recovery-smoke", operator="qa-lead",
        )
        assert direct_write["written"] == 1
        assert json.loads(recovery_checkpoint.read_text(encoding="utf-8"))["written"] == 0
        recovered = run_batch_remediation(
            recovery_database,
            expected_candidate_set_hash=recovery_preview["candidate_set_hash"],
            run_id="status-recovery-smoke", operator="qa-lead",
            checkpoint_path=recovery_checkpoint, confirmation=CONFIRMATION_PHRASE,
            authorized_total_writes=1, commit_batch_size=1,
        )
        assert recovered["status"] == "completed"
        assert recovered["written"] == 1
        assert recovered["newly_written"] == 0
        assert recovered["recovered_written"] == 1
        assert recovered["skipped"] == 0

        def isolated_fixture(stem: str, symbols: tuple[str, ...]):
            isolated_database = Path(temporary) / f"{stem}.sqlite3"
            isolated_market = AShareMarketStore(isolated_database)
            isolated_governance = AShareGovernanceStore(isolated_database)
            isolated_market.ensure_schema()
            isolated_governance.ensure_schema()
            isolated_market.upsert_symbols([
                {"symbol": symbol, "name": f"{stem}-{symbol}", "source": "smoke"}
                for symbol in symbols
            ])
            for symbol in symbols:
                isolated_market.upsert_daily_prices(
                    [_price(symbol, "2026-08-17")],
                    adjustment="qfq", source="smoke",
                )
                isolated_governance.upsert_trading_statuses([{
                    "symbol": symbol, "trade_date": "2026-08-17",
                    "status": "unknown", "is_tradable": None,
                    "source": "stage78.3:evidence_gap",
                    "evidence": {"fixture": stem},
                }])
            isolated_preview = build_preview_report(
                isolated_database, current_symbols_only=True,
                page_size=2, sample_limit=0,
            )
            assert isolated_preview["repairability_counts"] == {
                "auto_repairable": len(symbols),
            }
            return isolated_database, isolated_governance, isolated_preview

        # 外部 worker 中断要落盘为 failed；冻结参数不变且只能显式续跑。
        interrupt_database, _, interrupt_preview = isolated_fixture(
            "interrupt", ("100001", "100002"),
        )
        interrupt_checkpoint = Path(temporary) / "interrupt-checkpoint.json"
        interrupt_parameters = {
            "expected_candidate_set_hash": interrupt_preview["candidate_set_hash"],
            "run_id": "status-interrupt-smoke", "operator": "qa-lead",
            "checkpoint_path": interrupt_checkpoint,
            "confirmation": CONFIRMATION_PHRASE,
            "authorized_total_writes": 2, "commit_batch_size": 1,
            "authorization_reference": "interrupt-smoke-two",
        }
        interrupt_prepared = prepare_batch_remediation(
            interrupt_database, **interrupt_parameters,
        )
        frozen_before_interrupt = {
            key: interrupt_prepared[key]
            for key in (
                "run_id", "operator", "scope", "expected_candidate_set_hash",
                "authorized_total_writes", "commit_batch_size",
                "authorization_reference", "candidate_manifest_file_hash",
            )
        }
        interrupted = mark_batch_interrupted(
            interrupt_checkpoint, reason="isolated worker shutdown",
        )
        assert interrupted["status"] == "failed"
        assert interrupted["last_error"] == (
            "InterruptedError: isolated worker shutdown"
        )
        assert interrupted["failure_count"] == 1
        assert interrupted["interruption_count"] == 1
        assert interrupted["last_interruption"]["prior_status"] == "queued"
        assert interrupted["last_interruption"]["reason"] == (
            "isolated worker shutdown"
        )
        assert {
            key: interrupted[key] for key in frozen_before_interrupt
        } == frozen_before_interrupt
        interrupted_bytes = interrupt_checkpoint.read_bytes()
        already_failed = mark_batch_interrupted(
            interrupt_checkpoint, reason="must not overwrite root cause",
        )
        assert already_failed["last_interruption"]["reason"] == (
            "isolated worker shutdown"
        )
        assert interrupt_checkpoint.read_bytes() == interrupted_bytes
        resumed_after_interrupt = run_batch_remediation(
            interrupt_database, **interrupt_parameters,
        )
        assert resumed_after_interrupt["status"] == "completed"
        assert resumed_after_interrupt["completion_consistency"] == "matched"
        assert resumed_after_interrupt["written"] == 2
        assert resumed_after_interrupt["interruption_count"] == 1
        assert resumed_after_interrupt["last_error"] is None
        completed_bytes = interrupt_checkpoint.read_bytes()
        terminal_unchanged = mark_batch_interrupted(
            interrupt_checkpoint, reason="late shutdown notification",
        )
        assert terminal_unchanged["status"] == "completed"
        assert interrupt_checkpoint.read_bytes() == completed_bytes

        # 暂停请求若发生在事务提交中，只能在完整批次提交后停下。
        pause_database, _, pause_preview = isolated_fixture(
            "pause-boundary", ("100011", "100012"),
        )
        pause_checkpoint = Path(temporary) / "pause-boundary-checkpoint.json"
        original_pause_apply = AShareGovernanceStore.apply_trading_status_repair_batch
        pause_apply_calls = 0

        def apply_then_pause(self, candidates, *, run_id, operator):
            nonlocal pause_apply_calls
            result = original_pause_apply(
                self, candidates, run_id=run_id, operator=operator,
            )
            pause_apply_calls += 1
            request_batch_pause(pause_checkpoint)
            return result

        AShareGovernanceStore.apply_trading_status_repair_batch = apply_then_pause
        try:
            paused_at_boundary = run_batch_remediation(
                pause_database,
                expected_candidate_set_hash=pause_preview["candidate_set_hash"],
                run_id="status-pause-boundary-smoke", operator="qa-lead",
                checkpoint_path=pause_checkpoint,
                confirmation=CONFIRMATION_PHRASE,
                authorized_total_writes=2, commit_batch_size=2,
                authorization_reference="pause-boundary-smoke-two",
            )
        finally:
            AShareGovernanceStore.apply_trading_status_repair_batch = original_pause_apply
        assert pause_apply_calls == 1
        assert paused_at_boundary["status"] == "paused_by_user"
        assert paused_at_boundary["written"] == 2
        assert paused_at_boundary["authorization_consumed"] == 2
        assert paused_at_boundary["batch_count"] == 1
        assert paused_at_boundary["batches"][0]["candidate_count"] == 2
        assert paused_at_boundary["batches"][0]["written"] == 2
        assert clear_batch_pause(pause_checkpoint)["status"] == "queued"
        pause_completed = run_batch_remediation(
            pause_database,
            expected_candidate_set_hash=pause_preview["candidate_set_hash"],
            run_id="status-pause-boundary-smoke", operator="qa-lead",
            checkpoint_path=pause_checkpoint,
            confirmation=CONFIRMATION_PHRASE,
            authorized_total_writes=2, commit_batch_size=2,
            authorization_reference="pause-boundary-smoke-two",
        )
        assert pause_completed["status"] == "completed"
        assert pause_completed["completion_consistency"] == "matched"
        assert pause_completed["batch_count"] == 1

        # 即便检查点损坏导致计数漂移，也不得把不一致结果标记 completed。
        drift_database, _, drift_preview = isolated_fixture(
            "completion-drift", ("100021",),
        )
        drift_checkpoint = Path(temporary) / "completion-drift-checkpoint.json"
        drift_parameters = {
            "expected_candidate_set_hash": drift_preview["candidate_set_hash"],
            "run_id": "status-completion-drift-smoke", "operator": "qa-lead",
            "checkpoint_path": drift_checkpoint,
            "confirmation": CONFIRMATION_PHRASE,
            "authorized_total_writes": 1, "commit_batch_size": 1,
            "authorization_reference": "completion-drift-smoke-one",
        }
        drift_prepared = prepare_batch_remediation(
            drift_database, **drift_parameters,
        )
        drift_prepared["expected_candidate_count"] += 1
        remediation_runner._write_checkpoint(drift_checkpoint, drift_prepared)
        drift_result = run_batch_remediation(
            drift_database, **drift_parameters,
        )
        assert drift_result["status"] == "failed"
        assert drift_result["completion_consistency"] == "candidate_drift_detected"
        assert "completion candidate count mismatch" in drift_result["last_error"]

    javascript = (root / "web" / "data_center_stage_c.js").read_text(encoding="utf-8")
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    composition = (root / "app" / "runtime" / "demo_registry.py").read_text(
        encoding="utf-8"
    )
    assert "repairTradingStatusIssue" in javascript
    assert "trading-status-repair/preview" in javascript
    assert "previewStatusRemediation" in javascript
    assert 'STATUS_REMEDIATION_BASE="/api/data-center/quality/trading-status-remediation"' in javascript
    assert "trading-status-remediation/start" in javascript
    assert 'id="dc-status-remediation-form"' in html
    assert "1,000 条" in html
    assert '"var/runtime/trading_status_remediation"' in composition
    assert "预览确定性修复" in javascript
    print("trading status semantic repair smoke passed")


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--hold-database-lease":
        _hold_database_lease_child(
            Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]),
        )
    else:
        main()
