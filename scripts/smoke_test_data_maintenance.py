"""隔离验证数据维护的失败原子性、缓存重试、幂等及读事务保护。"""
from _project_bootstrap import ensure_project_root_on_sys_path
ensure_project_root_on_sys_path()
import sqlite3
import tempfile
import threading
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from data_platform import AShareMarketStore, AShareGovernanceStore, AShareSyncScheduler
from data_platform.storage.data_center_store import DataCenterStore
from data_platform.data_maintenance import DataMaintenance
from data_platform.maintenance_transaction import maintenance_transaction, stable_research_read, require_current_input
from smoke_test_stage78_2_incremental_scheduler import FakeProvider


def main():
    with tempfile.TemporaryDirectory(prefix="maintenance-") as directory:
        path = Path(directory) / "market.sqlite3"
        market, governance = AShareMarketStore(path), AShareGovernanceStore(path)
        provider = FakeProvider()
        provider.fail_once.clear()
        scheduler = AShareSyncScheduler(path, provider=provider, requests_per_minute=1000000,
                                       retry_count=1, sleep=lambda _: None, base_backoff_seconds=0)
        scheduler.ensure_schema()
        DataCenterStore(path).ensure_schema()
        market.replace_current_symbols([{"symbol": "000001", "name": "sample"}])
        manager = DataMaintenance(scheduler)
        batch = manager.create(target_trade_date="2026-01-08")
        provider.fail_always.add(("000001", "hfq"))
        failed = manager.run(batch["batch_id"])
        assert failed["status"] == "failed", failed
        with closing(sqlite3.connect(path)) as c:
            assert c.execute("SELECT COUNT(*) FROM market_daily_prices").fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM data_versions").fetchone()[0] == 0
        previous_calls = list(provider.calls)
        provider.fail_always.clear()
        passed = manager.run(batch["batch_id"])
        assert passed["status"] == "completed", passed
        assert [call[1] for call in provider.calls[len(previous_calls):]] == ["hfq"], provider.calls
        with closing(sqlite3.connect(path)) as c:
            assert c.execute("SELECT COUNT(*) FROM market_daily_prices").fetchone()[0] == 3
            assert c.execute("SELECT setting_value FROM data_center_settings WHERE setting_key='default_data_version_id'").fetchone()[0] == passed["result"]["data_version_id"]
        assert manager.run(batch["batch_id"])["result"] == passed["result"]
        with closing(sqlite3.connect(manager.state_path)) as c:
            assert c.execute('SELECT COUNT(*) FROM downloads').fetchone()[0] == 0
        # 模拟主库已提交、任务状态尚未记录时进程退出：重试只恢复凭据。
        manager.update(batch['batch_id'], 'interrupted', 'needs_attention')
        calls_before_recovery = list(provider.calls)
        recovered = manager.run(batch['batch_id'])
        assert recovered['status'] == 'completed' and recovered['result']['recovered']
        assert provider.calls == calls_before_recovery
        owner = SimpleNamespace(_maintenance_database_path=path)
        require_current_input(owner, {'data_version_id': passed['result']['data_version_id']})
        try:
            require_current_input(owner, {'data_version_id': 'scq-historical-unretained'})
        except ValueError as error:
            assert 'historical_input_not_retained' in str(error)
        else:
            raise AssertionError('historical input silently used current prices')
        noop = manager.run(manager.create(target_trade_date="2026-01-08")["batch_id"])
        assert noop["status"] == "completed_noop", noop
        with closing(sqlite3.connect(path)) as c:
            assert c.execute("SELECT COUNT(*) FROM data_versions").fetchone()[0] == 1
        # 有有效基线时，后续失败也不能泄漏部分更新。
        next_batch = manager.create(target_trade_date='2026-01-09')
        provider.fail_always.add(('000001', 'hfq'))
        assert manager.run(next_batch['batch_id'])['status'] == 'failed'
        with closing(sqlite3.connect(path)) as c:
            assert c.execute("SELECT MAX(trade_date) FROM market_daily_prices").fetchone()[0] == '2026-01-08'
            assert c.execute("SELECT setting_value FROM data_center_settings WHERE setting_key='default_data_version_id'").fetchone()[0] == passed['result']['data_version_id']
        with closing(sqlite3.connect(manager.state_path)) as c, c:
            c.execute("UPDATE downloads SET content_hash='corrupt' WHERE batch_id=?", (next_batch['batch_id'],))
        damaged = manager.run(next_batch['batch_id'])
        assert damaged['status'] == 'failed' and '缓存校验失败' in damaged['result']['error']
        # 此处仅调用内存 FakeProvider，验证已经获准运行的指定任务会自动复检。
        from app.services.data_center_service import DataCenterService
        service = DataCenterService(DataCenterStore(path), scheduler, governance)
        with closing(sqlite3.connect(path)) as c, c:
            c.execute("UPDATE market_daily_prices SET high=9 WHERE adjustment='raw'")
        scan = service.quality_scan_engine.create_scan(
            dataset='a_share_daily', date_from='2026-01-08', date_to='2026-01-08',
            scope='symbols', symbols=['000001'], adjustments=['raw'], rules=['ohlcv_validity'])
        service.quality_scan_engine.run_scan(scan['scan_id'])
        issue = service.store.list_issues(source_task_id=scan['scan_id'])[0]
        refetch = service.refetch_quality_issue(issue['issue_id'], run_now=False)
        refetched = scheduler.run_job(refetch['task_id'])
        assert refetched['status'] == 'published', refetched
        assert service.store.get_issue(issue['issue_id'])['status'] == 'corrected'
        # 读锁允许更新准备，但生效必须等待研究结束。
        prepared, finished = threading.Event(), threading.Event()
        def update():
            with maintenance_transaction(path) as c:
                c.execute("UPDATE market_daily_prices SET close=11")
                prepared.set()
            finished.set()
        with stable_research_read(path):
            thread = threading.Thread(target=update)
            thread.start()
            assert prepared.wait(5)
            assert not finished.wait(0.1)
            with closing(sqlite3.connect(path)) as c:
                assert c.execute("SELECT close FROM market_daily_prices WHERE adjustment='raw'").fetchone()[0] == 10.2
        thread.join(5)
        assert finished.is_set()
    print("data maintenance atomicity/cache/noop/read-guard passed")


if __name__ == "__main__":
    main()
