"""隔离 FakeProvider：勾选范围、整批原子性、越界及未选状态保护。"""
from _project_bootstrap import ensure_project_root_on_sys_path
ensure_project_root_on_sys_path()
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile

from app.services.data_center_service import DataCenterService
from data_platform import AShareSyncScheduler
from data_platform.data_maintenance import DataMaintenance
from data_platform.storage.data_center_store import DataCenterStore
from smoke_test_stage78_2_incremental_scheduler import FakeProvider


def snapshot(path):
    with closing(sqlite3.connect(path)) as c:
        names = ['market_daily_prices', 'data_versions', 'data_center_settings', 'data_quality_issues',
                 'data_quality_remediations', 'data_correction_overlays', 'data_quality_dispositions']
        return {name: c.execute('SELECT * FROM ' + name + ' ORDER BY rowid').fetchall() for name in names}


def fails(call):
    try:
        call()
    except (ValueError, RuntimeError):
        return
    raise AssertionError('unsafe request unexpectedly succeeded')


def fixture(path):
    provider = FakeProvider()
    provider.fail_once.clear()
    scheduler = AShareSyncScheduler(path, provider=provider, requests_per_minute=1000000,
                                    retry_count=1, sleep=lambda _: None, base_backoff_seconds=0)
    scheduler.ensure_schema()
    store = DataCenterStore(path)
    store.ensure_schema()
    manager = DataMaintenance(scheduler)
    result = manager.run(manager.create(target_trade_date='2026-01-08')['batch_id'])
    assert result['status'] == 'completed', result
    service = DataCenterService(store, scheduler, scheduler.governance_store)
    with closing(sqlite3.connect(path)) as c, c:
        c.execute("UPDATE market_daily_prices SET high=9 WHERE adjustment IN ('raw','qfq')")
    scan = service.quality_scan_engine.create_scan(dataset='a_share_daily', date_from='2026-01-08',
        date_to='2026-01-08', scope='symbols', symbols=['000001'], adjustments=['raw','qfq','hfq'], rules=['ohlcv_validity'])
    service.quality_scan_engine.run_scan(scan['scan_id'])
    ids = [i['issue_id'] for i in store.list_issues(source_task_id=scan['scan_id'])]
    assert len(ids) == 2
    return service, provider, ids


