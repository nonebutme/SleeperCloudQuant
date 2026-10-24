"""Deterministic proof for the formal-verification storage isolation layer."""

from __future__ import annotations

import ast
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    project_root = ensure_project_root_on_sys_path()
    import run_formal_verifications as formal

    assert "var" not in formal._SOURCE_DIRECTORIES
    assert "tmp" not in formal._SOURCE_DIRECTORIES
    assert "output" not in formal._SOURCE_DIRECTORIES
    assert "traces" not in formal._SOURCE_DIRECTORIES

    runner_source = Path(formal.__file__).read_text(encoding="utf-8")
    runner_tree = ast.parse(runner_source)
    script_list = next(
        [item.value for item in node.value.elts if isinstance(item, ast.Constant)]
        for node in ast.walk(runner_tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "scripts"
            for target in node.targets
        )
        and isinstance(node.value, ast.List)
    )
    assert len(script_list) == len(set(script_list)), 'verification entries must be unique'
    assert len(script_list) >= 110
    assert 'smoke_test_data_maintenance.py' in script_list
    assert script_list.count("smoke_test_formal_verification_isolation.py") == 1
    assert script_list.count("smoke_test_demo_governed_seed.py") == 1
    assert runner_source.index("before = _fingerprint_roots") < runner_source.index(
        "_assert_formal_source_is_quiescent(source_database)"
    )
    assert '"protected_storage_fingerprints_paired"' in runner_source
    assert '"protected_storage_unchanged"' in runner_source
    for report_field in (
        '"suite_completed"',
        '"script_results"',
        '"test_failures"',
        '"unattempted"',
        '"run_outcome"',
        '"fatal_failure"',
        '"per_script_writable_state_reset_policy_enabled"',
        '"per_script_writable_state_reset"',
        '"per_script_writable_state_successful_reset_count"',
        '"per_script_writable_state_expected_reset_count"',
        '"per_script_writable_state_roots"',
    ):
        assert report_field in runner_source

    with tempfile.TemporaryDirectory(
        prefix="scq-formal-isolation-", dir=project_root / "tmp"
    ) as temporary:
        fixture_root = Path(temporary).resolve()
        protected_root = fixture_root / "protected"
        sandbox_root = fixture_root / "snapshot"
        evidence_root = fixture_root / "evidence"
        protected_root.mkdir()
        sandbox_root.mkdir()
        evidence_root.mkdir()
        protected_database = protected_root / "formal.sqlite3"
        sandbox_database = sandbox_root / "isolated.sqlite3"
        with closing(sqlite3.connect(protected_database)) as connection, connection:
            connection.execute("CREATE TABLE probe (value TEXT NOT NULL)")
            connection.execute("INSERT INTO probe VALUES ('unchanged')")

        before = formal._fingerprint_roots(fixture_root, (protected_root,))
        guard_directory = Path(__file__).resolve().parent / "_formal_storage_guard"
        violation_log = evidence_root / "storage-guard-violations.jsonl"
        ready_log = evidence_root / "storage-guard-ready.jsonl"
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONPATH": str(guard_directory),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
                "SCQ_FORMAL_STORAGE_GUARD_REQUIRED": "1",
                "SCQ_FORMAL_PROTECTED_ROOTS": str(protected_root),
                "SCQ_FORMAL_STORAGE_GUARD_LOG": str(violation_log),
                "SCQ_FORMAL_STORAGE_GUARD_READY_LOG": str(ready_log),
                "SCQ_FORMAL_CURRENT_SCRIPT": "formal-isolation-fixture",
            }
        )
        child_code = textwrap.dedent(
            f"""
            import builtins
            import os
            import sqlite3
            import sqlite3.dbapi2 as dbapi2

            assert builtins._SCQ_FORMAL_STORAGE_GUARD_READY is True
            protected = {str(protected_database)!r}
            protected_uri = "file:" + {protected_database.as_posix()!r} + "?mode=ro&immutable=1"
            sandbox = {str(sandbox_database)!r}

            with sqlite3.connect(sandbox) as connection:
                connection.execute("CREATE TABLE local_probe (value TEXT)")
                connection.execute("INSERT INTO local_probe VALUES ('isolated')")

            try:
                sqlite3.connect(protected)
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError("plain protected connection was not blocked")

            try:
                dbapi2.connect(protected)
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError("dbapi2 protected connection was not blocked")

            try:
                open(protected, "wb")
            except PermissionError:
                pass
            else:
                raise AssertionError("plain file write to protected storage was not blocked")

            replace_source = sandbox + ".replace-source"
            with open(replace_source, "w", encoding="utf-8") as stream:
                stream.write("isolated")
            try:
                os.replace(replace_source, protected)
            except PermissionError:
                pass
            else:
                raise AssertionError("os.replace into protected storage was not blocked")

            with sqlite3.connect(protected_uri, uri=True) as connection:
                assert connection.execute("SELECT value FROM probe").fetchone()[0] == "unchanged"
                try:
                    connection.execute("CREATE TABLE forbidden (value TEXT)")
                except sqlite3.DatabaseError:
                    pass
                else:
                    raise AssertionError("write through immutable protected connection was not blocked")

            with sqlite3.connect(sandbox, uri=True) as connection:
                try:
                    connection.execute("ATTACH DATABASE ? AS protected", (protected,))
                except sqlite3.DatabaseError:
                    pass
                else:
                    raise AssertionError("plain protected ATTACH was not blocked")

            with sqlite3.connect(sandbox, uri=True) as connection:
                escaped_uri = protected_uri.replace("'", "''")
                connection.execute("ATTACH DATABASE '" + escaped_uri + "' AS protected")
                assert connection.execute("SELECT value FROM protected.probe").fetchone()[0] == "unchanged"
                try:
                    connection.execute("INSERT INTO protected.probe VALUES ('forbidden')")
                except sqlite3.DatabaseError:
                    pass
                else:
                    raise AssertionError("write through protected ATTACH was not blocked")
            """
        )
        guarded = subprocess.run(
            [sys.executable, "-B", "-c", child_code],
            cwd=sandbox_root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if guarded.returncode != 0:
            raise AssertionError(
                "guard fixture failed:\n" + guarded.stdout + "\n" + guarded.stderr
            )

        after = formal._fingerprint_roots(fixture_root, (protected_root,))
        assert formal._fingerprint_changes(before, after) == {}
        ready_events = [
            json.loads(line)
            for line in ready_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        violation_events = [
            json.loads(line)
            for line in violation_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(item["event"] == "guard_ready" for item in ready_events)
        event_names = {item["event"] for item in violation_events}
        assert {
            "protected_connect_blocked",
            "protected_attach_blocked",
            "protected_write_blocked",
            "protected_filesystem_write_blocked",
        }.issubset(event_names)
        evidence_log = evidence_root / "logs" / "001-fixture.log"
        evidence_log.parent.mkdir()
        evidence_log.write_text("fixture log\n", encoding="utf-8")
        writable_state_evidence = evidence_root / "writable-state" / "001-fixture.json"
        writable_state_evidence.parent.mkdir()
        writable_state_evidence.write_text("{}\n", encoding="utf-8")
        persistent_evidence = fixture_root / "persistent-evidence"
        formal._persist_evidence(evidence_root, persistent_evidence)
        assert (persistent_evidence / "logs" / evidence_log.name).read_text(
            encoding="utf-8"
        ) == "fixture log\n"
        assert (persistent_evidence / ready_log.name).is_file()
        assert (persistent_evidence / violation_log.name).is_file()
        assert (
            persistent_evidence / "writable-state" / writable_state_evidence.name
        ).read_text(encoding="utf-8") == "{}\n"

        probe = fixture_root / "must-not-run.py"
        probe.write_text("raise AssertionError('wrapper ran without guard')\n", encoding="utf-8")
        missing_guard_environment = dict(os.environ)
        missing_guard_environment["PYTHONPATH"] = ""
        missing_guard_environment["SCQ_FORMAL_STORAGE_GUARD_REQUIRED"] = "1"
        missing_guard = subprocess.run(
            [
                sys.executable,
                "-B",
                str(Path(__file__).resolve().parent / "_run_formal_isolated.py"),
                str(probe),
            ],
            cwd=fixture_root,
            env=missing_guard_environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert missing_guard.returncode == 97
        assert "storage guard was not loaded" in missing_guard.stderr

        built_environment = formal._build_environment(
            project_root=project_root,
            snapshot_root=sandbox_root,
            evidence_root=evidence_root,
        )
        expected_temp = str(sandbox_root / "tmp" / "system-temp")
        assert {built_environment[key] for key in ("TEMP", "TMP", "TMPDIR")} == {
            expected_temp
        }
        assert built_environment["SCQ_ENABLE_DEMO_SEED"] == "1"
        assert built_environment["PYTHONDONTWRITEBYTECODE"] == "1"
        assert built_environment["NO_PROXY"] == "127.0.0.1,localhost"
        assert all(key not in built_environment for key in formal._EXTERNAL_ENVIRONMENT_KEYS)
        assert "SCQ_FORMAL_SOURCE_A_SHARE_CANONICAL_DB_PATH" not in built_environment
        assert Path(built_environment["SCQ_A_SHARE_CANONICAL_DB_PATH"]).is_relative_to(
            sandbox_root
        )
        assert Path(built_environment["SCQ_BACKTEST_RUNTIME_DB_PATH"]).is_relative_to(
            sandbox_root
        )
        for script_name in script_list:
            script_environment = formal._build_script_environment(
                script_name=script_name,
                base_environment=built_environment,
                formal_source_database=protected_database,
            )
            has_formal_source = (
                "SCQ_FORMAL_SOURCE_A_SHARE_CANONICAL_DB_PATH" in script_environment
            )
            assert has_formal_source is (script_name in formal._FORMAL_SOURCE_SCRIPTS)
            if has_formal_source:
                assert script_environment[
                    "SCQ_FORMAL_SOURCE_A_SHARE_CANONICAL_DB_PATH"
                ] == str(protected_database.resolve())
            if Path(script_name).suffix == ".mjs":
                assert all(
                    key not in script_environment
                    for key in (
                        "SCQ_FORMAL_PROTECTED_ROOTS",
                        "SCQ_FORMAL_STORAGE_GUARD_LOG",
                        "SCQ_FORMAL_STORAGE_GUARD_READY_LOG",
                        "SCQ_FORMAL_STORAGE_GUARD_REQUIRED",
                    )
                )
            else:
                assert script_environment["SCQ_FORMAL_STORAGE_GUARD_REQUIRED"] == "1"

        try:
            formal._reset_per_script_writable_state(
                fixture_root, project_root=fixture_root
            )
        except formal.FormalVerificationIsolationError as error:
            assert "unexpected formal snapshot path" in str(error)
        else:
            raise AssertionError("project/fixture root was accepted as a snapshot")

        wrong_anchor_snapshot = (
            fixture_root / "formal-verification" / "formal-wrong-anchor" / "source"
        )
        wrong_anchor_snapshot.mkdir(parents=True)
        try:
            formal._write_formal_snapshot_marker(
                wrong_anchor_snapshot, project_root=fixture_root
            )
        except formal.FormalVerificationIsolationError as error:
            assert "not anchored" in str(error)
        else:
            raise AssertionError("snapshot outside project tmp was accepted")

        tampered_snapshot = (
            fixture_root
            / "tmp"
            / "formal-verification"
            / "formal-tampered"
            / "source"
        )
        tampered_snapshot.mkdir(parents=True)
        formal._write_formal_snapshot_marker(
            tampered_snapshot, project_root=fixture_root
        )
        (tampered_snapshot / formal._FORMAL_SNAPSHOT_MARKER).write_text(
            json.dumps({"format": 1, "snapshot_root": str(protected_root)}),
            encoding="utf-8",
        )
        try:
            formal._reset_per_script_writable_state(
                tampered_snapshot, project_root=fixture_root
            )
        except formal.FormalVerificationIsolationError as error:
            assert "does not bind this root" in str(error)
        else:
            raise AssertionError("tampered snapshot marker was accepted")

        redirected_snapshot = (
            fixture_root
            / "tmp"
            / "formal-verification"
            / "formal-redirected"
            / "source"
        )
        redirected_runtime = redirected_snapshot / "var" / "runtime"
        redirected_runtime.mkdir(parents=True)
        formal._write_formal_snapshot_marker(
            redirected_snapshot, project_root=fixture_root
        )
        real_is_link_or_reparse = formal._is_link_or_reparse

        def flag_runtime_as_redirect(path: Path) -> bool:
            return path == redirected_runtime or real_is_link_or_reparse(path)

        formal._is_link_or_reparse = flag_runtime_as_redirect
        try:
            try:
                formal._reset_per_script_writable_state(
                    redirected_snapshot, project_root=fixture_root
                )
            except formal.FormalVerificationIsolationError as error:
                assert "symlink or junction" in str(error)
            else:
                raise AssertionError("redirected writable root was accepted")
        finally:
            formal._is_link_or_reparse = real_is_link_or_reparse

        sequence_snapshot = (
            fixture_root
            / "tmp"
            / "formal-verification"
            / "formal-sequence-fixture"
            / "source"
        )
        sequence_scripts = sequence_snapshot / "scripts"
        sequence_evidence = fixture_root / "sequence-evidence"
        sequence_scripts.mkdir(parents=True)
        sequence_evidence.mkdir()
        (sequence_snapshot / "tmp" / "system-temp").mkdir(parents=True)
        (sequence_snapshot / "var" / "market").mkdir(parents=True)
        (sequence_snapshot / "var" / "runtime").mkdir(parents=True)
        formal._write_formal_snapshot_marker(
            sequence_snapshot, project_root=fixture_root
        )
        shutil.copy2(
            Path(__file__).resolve().parent / "_run_formal_isolated.py",
            sequence_scripts / "_run_formal_isolated.py",
        )
        ordinary_marker = sequence_snapshot / "ordinary-pass-ran.txt"
        (sequence_scripts / "ordinary-fail.py").write_text(
            "import os\n"
            "import sqlite3\n"
            "from pathlib import Path\n"
            "runtime = Path(os.environ['SCQ_BACKTEST_RUNTIME_DB_PATH']).parent\n"
            "(runtime / 'script-a-marker.txt').write_text('a', encoding='utf-8')\n"
            "with sqlite3.connect(runtime / 'script-a.sqlite3') as connection:\n"
            "    connection.execute('CREATE TABLE probe (value TEXT)')\n"
            "    connection.execute(\"INSERT INTO probe VALUES ('a')\")\n"
            "raise SystemExit(9)\n",
            encoding="utf-8",
        )
        (sequence_scripts / "ordinary-pass.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            "runtime = Path(os.environ['SCQ_BACKTEST_RUNTIME_DB_PATH']).parent\n"
            "assert not (runtime / 'script-a-marker.txt').exists()\n"
            "assert not (runtime / 'script-a.sqlite3').exists()\n"
            "(runtime / 'script-b-marker.txt').write_text('b', encoding='utf-8')\n"
            f"Path({str(ordinary_marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        sequence_environment = formal._build_environment(
            project_root=fixture_root,
            snapshot_root=sequence_snapshot,
            evidence_root=sequence_evidence,
        )
        sequence_environment["PYTHONPATH"] = os.pathsep.join(
            (str(guard_directory), str(project_root))
        )
        sequence_environment["SCQ_FORMAL_PROTECTED_ROOTS"] = str(protected_root)
        sequence_environment["SCQ_TEST_PROTECTED_PATH"] = str(protected_database)
        evidence_sentinel = sequence_evidence / "must-survive-resets.txt"
        evidence_sentinel.write_text("outside snapshot\n", encoding="utf-8")
        sequence_before = formal._fingerprint_roots(fixture_root, (protected_root,))
        ordinary_results, ordinary_fatal = formal._execute_script_sequence(
            ["ordinary-fail.py", "ordinary-pass.py"],
            project_root=fixture_root,
            protected_roots=(protected_root,),
            protected_baseline=sequence_before,
            snapshot_root=sequence_snapshot,
            base_environment=sequence_environment,
            evidence_root=sequence_evidence,
            formal_source_database=protected_database,
        )
        assert ordinary_fatal is None
        assert [item.status for item in ordinary_results] == ["failed", "passed"]
        assert ordinary_results[0].failure_type == "FormalVerificationTestFailure"
        assert ordinary_marker.read_text(encoding="utf-8") == "ran"
        assert evidence_sentinel.read_text(encoding="utf-8") == "outside snapshot\n"
        first_state_path = sequence_evidence / str(
            ordinary_results[0].writable_state_evidence
        )
        second_state_path = sequence_evidence / str(
            ordinary_results[1].writable_state_evidence
        )
        first_state = json.loads(first_state_path.read_text(encoding="utf-8"))
        second_state = json.loads(second_state_path.read_text(encoding="utf-8"))
        first_paths = {
            entry["path"]
            for root in first_state["roots"]
            for entry in root["entries"]
        }
        second_paths = {
            entry["path"]
            for root in second_state["roots"]
            for entry in root["entries"]
        }
        assert {"script-a-marker.txt", "script-a.sqlite3"}.issubset(first_paths)
        assert "script-a-marker.txt" not in second_paths
        assert "script-a.sqlite3" not in second_paths
        assert "script-b-marker.txt" in second_paths
        assert first_state["content_copied"] is False
        assert second_state["content_copied"] is False
        ordinary_summary = formal._summarize_script_results(
            ["ordinary-fail.py", "ordinary-pass.py"],
            ordinary_results,
            ordinary_fatal,
        )
        assert ordinary_summary["suite_completed"] is True
        assert ordinary_summary["run_outcome"] == "completed_with_test_failures"
        assert ordinary_summary["unattempted"] == []
        assert len(ordinary_summary["test_failures"]) == 1
        assert ordinary_summary["completed_scripts"] == [
            "ordinary-fail.py",
            "ordinary-pass.py",
        ]
        assert ordinary_summary["passed_scripts"] == ["ordinary-pass.py"]
        ordinary_reset_summary = formal._summarize_per_script_writable_state_resets(
            ["ordinary-fail.py", "ordinary-pass.py"], ordinary_results
        )
        assert ordinary_reset_summary == {
            "policy_enabled": True,
            "successful_reset_count": 2,
            "expected_reset_count": 2,
            "completed_for_entire_suite": True,
        }

        real_reset_writable_state = formal._reset_per_script_writable_state

        def reject_first_reset(*_args: object, **_kwargs: object) -> object:
            raise formal.FormalVerificationIsolationError("fixture reset refused")

        formal._reset_per_script_writable_state = reject_first_reset
        try:
            reset_failure_results, reset_failure_fatal = (
                formal._execute_script_sequence(
                    ["ordinary-pass.py"],
                    project_root=fixture_root,
                    protected_roots=(protected_root,),
                    protected_baseline=sequence_before,
                    snapshot_root=sequence_snapshot,
                    base_environment=sequence_environment,
                    evidence_root=sequence_evidence,
                    formal_source_database=protected_database,
                )
            )
        finally:
            formal._reset_per_script_writable_state = real_reset_writable_state
        assert isinstance(
            reset_failure_fatal, formal.FormalVerificationIsolationError
        )
        assert len(reset_failure_results) == 1
        assert reset_failure_results[0].status == "fatal"
        assert reset_failure_results[0].writable_state_reset is False
        assert reset_failure_results[0].writable_state_evidence is None
        assert formal._summarize_per_script_writable_state_resets(
            ["ordinary-pass.py"], reset_failure_results
        ) == {
            "policy_enabled": True,
            "successful_reset_count": 0,
            "expected_reset_count": 1,
            "completed_for_entire_suite": False,
        }

        guard_stop_marker = sequence_snapshot / "guard-stop-must-not-run.txt"
        (sequence_scripts / "guard-violation.py").write_text(
            "import os\n"
            "open(os.environ['SCQ_TEST_PROTECTED_PATH'], 'wb').close()\n",
            encoding="utf-8",
        )
        (sequence_scripts / "guard-stop-must-not-run.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(guard_stop_marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        guard_results, guard_fatal = formal._execute_script_sequence(
            ["guard-violation.py", "guard-stop-must-not-run.py"],
            project_root=fixture_root,
            protected_roots=(protected_root,),
            protected_baseline=sequence_before,
            snapshot_root=sequence_snapshot,
            base_environment=sequence_environment,
            evidence_root=sequence_evidence,
            formal_source_database=protected_database,
        )
        assert isinstance(guard_fatal, formal.FormalVerificationIsolationError)
        assert [item.status for item in guard_results] == ["fatal"]
        assert not guard_stop_marker.exists()
        guard_summary = formal._summarize_script_results(
            ["guard-violation.py", "guard-stop-must-not-run.py"],
            guard_results,
            guard_fatal,
        )
        assert guard_summary["suite_completed"] is False
        assert guard_summary["run_outcome"] == "fatal_failure"
        assert guard_summary["test_failures"] == []
        assert guard_summary["unattempted"] == ["guard-stop-must-not-run.py"]

        fingerprint_marker = protected_root / "fingerprint-probe.txt"
        fingerprint_marker.write_text("before", encoding="utf-8")
        fingerprint_before = formal._fingerprint_roots(
            fixture_root, (protected_root,)
        )
        fingerprint_calls: list[str] = []
        real_run_script = formal._run_script

        def fake_run_script(script_name: str, **kwargs: object) -> object:
            fingerprint_calls.append(script_name)
            if script_name == "fingerprint-mutation.py":
                fingerprint_marker.write_text("after", encoding="utf-8")
            sequence = int(kwargs["sequence"])
            return formal.FormalScriptResult(
                sequence=sequence,
                script_name=script_name,
                status="passed",
                exit_code=0,
                log_path=f"logs/{sequence:03d}-{script_name}.log",
            )

        formal._run_script = fake_run_script
        try:
            fingerprint_results, fingerprint_fatal = formal._execute_script_sequence(
                ["fingerprint-mutation.py", "fingerprint-stop-must-not-run.py"],
                project_root=fixture_root,
                protected_roots=(protected_root,),
                protected_baseline=fingerprint_before,
                snapshot_root=sequence_snapshot,
                base_environment=sequence_environment,
                evidence_root=sequence_evidence,
                formal_source_database=protected_database,
            )
        finally:
            formal._run_script = real_run_script
        assert isinstance(
            fingerprint_fatal, formal.FormalVerificationIsolationError
        )
        assert [item.status for item in fingerprint_results] == ["fatal"]
        assert fingerprint_results[0].log_path is None
        assert fingerprint_calls == ["fingerprint-mutation.py"]

        final_fingerprint_failure = formal._promote_final_fingerprint_failure(
            None,
            fingerprints_paired=True,
            changes={"protected": {"before": {}, "after": {"changed": True}}},
        )
        final_fingerprint_summary = formal._summarize_script_results(
            ["ordinary-fail.py", "ordinary-pass.py"],
            ordinary_results,
            final_fingerprint_failure,
        )
        assert isinstance(
            final_fingerprint_failure, formal.FormalVerificationIsolationError
        )
        assert final_fingerprint_summary["run_outcome"] == "fatal_failure"
        assert final_fingerprint_summary["suite_completed"] is False
        assert len(final_fingerprint_summary["test_failures"]) == 1
        assert final_fingerprint_summary["unattempted"] == []

        source_calls: list[str] = []
        source_script = "smoke_test_a_share_source_database.py"
        real_run_script = formal._run_script
        real_source_identity = formal._formal_source_identity
        identity_values = iter(({"identity": "before"}, {"identity": "after"}))

        def fake_source_run(script_name: str, **kwargs: object) -> object:
            source_calls.append(script_name)
            sequence = int(kwargs["sequence"])
            return formal.FormalScriptResult(
                sequence=sequence,
                script_name=script_name,
                status="passed",
                exit_code=0,
                log_path=f"logs/{sequence:03d}-{script_name}.log",
            )

        formal._run_script = fake_source_run
        formal._formal_source_identity = lambda _path: next(identity_values)
        try:
            source_results, source_fatal = formal._execute_script_sequence(
                [source_script, "source-identity-stop-must-not-run.py"],
                project_root=fixture_root,
                protected_roots=(protected_root,),
                protected_baseline=formal._fingerprint_roots(
                    fixture_root, (protected_root,)
                ),
                snapshot_root=sequence_snapshot,
                base_environment=sequence_environment,
                evidence_root=sequence_evidence,
                formal_source_database=protected_database,
            )
        finally:
            formal._run_script = real_run_script
            formal._formal_source_identity = real_source_identity
        assert isinstance(source_fatal, formal.FormalVerificationIsolationError)
        assert [item.status for item in source_results] == ["fatal"]
        assert source_results[0].log_path is None
        assert source_calls == [source_script]

    print("formal verification isolation smoke passed")


if __name__ == "__main__":
    main()
