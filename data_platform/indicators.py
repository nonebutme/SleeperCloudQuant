"""统一日线指标内核；独立实现，显式算法口径，前缀计算不读未来。"""
from collections import deque
from datetime import date
from hashlib import sha256
import json
import math
import statistics

from factor_lab.expression_factor import calculate_expression_factor, validate_expression


ENGINE_VERSION = 'r2-v1'
SOURCE = 'https://ta-lib.org/functions/'


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def definitions():
    specs = [
        ('sma', '简单移动平均 SMA', {'period':20}, ['value'], '最近 N 个有效收盘价算术平均', 'price'),
        ('ema', '指数移动平均 EMA', {'period':20}, ['value'], '首 N 项 SMA 作种子，alpha=2/(N+1)，从历史起点递推', 'price'),
        ('wma', '加权移动平均 WMA', {'period':20}, ['value'], '窗口由旧至新权重 1..N', 'price'),
        ('rsi', '相对强弱 RSI', {'period':14}, ['value'], '涨跌幅 Wilder 平滑；首 N 个差分均值作种子；全平为 50、无跌为 100', '0..100'),
        ('macd', 'MACD', {'fast':12,'slow':26,'signal':9}, ['macd','signal','histogram'], 'SMA 种子 EMA；快线-慢线；信号为差值 EMA；柱为差值-信号（不乘 2）', 'price'),
        ('atr', '平均真实波幅 ATR', {'period':14}, ['value'], 'TR=max(H-L,abs(H-prevC),abs(L-prevC))；首日 TR=H-L；SMA 种子 Wilder 平滑', 'price'),
        ('bbands', '布林带', {'period':20,'deviations':2.0}, ['upper','middle','lower'], 'SMA ± 倍数×总体标准差（ddof=0）', 'price'),
        ('roc', '变化率 ROC', {'period':10}, ['value'], '(C/C[-N]-1)×100；分母为零时缺值', 'percent'),
    ]
    return [dict(indicator_id=i, name=n, definition_version=ENGINE_VERSION, definition_type='builtin',
                 parameters=p, outputs=o, formula=f, unit=u, frequency='daily',
                 input_fields=['high','low','close'] if i=='atr' else ['close'],
                 source_reference=SOURCE, source_note='公开技术指标目录；项目独立实现，具体种子与公式以本条为准',
                 missing_policy='缺失值不填零；连续缺失中断窗口并重置递推状态',
                 history_policy='canonical_series_origin', verification_status='sample_verified')
            for i,n,p,o,f,u in specs]


def configure(definition, parameters):
    result = dict(definition)
    supplied = dict(parameters or {})
    defaults = dict(result.get('parameters') or {})
    if set(supplied) - set(defaults):
        raise ValueError('存在不支持的指标参数')
    params = {**defaults, **supplied}
    for key, value in params.items():
        if key == 'deviations':
            if isinstance(value, bool) or not isinstance(value, (float,int)) or not math.isfinite(value) or not 0 < value <= 10:
                raise ValueError('标准差倍数须在 (0,10] 内')
        elif isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 252:
            raise ValueError('指标窗口须为 1–252 的整数')
    if result['indicator_id']=='macd' and params['fast'] >= params['slow']:
        raise ValueError('MACD 快线周期须小于慢线周期')
    result['parameters'] = params
    n = int(params.get('period',1))
    result['minimum_history'] = (params['slow']+params['signal']-1 if result['indicator_id']=='macd'
                                else n+1 if result['indicator_id'] in {'rsi','roc'} else n)
    if result.get('definition_type') == 'expression':
        result['minimum_history'] = validate_expression(result['expression'])['minimum_history']
    return result


def _finite(value):
    return float(value) if not isinstance(value,bool) and isinstance(value,(float,int)) and math.isfinite(value) else None


def _smooth(values, n, alpha):
    window, previous, result = deque(maxlen=n), None, []
    for value in values:
        if value is None:
            window.clear()
            previous = None
        elif previous is None:
            window.append(value)
            if len(window)==n:
                previous = sum(window)/n
        else:
            previous += alpha*(value-previous)
        result.append(previous)
    return result


