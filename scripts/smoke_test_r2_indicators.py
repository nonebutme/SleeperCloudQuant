"""R2 数值、缓存、接口和策略消费验证；只使用临时数据库。"""
from _project_bootstrap import ensure_project_root_on_sys_path
ensure_project_root_on_sys_path()
import math
import sqlite3
import tempfile
from pathlib import Path
from datetime import date, timedelta
from data_platform.indicators import definitions, configure, calculate, calculate_indicator_factor, create_expression_definition
from app.services.indicator_service import IndicatorService, declared_indicators
from app.services.strategy_dataset_resolver import StrategyDatasetResolver
from app.api.indicators import build_indicator_routes
from app.main import SimpleApiApp
from smoke_test_stage87_factor_research_api import _seed_market_database, _dispatch, _wait_for_completion


def rejects(call):
    try: call()
    except (ValueError, RuntimeError): return
    raise AssertionError('应拒绝此输入')


def main():
    builtins={d['indicator_id']:d for d in definitions()}
    bars=[dict(trade_date=(date(2026,1,1)+timedelta(days=i)).isoformat(),close=float(i+1),high=float(i+2),low=float(i),open=float(i+1),volume=100,amount=1000) for i in range(60)]
    expected={'sma':59.,'ema':59.,'wma':(58+59*2+60*3)/6,'rsi':100.,'atr':2.,'roc':(60/57-1)*100}
    for key, value in expected.items():
        result=calculate(configure(builtins[key],{'period':3}),bars)
        assert math.isclose(result[-1]['values']['value'],value,abs_tol=1e-10), (key,result[-1])
    bb=calculate(configure(builtins['bbands'],{'period':3}),bars)[-1]['values']
    assert math.isclose(bb['upper'],59+2*math.sqrt(2/3)) and bb['middle']==59
    macd=calculate(configure(builtins['macd'],{'fast':2,'slow':3,'signal':2}),bars)[-1]['values']
    assert macd=={'macd':0.5,'signal':0.5,'histogram':0.0},macd
    flat=[{**b,'close':10.} for b in bars]
    assert calculate(configure(builtins['rsi'],{'period':3}),flat)[-1]['values']['value']==50
    mixed=[{**b,'close':c} for b,c in zip(bars,[1.,2.,1.,3.])]
    assert math.isclose(calculate(configure(builtins['rsi'],{'period':2}),mixed)[-1]['values']['value'],100*5/6)
    macd_mixed=[{**b,'close':c} for b,c in zip(bars,[1.,2.,3.,2.,5.])]
    assert math.isclose(calculate(configure(builtins['macd'],{'fast':2,'slow':3,'signal':2}),macd_mixed)[3]['values']['histogram'],-1/6)
    for d in builtins.values():
        full=calculate(d,bars)
        assert full[:40]==calculate(d,bars[:40]),d['indicator_id']
    broken=[*bars[:5],{**bars[5],'close':None},*bars[6:]]
    output=calculate(configure(builtins['ema'],{'period':3}),broken)
    assert all(output[i]['values']['value'] is None for i in [5,6,7]) and output[8]['values']['value']==8
    rejects(lambda:configure(builtins['ema'],{'period':True}))
    rejects(lambda:configure(builtins['macd'],{'fast':26}))
    rejects(lambda:calculate(builtins['sma'],[bars[0],bars[0]]))
    custom=create_expression_definition('偏离','close / mean(close, 3) - 1','人工公式样例',[{'bars':bars[:3],'expected':{bars[2]['trade_date']:0.5}}])
    assert calculate(custom,bars)[2]['values']['value']==0.5
    rejects(lambda:create_expression_definition('错误','close','测试',[{'bars':bars[:1],'expected':{bars[0]['trade_date']:2}}]))
    rejects(lambda:create_expression_definition('未来','lag(close, -1)','测试',[]))
    with tempfile.TemporaryDirectory(prefix='scq-r2-',ignore_cleanup_errors=True) as directory:
        market=Path(directory)/'market.sqlite3'
        _seed_market_database(market)
        with sqlite3.connect(market) as c:
            for field in ['open','high','low','volume']:
                c.execute(f'ALTER TABLE market_daily_prices ADD COLUMN {field} REAL')
            c.execute('UPDATE market_daily_prices SET open=close,high=close+1,low=close-1,volume=1000')
        service=IndicatorService(market)
        app=SimpleApiApp(title='R2 fixture',routes=build_indicator_routes(service))
        assert len(_dispatch(app,'GET','/api/indicators')['result']['items'])==8
        config=_dispatch(app,'POST','/api/indicators/registrations',payload={'indicator_id':'ema','parameters':{'period':3},'adjustment':'raw'})['result']
        cid=config['config_id']
        assert service.register(indicator_id='ema',parameters={'period':3},adjustment='raw')['config_id']==cid
        query=dict(symbol='000001',start_date='2026-03-02',end_date='2026-03-20')
        first=service.values(cid,**query)
        assert first['status']=='ready' and not first['cache_hit']
        assert service.values(cid,**query)['cache_hit']
        subset=service.values(cid,**{**query,'start_date':'2026-03-10'})
        assert subset['rows']==[r for r in first['rows'] if r['trade_date']>='2026-03-10']
        with sqlite3.connect(market) as c:
            c.execute("UPDATE market_daily_prices SET close=close+10 WHERE symbol='000001' AND adjustment='raw' AND trade_date='2026-03-02'")
        changed=service.values(cid,**query)
        assert not changed['cache_hit'] and changed['input_hash']!=first['input_hash']
        assert changed['rows'][0]['values']!=first['rows'][0]['values']
        rejects(lambda:service.values(cid,**query,expected_version='not-preserved'))
        source=service.strategy_example(cid)['source_code']
        assert declared_indicators(source)==[cid]
        resolver=StrategyDatasetResolver(None,indicator_service=service)
        with sqlite3.connect(market) as c:
            c.row_factory=sqlite3.Row
            inputs=[dict(r) for r in c.execute("SELECT *, trade_date AS date FROM market_daily_prices WHERE symbol='000001' AND adjustment='raw' AND trade_date BETWEEN '2026-03-02' AND '2026-03-20' ORDER BY trade_date")]
        result=resolver.resolve(source,inputs,{'adjustment':'raw'}, {'symbol':'000001','adjustment':'raw','data_version_id':first['data_version_id']})
        namespace={}; exec(source,namespace)
        weights=namespace['generate_target_weights'](result['bars'],{})
        assert len(weights)==len(inputs) and all(x in (0.,1.) for x in weights)
        from backtest_kernel.adapters.local_sqlite_runtime import LocalSQLiteBacktestRuntime
        class Repository:
            def fetch_price_history(self,*args,**kwargs): return inputs
        runtime=LocalSQLiteBacktestRuntime(Repository(),strategy_resolver=lambda *args:{
            'source_code':source,'source_sha256':'fixture-source','execution_contract':'target-weights-v1'},dataset_resolver=resolver.resolve)
        backtest=runtime.run(dict(run_id='r2-test',symbol='000001.XSHE',start_date='2026-03-02',end_date='2026-03-20',
            parameters={'adjustment':'raw'},extra_config={'strategy_id':'r2','strategy_version':'v1','data_version_id':first['data_version_id']}))
        assert any(e['dataset_id']=='indicator_values' for e in backtest['raw_result']['strategy_binding']['datasets'])
        rejects(lambda:resolver.resolve(source,inputs,{'adjustment':'qfq'}))
        service.set_enabled(cid,False)
        rejects(lambda:service.values(cid,**query))
        rejects(lambda:resolver.freeze_parameters(source,{}))
        service.set_enabled(cid,True)
        factor=dict(indicator_definition=config['definition'],indicator_output='value',indicator_transform='identity')
        assert calculate_indicator_factor(factor,bars)=={r['trade_date']:r['values']['value'] for r in calculate(config['definition'],bars) if r['values']['value'] is not None}
        from app.services.factor_analysis_service import FactorAnalysisService
        from factor_lab.storage import SqliteFactorResearchStore
        from data_platform import DataCenterStore, ClassificationHistoryStore
        index=DataCenterStore(market); index.ensure_schema()
        store=SqliteFactorResearchStore(Path(directory)/'research.sqlite3',index_store=index)
        service.factors=FactorAnalysisService(market_database_path=market,research_store=store,
            classification_store=ClassificationHistoryStore(Path(directory)/'classifications.sqlite3'))
        generated=service.make_factor(cid,output='value',transform='price_ratio')
        fid=generated['definition']['factor_id']
        task_config=dict(factor_id=fid,factor_version='v1',start_date='2026-02-02',end_date='2026-03-31',
            symbols=[],symbol_limit=0,pool_type='all_a',factor_adjustment='raw',outcome_adjustment='qfq',
            forward_horizons=[5],preprocessing={'winsor_mad':3.0,'standardize':True,'industry_neutral':False},
            group_count=5,cost_assumption={'one_side_rate':0.001},task_id='r2-indicator-factor')
        rejects(lambda:service.factors.preflight({**task_config,'factor_adjustment':'qfq'}))
        task=service.factors.create_task(task_config)
        service.factors.start_task(task['task_id'])
        completed=_wait_for_completion(service.factors,task['task_id'])
        artifact=service.factors.list_artifacts(factor_id=fid)['items'][0]
        rejects(lambda:service.require_factor_registration(artifact))
        registered=service.register_factor(artifact['artifact_id'],reason='隔离测试：已检查分析结果与使用口径')
        assert service.list_factor_artifacts()['items'][0]['registered']
        assert registered['registered'] and completed['status']=='completed'
        service.require_factor_registration(artifact)
        rejects(lambda:service.require_factor_registration({**artifact,'content_hash':'changed'}))
    print('R2 indicators: 8 algorithms, causal prefixes, custom validation, API, cache invalidation, real backtest, factor analysis and explicit artifact registration passed')


if __name__=='__main__': main()
