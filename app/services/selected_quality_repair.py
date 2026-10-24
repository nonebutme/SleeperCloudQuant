"""用户显式选择的价格修复：限定写入、整批复检、一次原子生效。"""
from datetime import date
from hashlib import sha256
import json
import math
import uuid

from data_platform.maintenance_transaction import maintenance_transaction, materialize_price_corrections, record_activation


FIELDS = frozenset(('open', 'high', 'low', 'close', 'volume', 'amount', 'amplitude',
                    'change_pct', 'change_amount', 'turnover_rate'))


def selected_issues(service, ids, *, allow_pending=False):
    ids = list(ids)
    if not 1 <= len(ids) <= 50 or any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('须明确选择 1–50 个不重复的问题')
    issues = [service.store.get_issue(i) for i in ids]
    if len({(i['dataset'], i['rule_id']) for i in issues}) != 1:
        raise ValueError('仅支持同一数据集、同一规则的勾选项')
    for issue in issues:
        if issue['dataset'] != 'a_share_daily' or issue['rule_id'] not in {
            'ohlcv_validity', 'missing_open_day', 'adjustment_date_consistency',
        }:
            raise ValueError('该问题须使用对应的授权证据修复流程')
        if issue['status'] not in {'open', 'quarantined'}:
            raise ValueError('勾选项已处理，请刷新；不会重复执行')
        history = service.store.get_issue_history(issue['issue_id'])
        pending = [x for x in history['overlays'] if x['status'] == 'pending_publish']
        active = [x for x in history['remediations'] if x['status'] in {'remediating', 'awaiting_publish', 'awaiting_recheck'}]
        reviewed_pending = (allow_pending and len(pending) == 1 and bool(active) and all(
            x['status'] == 'awaiting_publish' and x['executor_id'] == pending[0]['overlay_id'] for x in active))
        if (active or pending) and not reviewed_pending:
            raise ValueError('勾选项已有未完成修复，请先完成或处置原任务')
        parent = service.quality_scan_engine.get_scan(str(issue.get('source_task_id') or ''))
        scope = scope_for(issue)
        if (parent['dataset'] != issue['dataset'] or issue['rule_id'] not in parent['rules']
                or scope['start_date'] < parent['date_from'] or scope['end_date'] > parent['date_to']
                or (parent['scope'] == 'symbols' and scope['symbol'] not in parent['symbols'])
                or set(scope['adjustments']) - set(parent['adjustments'])):
            raise ValueError('问题与原检查范围不一致，不能自动关闭')
    return issues


def scope_for(issue):
    evidence = issue.get('evidence') or {}
    target = str(issue.get('observation_at') or '')[:10]
    start = target
    adjustments = [str(evidence.get('adjustment') or '')]
    if issue['rule_id'] == 'missing_open_day':
        start = str(evidence.get('first_missing_date') or target)[:10]
        target = str(evidence.get('last_missing_date') or target)[:10]
    elif issue['rule_id'] == 'adjustment_date_consistency':
        adjustments = list(evidence.get('missing_adjustments') or [])
    if not issue.get('symbol') or not adjustments or set(adjustments) - {'raw', 'qfq', 'hfq'}:
        raise ValueError('勾选项缺少明确的证券或复权范围')
    if date.fromisoformat(start) > date.fromisoformat(target):
        raise ValueError('勾选项日期范围无效')
    return dict(symbol=str(issue['symbol']), start_date=start, end_date=target, adjustments=adjustments)


def correction_preview(service, ids):
    with maintenance_transaction(service.store.database_path) as connection:
        issues = selected_issues(service, ids, allow_pending=True)
        result = []
        for issue in issues:
            if issue['rule_id'] != 'ohlcv_validity':
                raise ValueError('整批纠错仅支持 OHLCV 数值问题')
            scope = scope_for(issue)
            row = connection.execute(
                'SELECT * FROM market_daily_prices WHERE symbol=? AND trade_date=? AND adjustment=?',
                (scope['symbol'], scope['start_date'], scope['adjustments'][0]),
            ).fetchone()
            if row is None:
                raise ValueError('规范行情已不存在，请刷新检查')
            before = {k: row[k] for k in sorted(FIELDS)}
            pending = [x for x in service.store.get_issue_history(issue['issue_id'])['overlays'] if x['status']=='pending_publish']
            result.append(dict(issue_id=issue['issue_id'], scope=scope, before=before,
                               after=pending[0]['after'] if pending else {}))
        return {'items': result}