def calculate(definition, bars):
    config = configure(definition, definition.get('parameters'))
    rows = sorted((dict(r) for r in bars), key=lambda r:str(r.get('date') or r.get('trade_date') or ''))
    dates = [date.fromisoformat(str(r.get('date') or r.get('trade_date') or '')[:10]).isoformat() for r in rows]
    if len(set(dates)) != len(dates):
        raise ValueError('指标输入同一证券日期重复')
    prices = [_finite(r.get('close')) for r in rows]
    key, p = config['indicator_id'], config['parameters']
    result = [{field:None for field in config['outputs']} for _ in rows]
    if config.get('definition_type')=='expression':
        values = calculate_expression_factor(config['expression'], rows)
        for day, output in zip(dates, result):
            output['value'] = values.get(day)
    elif key in {'sma','wma','bbands'}:
        n, window = p['period'], deque(maxlen=p['period'])
        for i,v in enumerate(prices):
            if v is None:
                window.clear()
                continue
            window.append(v)
            if len(window)<n:
                continue
            mean = sum(window)/n
            if key=='sma': result[i]['value']=mean
            elif key=='wma': result[i]['value']=sum((k+1)*x for k,x in enumerate(window))/(n*(n+1)/2)
            else:
                deviation=statistics.pstdev(window)*p['deviations']
                result[i]=dict(upper=mean+deviation,middle=mean,lower=mean-deviation)
    elif key=='ema':
        for output,value in zip(result,_smooth(prices,p['period'],2/(p['period']+1))): output['value']=value
    elif key=='macd':
        fast=_smooth(prices,p['fast'],2/(p['fast']+1))
        slow=_smooth(prices,p['slow'],2/(p['slow']+1))
        line=[a-b if a is not None and b is not None else None for a,b in zip(fast,slow)]
        signal=_smooth(line,p['signal'],2/(p['signal']+1))
        for output,a,b in zip(result,line,signal):
            if a is not None and b is not None: output.update(macd=a,signal=b,histogram=a-b)
    elif key=='rsi':
        delta=[None]+[b-a if a is not None and b is not None else None for a,b in zip(prices,prices[1:])]
        gains=_smooth([max(v,0) if v is not None else None for v in delta],p['period'],1/p['period'])
        losses=_smooth([max(-v,0) if v is not None else None for v in delta],p['period'],1/p['period'])
        for output,g,l in zip(result,gains,losses):
            if g is not None and l is not None: output['value']=50.0 if g==l==0 else 100.0 if l==0 else 100-100/(1+g/l)
    elif key=='atr':
        tr=[]
        for i,row in enumerate(rows):
            high,low=_finite(row.get('high')),_finite(row.get('low'))
            prior=prices[i-1] if i else None
            tr.append(None if high is None or low is None or prices[i] is None or high<low else
                      max(high-low,abs(high-prior),abs(low-prior)) if prior is not None else high-low)
        for output,v in zip(result,_smooth(tr,p['period'],1/p['period'])): output['value']=v
    elif key=='roc':
        n=p['period']
        for i,v in enumerate(prices):
            if i>=n and v is not None and prices[i-n] not in (None,0) and all(x is not None for x in prices[i-n:i+1]):
                result[i]['value']=(v/prices[i-n]-1)*100
    else:
        raise ValueError('未知指标实现')
    return [dict(trade_date=day, values={k:_finite(v) for k,v in output.items()},
                 status='ready' if all(_finite(v) is not None for v in output.values()) else 'unavailable',
                 available_at=day+'T18:00:00+08:00') for day,output in zip(dates,result)]


def create_expression_definition(name, expression, source_reference, test_cases):
    validation=validate_expression(expression)
    if not str(name).strip() or len(str(name))>80 or not str(source_reference).strip():
        raise ValueError('请填写指标名称和公式来源/说明')
    definition=dict(indicator_id='custom_'+digest([name,expression,source_reference])[:16],name=str(name),
        definition_type='expression',definition_version=ENGINE_VERSION,expression=expression,formula=expression,
        parameters={},outputs=['value'],unit='formula_defined',frequency='daily',input_fields=validation['input_fields'],
        source_reference=str(source_reference),source_note='用户提供公式，受控表达式及给定数值样例校验',
        missing_policy='缺失值不填零',history_policy='canonical_series_origin',verification_status='sample_verified')
    if not isinstance(test_cases,list) or not 1<=len(test_cases)<=10:
        raise ValueError('自定义指标须提供 1–10 个包含 bars 与 expected 的数值样例')
    for case in test_cases:
        if not isinstance(case,dict) or not isinstance(case.get('bars'),list) or not 1<=len(case['bars'])<=1000:
            raise ValueError('每个数值样例须包含 1–1000 条行情')
        expected=case.get('expected')
        output=calculate(definition,case['bars'])
        if not isinstance(expected,dict) or not expected:
            raise ValueError('样例 expected 须为 日期:期望值 映射')
        actual={r['trade_date']:r['values']['value'] for r in output}
        for day,value in expected.items():
            if _finite(value) is None or actual.get(day) is None or not math.isclose(actual[day],value,rel_tol=1e-9,abs_tol=1e-9):
                raise ValueError('自定义指标数值样例不匹配：'+str(day))
    definition['test_cases_hash']=digest(test_cases)
    return configure(definition,{})


def calculate_indicator_factor(definition, bars):
    values=calculate(definition['indicator_definition'],bars)
    closes={str(r.get('date') or r.get('trade_date'))[:10]:_finite(r.get('close')) for r in bars}
    result={}
    for row in values:
        v=row['values'].get(definition['indicator_output'])
        if v is None: continue
        conversion=definition['indicator_transform']
        if conversion=='negate': v=-v
        elif conversion=='price_ratio':
            c=closes.get(row['trade_date'])
            if v==0 or c is None: continue
            v=c/v-1
        if math.isfinite(v): result[row['trade_date']]=v
    return result