def main():
    with tempfile.TemporaryDirectory(prefix='selected-repair-') as directory:
        root = Path(directory)
        service, provider, ids = fixture(root / 'correction.sqlite3')
        path = service.store.database_path
        before = snapshot(path)
        preview = service.preview_selected_corrections(ids)['items']
        corrections = [dict(issue_id=i['issue_id'], before=i['before'], after={'high':10.5}) for i in preview]
        for bad_ids, changes in [([], []), ([ids[0],ids[0]], corrections), (ids, corrections[:1]),
                                 (ids, [corrections[0], dict(corrections[1], issue_id='unselected')]),
                                 (ids, [corrections[0], dict(corrections[1], before={'high':123})]),
                                 (ids, [corrections[0], dict(corrections[1], after={'symbol':1})]),
                                 (ids, [corrections[0], dict(corrections[1], after={'high':1})])]:
            fails(lambda: service.correct_selected_issues(bad_ids, corrections=changes, reason='test', operator='tester'))
            assert snapshot(path) == before
        # 未勾选阻断项不会被顺带关闭；不能只修第一条就发布。
        fails(lambda: service.correct_selected_issues(ids[:1], corrections=corrections[:1], reason='test', operator='tester'))
        assert snapshot(path) == before
        result = service.correct_selected_issues(ids, corrections=corrections, reason='test', operator='tester')
        after = snapshot(path)
        assert result['automatically_effective'] and result['processed_count'] == 2
        assert len(after['data_versions']) == len(before['data_versions']) + 1
        assert [r for r in before['market_daily_prices'] if r[2]=='hfq'] == [r for r in after['market_daily_prices'] if r[2]=='hfq']
        fails(lambda: service.correct_selected_issues(ids, corrections=corrections, reason='test', operator='tester'))
        assert snapshot(path) == after
        # 上游第二项失败，第一项已写入也必须撤回。
        service, provider, ids = fixture(root / 'refetch.sqlite3')
        path = service.store.database_path
        before = snapshot(path)
        second = service.store.get_issue(ids[1])['evidence']['adjustment']
        provider.fail_always.add(('000001', second))
        fails(lambda: service.bulk_refetch_quality_issues(ids, reason='test', operator='tester', run_now=True))
        assert snapshot(path) == before
        provider.fail_always.clear()
        reference_calls = list(provider.reference_calls)
        result = service.bulk_refetch_quality_issues(ids, reason='test', operator='tester', run_now=True)
        after = snapshot(path)
        assert result['automatically_effective'] and len(after['data_versions']) == len(before['data_versions']) + 1
        assert provider.reference_calls == reference_calls, 'selected repair refreshed unrelated reference data'
        assert [r for r in before['market_daily_prices'] if r[2]=='hfq'] == [r for r in after['market_daily_prices'] if r[2]=='hfq']
        assert all(service.store.get_issue(i)['status']=='corrected' for i in ids)
        # 越界证券写入必须整批失败。
        service, provider, ids = fixture(root / 'escape.sqlite3')
        before = snapshot(service.store.database_path)
        original = provider.sync_symbol
        def escape(store, **kwargs):
            result = original(store, **kwargs)
            store.upsert_daily_prices([{'symbol':'999999','date':kwargs['end_date'],'close':1}],
                                      adjustment=kwargs['adjustment'], source='unsafe-test')
            return result
        provider.sync_symbol = escape
        fails(lambda: service.bulk_refetch_quality_issues(ids, reason='test', operator='tester', run_now=True))
        assert snapshot(service.store.database_path) == before
        # 未选的待发布纠错绝不消费；即使物理事实已正确也不能顺带关闭。
        service, provider, ids = fixture(root / 'pending.sqlite3')
        path = service.store.database_path
        with closing(sqlite3.connect(path)) as c, c:
            c.execute("UPDATE market_daily_prices SET high=9 WHERE adjustment='hfq'")
        parent = service.store.get_issue(ids[0])['source_task_id']
        scan = service.quality_scan_engine.recheck(parent)
        service.quality_scan_engine.run_scan(scan['scan_id'])
        extra = next(i for i in service.store.list_issues(source_task_id=scan['scan_id']) if i['evidence']['adjustment']=='hfq')
        service.store.disposition_issue(extra['issue_id'], action='correct', reason='unselected pending',
            operator='tester', before={'high':9}, after={'high':10.5})
        with closing(sqlite3.connect(path)) as c, c:
            c.execute("UPDATE market_daily_prices SET high=10.5 WHERE adjustment='hfq'")
        before = snapshot(path)
        preview = service.preview_selected_corrections(ids)['items']
        changes = [dict(issue_id=i['issue_id'], before=i['before'], after={'high':10.5}) for i in preview]
        fails(lambda: service.correct_selected_issues(ids, corrections=changes, reason='test', operator='tester'))
        assert snapshot(path) == before
        assert service.store.get_issue_history(extra['issue_id'])['overlays'][0]['status'] == 'pending_publish'
        # 用户明确把已有待纠错加入选择后，才可一并核对、生效。
        all_ids = [*ids, extra['issue_id']]
        with closing(sqlite3.connect(path)) as c, c:
            c.execute("UPDATE market_daily_prices SET high=9 WHERE adjustment='hfq'")
        preview = service.preview_selected_corrections(all_ids)['items']
        assert preview[-1]['after'] == {'high':10.5}
        changes = [dict(issue_id=i['issue_id'], before=i['before'], after={'high':10.5}) for i in preview]
        result = service.correct_selected_issues(all_ids, corrections=changes, reason='confirm selected pending', operator='tester')
        assert result['processed_count'] == 3
        assert len(service.store.get_issue_history(extra['issue_id'])['overlays']) == 1
        assert service.store.get_issue_history(extra['issue_id'])['overlays'][0]['status'] == 'published'
    print('selected repair: correction/refetch atomicity, exact selection, stale values, replay and write boundary passed')


if __name__ == '__main__':
    main()
