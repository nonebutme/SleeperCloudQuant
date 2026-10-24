"""指标定义、显式注册、当前行情计算与指标转因子应用服务。"""
import ast
from contextlib import closing
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sqlite3

from data_platform.indicators import calculate, configure, create_expression_definition, definitions, digest
from data_platform.maintenance_transaction import stable_research_read


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class IndicatorService:
    def __init__(self, market_database_path, factor_analysis_service=None):
        self.market_path=Path(market_database_path)
        self.path=Path(str(self.market_path)+'.indicators.sqlite3')
        self.factors=factor_analysis_service
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS indicator_definitions(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS indicator_configs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS indicator_cache(request_key TEXT PRIMARY KEY, config_id TEXT NOT NULL, data_version_id TEXT NOT NULL, input_hash TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS indicator_factor_links(factor_id TEXT PRIMARY KEY, config_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS indicator_factor_approvals(artifact_id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, reason TEXT NOT NULL);
            ''')
            for definition in definitions():
                c.execute('INSERT OR IGNORE INTO indicator_definitions VALUES (?,?)',(definition['indicator_id'],_dump(definition)))

    def _connect(self):
        connection=sqlite3.connect(self.path,timeout=30)
        connection.row_factory=sqlite3.Row
        return _ClosingConnection(connection)

    def list_definitions(self):
        with self._connect() as c:
            return {'items':[json.loads(r[0]) for r in c.execute('SELECT payload FROM indicator_definitions ORDER BY id')]}

    def get_definition(self, indicator_id):
        with self._connect() as c:
            row=c.execute('SELECT payload FROM indicator_definitions WHERE id=?',(indicator_id,)).fetchone()
        if row is None: raise ValueError('未知指标：'+str(indicator_id))
        return json.loads(row[0])

    def create_definition(self, *, name, expression, source_reference, test_cases):
        definition=create_expression_definition(name,expression,source_reference,test_cases)
        with self._connect() as c:
            c.execute('INSERT OR IGNORE INTO indicator_definitions VALUES (?,?)',(definition['indicator_id'],_dump(definition)))
        return self.get_definition(definition['indicator_id'])

    def register(self, *, indicator_id, parameters, adjustment, name=''):
        if adjustment not in {'raw','qfq','hfq'}: raise ValueError('请选择 raw/qfq/hfq 复权口径')
        definition=configure(self.get_definition(indicator_id),parameters)
        if definition.get('verification_status')!='sample_verified': raise ValueError('指标未通过样例校验')
        payload=dict(definition=definition,adjustment=adjustment,frequency='daily',
                     name=str(name).strip()[:80] or definition['name'],definition_hash=digest(definition))
        config_id='ic_'+digest(payload)[:24]
        payload.update(config_id=config_id,dataset_id='indicator_values')
        with self._connect() as c:
            c.execute('INSERT OR IGNORE INTO indicator_configs(id,payload) VALUES (?,?)',(config_id,_dump(payload)))
        return self.get_config(config_id,require_enabled=False)

    def get_config(self, config_id, *, require_enabled=True):
        with self._connect() as c:
            row=c.execute('SELECT payload,enabled FROM indicator_configs WHERE id=?',(config_id,)).fetchone()
        if row is None: raise ValueError('指标配置未注册：'+str(config_id))
        payload=json.loads(row['payload'])
        payload['enabled']=bool(row['enabled'])
        if require_enabled and not payload['enabled']: raise ValueError('指标配置已停用：'+str(config_id))
        if digest(payload['definition']) != payload['definition_hash']: raise ValueError('指标定义证据不一致')
        return payload

    def set_enabled(self, config_id, enabled):
        self.get_config(config_id,require_enabled=False)
        if not isinstance(enabled,bool): raise ValueError('enabled 必须是布尔值')
        with self._connect() as c:
            c.execute('UPDATE indicator_configs SET enabled=? WHERE id=?',(int(enabled),config_id))
        return self.get_config(config_id,require_enabled=False)

    def list_configs(self):
        with self._connect() as c:
            ids=[r[0] for r in c.execute('SELECT id FROM indicator_configs ORDER BY id')]
            cache={r['config_id']:dict(r) for r in c.execute('SELECT config_id,COUNT(*) AS cached_ranges FROM indicator_cache GROUP BY config_id')}
        return {'items':[{**self.get_config(i,require_enabled=False),**cache.get(i,{}),
                          'coverage_status':'cached_requires_input_check' if i in cache else 'not_computed'} for i in ids]}

    def current_version(self, connection=None):
        if connection is None:
            with closing(sqlite3.connect(f'file:{self.market_path.resolve().as_posix()}?mode=ro',uri=True)) as c:
                return self.current_version(c)
        row=connection.execute("""SELECT v.data_version_id,v.as_of_trade_date FROM data_versions v
            JOIN data_center_settings s ON s.setting_key='default_data_version_id' AND s.setting_value=v.data_version_id
            JOIN data_quality_reports q ON q.quality_report_id=v.quality_report_id
            WHERE v.status='published' AND q.status='passed'""").fetchone()
        if row is None: raise ValueError('暂无通过检查的当前行情，请先完成数据更新')
        return {'data_version_id':row[0],'as_of_trade_date':row[1]}

    def values(self, config_id, *, symbol, start_date='', end_date='', limit=2000, expected_version=''):
        config=self.get_config(config_id)
        match=re.fullmatch(r'(\d{6})(?:\.(?:XSHE|XSHG|XBSE|BSE))?',str(symbol).upper())
        if not match: raise ValueError('证券代码应为六位代码或带交易所后缀的代码')
        code=match.group(1)
        with stable_research_read(self.market_path), closing(sqlite3.connect(f'file:{self.market_path.resolve().as_posix()}?mode=ro',uri=True)) as c:
            c.row_factory=sqlite3.Row
            c.execute('BEGIN')
            version=self.current_version(c)
            if expected_version and expected_version!=version['data_version_id']:
                raise ValueError('指标只支持当前规范行情；指定历史输入未保留，不能重算')
            end=date.fromisoformat(end_date or version['as_of_trade_date']).isoformat()
            start=date.fromisoformat(start_date).isoformat() if start_date else (date.fromisoformat(end)-timedelta(days=30)).isoformat()
            if start>end or end>version['as_of_trade_date']: raise ValueError('日期范围无效或超出当前数据截止日')
            bars=[dict(r) for r in c.execute('''SELECT symbol,trade_date,open,high,low,close,volume,amount FROM market_daily_prices p
                WHERE symbol=? AND adjustment=? AND trade_date<=?
                  AND NOT EXISTS (SELECT 1 FROM security_trading_status_daily s WHERE s.symbol=p.symbol AND s.trade_date=p.trade_date AND s.is_tradable=0)
                  AND EXISTS (SELECT 1 FROM security_lifecycle_events l WHERE l.symbol=p.symbol
                    AND l.event_type IN ('listed','listed_source_observation') AND COALESCE(l.effective_from,'')<=p.trade_date
                    AND (l.effective_to IS NULL OR l.effective_to='' OR l.effective_to>=p.trade_date))
                  AND NOT EXISTS (SELECT 1 FROM security_lifecycle_events l WHERE l.symbol=p.symbol
                    AND LOWER(l.event_type) LIKE 'delist%' AND COALESCE(l.effective_from,'')<=p.trade_date)
                ORDER BY trade_date''',
                                            (code,config['adjustment'],end))]
        # 摘取一致的输入后再写旁库，避免与维护主库写锁和研究锁互相等待。
        input_hash=digest(bars)
        request_key=digest([config_id,code,start,end,limit])
        with self._connect() as c:
            cached=c.execute('SELECT * FROM indicator_cache WHERE request_key=?',(request_key,)).fetchone()
        if cached and cached['input_hash']==input_hash and cached['data_version_id']==version['data_version_id']:
            return {**json.loads(cached['payload']),'cache_hit':True}
        rows=[]
        source_values={r['trade_date']:{field:r.get(field) for field in config['definition']['input_fields']} for r in bars}
        for output in calculate(config['definition'],bars):
            if not start<=output['trade_date']<=end: continue
            rows.append({**output,'symbol':code,'config_id':config_id,'indicator_id':config['definition']['indicator_id'],
                         'adjustment':config['adjustment'],'source_values':source_values[output['trade_date']]})
        total=len(rows)
        if limit is not None: rows=rows[:min(max(int(limit),1),2000)]
        payload=dict(config=config,rows=rows,row_count=len(rows),total=total,start_date=start,end_date=end,
                     status='ready' if rows and all(r['status']=='ready' for r in rows) else 'unavailable',
                     reason='' if rows and all(r['status']=='ready' for r in rows) else '历史不足、输入缺失或当前范围无行情',
                     data_version_id=version['data_version_id'],input_hash=input_hash,cache_hit=False,
                     availability_policy='当日完整行情于收盘后可用；用于下一可交易时点决策')
        with self._connect() as c:
            c.execute('INSERT OR REPLACE INTO indicator_cache VALUES (?,?,?,?,?)',
                      (request_key,config_id,version['data_version_id'],input_hash,_dump(payload)))
        return payload

    def make_factor(self, config_id, *, output, transform, name=''):
        config=self.get_config(config_id)
        if self.factors is None: raise ValueError('因子研究服务未接入')
        if output not in config['definition']['outputs']: raise ValueError('请选择明确的指标输出')
        if transform not in {'identity','negate','price_ratio'}: raise ValueError('不支持的因子转换')
        if transform=='price_ratio' and config['definition']['unit']!='price': raise ValueError('价格偏离转换仅用于价格量纲指标')
        factor_id='indicator_'+digest([config_id,output,transform])[:24]
        definition=dict(factor_id=factor_id,factor_version='v1',name=str(name).strip()[:80] or config['name']+' 因子',
            category='指标衍生',definition_type='indicator',status='published',direction='positive',
            formula=f'{config_id}.{output} / {transform}',description='指标同源计算；研究制品需用户明确注册后供策略使用',
            input_fields=sorted(set(config['definition']['input_fields'])|({'close'} if transform=='price_ratio' else set())),
            minimum_history=config['definition']['minimum_history'],parameters=config['definition']['parameters'],
            indicator_definition=config['definition'],indicator_config_id=config_id,indicator_output=output,
            indicator_transform=transform,required_adjustment=config['adjustment'],requires_user_registration=True)
        existing=self.factors._store.get_definition(factor_id,'v1')
        if existing is None: self.factors._store.create_definition(definition)
        with self._connect() as c:
            c.execute('INSERT OR IGNORE INTO indicator_factor_links VALUES (?,?)',(factor_id,config_id))
        return self.factors.get_definition(factor_id,'v1')

    def register_factor(self, artifact_id, *, reason):
        if self.factors is None or not str(reason).strip(): raise ValueError('请填写选用该因子的分析依据')
        artifact=self.factors._store.get_artifact(artifact_id)
        definition=self.factors._store.get_definition(artifact.get('factor_id'),artifact.get('factor_version'))
        if not definition or definition.get('definition_type')!='indicator': raise ValueError('此入口只注册指标衍生因子')
        task=self.factors._store.get_task(artifact.get('source_task_id',''))
        if task.get('status')!='completed' or artifact.get('status')!='ready': raise ValueError('因子尚未通过统一审批与登记')
        if artifact.get('data_version_id')!=self.current_version()['data_version_id']: raise ValueError('因子使用旧输入，请重新分析当前数据')
        self.factors._store.require_artifact_registration(artifact_id)
        declaration=self.factors.export_strategy_factor_declaration(artifact_id)
        with self._connect() as c:
            c.execute('INSERT OR IGNORE INTO indicator_factor_approvals VALUES (?,?,?)',(artifact_id,str(artifact.get('content_hash') or ''),str(reason).strip()))
        return {'artifact_id':artifact_id,'registered':True,'declaration':declaration}

    def list_factor_artifacts(self):
        if self.factors is None: return {'items':[]}
        items=[]
        for artifact in self.factors.list_artifacts(limit=100)['items']:
            definition=self.factors._store.get_definition(artifact['factor_id'],artifact['factor_version'])
            if not definition or not definition.get('requires_user_registration'): continue
            governance=artifact.get('governance') or {}
            items.append({**artifact,'name':definition['name'],
                'registered':governance.get('registration_status')=='registered',
                'selection_reason':governance.get('decision_note','')})
        return {'items':items,'limit':100}

    def require_factor_registration(self, artifact):
        if self.factors is None: return
        definition=self.factors._store.get_definition(artifact.get('factor_id'),artifact.get('factor_version'))
        if not definition or not definition.get('requires_user_registration'): return
        self.factors._store.require_artifact_registration(artifact['artifact_id'])

    def strategy_example(self, config_id):
        config=self.get_config(config_id)
        field=config['definition']['outputs'][0]
        code=(f'DATASET_REQUIREMENTS = ["a_share_daily", "indicator_values"]\n'
              f'INDICATOR_REQUIREMENTS = [{config_id!r}]\n\n'
              'def generate_target_weights(bars, parameters):\n'
              '    result = []\n'
              '    for bar in bars:\n'
              f'        indicator = bar["datasets"]["indicator_values"]["items"][{config_id!r}]\n'
              f'        value = indicator["values"][{field!r}]\n'
              '        weight = 0.0\n'
              '        if value is not None:\n'
              '            weight = 1.0 if bar["close"] > value else 0.0\n'
              '        result.append(weight)\n'
              '    return result\n')
        return {'source_code':code,'adjustment':config['adjustment'],'minimum_history':config['definition']['minimum_history'],
                'note':'仅为调用示例；非价格指标请自行定义有意义的信号阈值。'}


class _ClosingConnection:
    def __init__(self, connection): self.connection=connection
    def __enter__(self): return self.connection
    def __exit__(self, kind, value, trace):
        try:
            self.connection.rollback() if kind else self.connection.commit()
        finally: self.connection.close()


def declared_indicators(source):
    result=None
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='INDICATOR_REQUIREMENTS' for t in node.targets):
            if result is not None: raise ValueError('指标声明重复')
            try: result=ast.literal_eval(node.value)
            except (ValueError,SyntaxError): raise ValueError('指标声明必须是固定配置 ID 列表')
    if result is None: return []
    if not isinstance(result,(tuple,list)) or not 1<=len(result)<=20 or any(not isinstance(x,str) or not re.fullmatch(r'ic_[a-f0-9]{24}',x) for x in result):
        raise ValueError('指标声明须包含 1–20 个已注册配置 ID')
    if len(set(result))!=len(result): raise ValueError('指标声明重复')
    return list(result)