class ScopedPriceStore:
    """只暴露行情读取和授权键写入；上游返回范围外数据时整批拒绝。"""
    def __init__(self, store, scope, adjustment, allowed_dates):
        self._store, self.scope, self.adjustment = store, scope, adjustment
        self.allowed_dates = allowed_dates
        self.written = 0
        self.written_keys = set()

    def fetch_daily_prices(self, **kwargs):
        return self._store.fetch_daily_prices(**kwargs)

    def upsert_daily_prices(self, rows, *, adjustment, source):
        rows = list(rows)
        for row in rows:
            day = str(row.get('date') or row.get('trade_date') or '')
            if (str(row.get('symbol') or '') != self.scope['symbol'] or adjustment != self.adjustment
                    or not self.scope['start_date'] <= day <= self.scope['end_date']):
                raise ValueError('上游返回超出本次勾选范围的数据，整批撤回')
        # 缺口问题只补缺失键，不覆盖窗口内原有的正常行情。
        rows = [r for r in rows if self.allowed_dates is None or
                str(r.get('date') or r.get('trade_date') or '') in self.allowed_dates]
        written = self._store.upsert_daily_prices(rows, adjustment=adjustment, source=source)
        self.written += written
        self.written_keys.update((str(r['symbol']), str(r.get('date') or r.get('trade_date')), adjustment) for r in rows)
        return written


def execute_selected(service, ids, *, action, reason, operator, corrections=()):
    if not reason.strip():
        raise ValueError('请填写本次处理依据')
    if action not in {'correct', 'refetch'}:
        raise ValueError('不支持的自动修复操作')
    with maintenance_transaction(service.store.database_path) as connection:
        issues = selected_issues(service, ids, allow_pending=action == 'correct')
        scopes = [scope_for(i) for i in issues]
        versions = service.store.list_versions()
        base = versions.get('default_version')
        if not base or base['data_version_id'] != (versions.get('latest_published_version') or {}).get('data_version_id'):
            raise ValueError('须先建立与最新检查一致的当前可用数据')
        base_id = base['data_version_id']
        base_version = service.governance_store.fetch_data_version(base_id)
        if any(scope['end_date'] > str(base_version['as_of_trade_date']) for scope in scopes):
            raise ValueError('问题超出当前数据截止日，请先执行数据更新；定向修复不扩展截止日')
        batch_id = 'selected-repair-' + uuid.uuid4().hex
        evidence = []
        overlay_ids = []
        if action == 'correct':
            corrections = list(corrections)
            if (any(not isinstance(c, dict) for c in corrections) or len(corrections) != len(ids)
                    or {c.get('issue_id') for c in corrections} != set(ids)):
                raise ValueError('修正值必须与本次勾选 ID 一一对应，不得遗漏、重复或夹带')
            mapping = {c['issue_id']: c for c in corrections}
            seen = set()
            for issue, scope in zip(issues, scopes):
                if issue['rule_id'] != 'ohlcv_validity':
                    raise ValueError('整批纠错仅支持 OHLCV 数值问题')
                key = (scope['symbol'], scope['start_date'], scope['adjustments'][0])
                if key in seen:
                    raise ValueError('多个勾选项指向同一行情键，请合并后提交')
                seen.add(key)
                correction = mapping[issue['issue_id']]
                before, after = correction.get('before'), correction.get('after')
                if not isinstance(before, dict) or not isinstance(after, dict) or not after or set(after) - FIELDS or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in after.values()
                ):
                    raise ValueError('请逐项填写合法价格字段及有限数值')
                row = connection.execute('SELECT * FROM market_daily_prices WHERE symbol=? AND trade_date=? AND adjustment=?', key).fetchone()
                if row is None or any(k not in before or row[k] != before[k] for k in after):
                    raise ValueError('原值已变化或缺失，请重新预览；整批未生效')
                pending = [x for x in service.store.get_issue_history(issue['issue_id'])['overlays'] if x['status']=='pending_publish']
                if pending:
                    if pending[0]['after'] != after or any(pending[0]['before'].get(k) != before[k] for k in after):
                        raise ValueError('已有待纠错证据与确认值不一致，请先核对原记录；不自动替换候选')
                else:
                    service.store.disposition_issue(issue['issue_id'], action='correct', reason=reason,
                                                    operator=operator, before=before, after=after)
                    pending = [x for x in service.store.get_issue_history(issue['issue_id'])['overlays'] if x['status']=='pending_publish']
                service.store.mark_overlay_published(issue['issue_id'], data_version_id=base_id)
                overlay_ids.append(pending[0]['overlay_id'])
                connection.execute('UPDATE market_daily_prices SET ' + ','.join(k + '=?' for k in after)
                                   + ' WHERE symbol=? AND trade_date=? AND adjustment=?', (*after.values(), *key))
                evidence.append(correction)
        else:
            for issue in issues:
                service._validate_quality_refetch_issue(issue)
            service.store.freeze_route_snapshot('a_share_daily', task_id=batch_id)
            service.scheduler._apply_effective_config(service.store.effective_route_config('a_share_daily'))
            for issue, scope in zip(issues, scopes):
                remediation = service.store.create_remediation(issue['issue_id'], method='refetch',
                    executor_type='selected_price_repair', executor_id=batch_id, reason=reason, operator=operator)
                for adjustment in scope['adjustments']:
                    allowed_dates = None
                    if issue['rule_id'] != 'ohlcv_validity':
                        existing = {r[0] for r in connection.execute(
                            'SELECT trade_date FROM market_daily_prices WHERE symbol=? AND adjustment=? AND trade_date BETWEEN ? AND ?',
                            (scope['symbol'], adjustment, scope['start_date'], scope['end_date']))}
                        dates = {r[0] for r in connection.execute(
                            "SELECT trade_date FROM market_trade_calendar WHERE market='CN' AND is_open=1 AND trade_date BETWEEN ? AND ?",
                            (scope['start_date'], scope['end_date']))}
                        allowed_dates = dates - existing
                    scoped = ScopedPriceStore(service.scheduler.market_store, scope, adjustment, allowed_dates)
                    if not service.scheduler._provider_controls_rate:
                        service.scheduler._rate_limiter.acquire()
                    result = service.scheduler.provider.sync_symbol(scoped, symbol=scope['symbol'], adjustment=adjustment,
                        start_date=scope['start_date'], end_date=scope['end_date'])
                    if result.get('status') != 'completed' or scoped.written == 0:
                        raise ValueError('勾选项未获得有效行情，整批撤回')
                    # 只保留这些已授权行情键上的既有生效修正；不发布任何待处理覆盖层。
                    materialize_price_corrections(connection, base_id, selected_price_keys=scoped.written_keys)
                    evidence.append(dict(issue_id=issue['issue_id'], scope=scope, adjustment=adjustment, result=result))
                service.store.update_remediation(remediation['remediation_id'], status='awaiting_recheck', data_version_id=base_id)
        scans = []
        # 原规则（例如缺口）通过不代表新价格有效；额外检查实际规范行情。
        for scope in scopes:
            scan = service.quality_scan_engine.create_scan(dataset='a_share_daily', scope='symbols',
                symbols=[scope['symbol']], date_from=scope['start_date'], date_to=scope['end_date'],
                adjustments=scope['adjustments'], rules=['ohlcv_validity'])
            if service.quality_scan_engine.run_scan(scan['scan_id'], selected_issue_ids=set(ids))['status'] != 'passed':
                raise ValueError('修复后的规范行情数值无效，整批撤回')
            scans.append(scan['scan_id'])
            digest_rows = sha256()
            for row in connection.execute('SELECT * FROM market_daily_prices WHERE symbol=? AND trade_date BETWEEN ? AND ? ORDER BY trade_date,adjustment',
                                          (scope['symbol'], scope['start_date'], scope['end_date'])):
                if row['adjustment'] in scope['adjustments']:
                    digest_rows.update(json.dumps(dict(row), sort_keys=True).encode())
            evidence.append(dict(scope=scope, physical_content_hash=digest_rows.hexdigest()))
        for parent in dict.fromkeys(i['source_task_id'] for i in issues):
            scan = service.quality_scan_engine.recheck(parent)
            checked = service.quality_scan_engine.run_scan(scan['scan_id'], selected_issue_ids=set(ids))
            if checked['status'] != 'passed':
                raise ValueError('复检仍有异常，整批修复及生效已撤回')
            scans.append(scan['scan_id'])
        if any(service.store.get_issue(i)['status'] != 'corrected' for i in ids):
            raise ValueError('勾选项未全部通过复检，整批撤回')
        if service.store.release_readiness()['status'] != 'ready':
            raise ValueError('未选问题或其他质量门禁仍阻断生效；不自动处理，整批撤回')
        payload = dict(issue_ids=list(ids), action=action, reason=reason, operator=operator,
                       base_version_id=base_id, verification_scan_ids=scans, evidence=evidence)
        digest = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        report = service.governance_store.save_quality_report(quality_report_id='dq-selected-' + digest[:24],
            rule_version='r1-selected-repair-v1', status='passed', payload=payload)
        members = service.scheduler._release_members(batch_id, str(base_version['as_of_trade_date']))
        for member in members:
            if member['dataset'] == 'market_daily_prices':
                member['content_hash'] = sha256((str(member.get('content_hash')) + digest).encode()).hexdigest()
                member['details'] = {**member.get('details', {}), 'selected_repair_evidence_hash': digest}
        service.scheduler._validate_release_member_consistency(members)
        published = service.governance_store.publish_data_version(as_of_trade_date=str(base_version['as_of_trade_date']),
            quality_report_id=report['quality_report_id'], members=members, notes='R1 selected repair; batch=' + batch_id)
        version_id = published['data_version_id']
        for overlay_id in overlay_ids:
            connection.execute('UPDATE data_correction_overlays SET data_version_id=? WHERE overlay_id=?', (version_id, overlay_id))
        for issue_id in ids:
            connection.execute('UPDATE data_quality_issues SET data_version_id=? WHERE issue_id=?', (version_id, issue_id))
            connection.execute('UPDATE data_quality_remediations SET data_version_id=? WHERE issue_id=? AND verification_scan_id IN ('
                               + ','.join('?' for _ in scans) + ')', (version_id, issue_id, *scans))
        service.store.set_default_version(version_id)
        record_activation(connection, batch_id, version_id)
        return dict(processed_count=len(ids), issue_ids=list(ids), items=[service.store.get_issue(i) for i in ids],
                    data_version_id=version_id, verification_scan_ids=scans, automatically_effective=True, batch_id=batch_id)
