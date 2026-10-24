/* R2：正式数据浏览与数据集页面共用注册配置，所有值由服务端计算。 */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let definitions = [], configs = [];
  async function api(path, body, method = 'POST') {
    const response = await fetch('/api/indicators' + path, body === undefined ? {} : {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || data.detail || JSON.stringify(data));
    return data.result || data;
  }
  const el = id => document.getElementById(id);
  const parameterNames={period:'周期',fast:'快线周期',slow:'慢线周期',signal:'信号周期',deviations:'标准差倍数'};
  function report(message) { el('r2-status').textContent = message; el('r2-browser-status').textContent = message; }
  function bind(id, action, event = 'click') { let busy=false; el(id).addEventListener(event, async e => { e.preventDefault(); if(busy) return; busy=true; const button=e.currentTarget; button.disabled=true; try { await action(e); } catch(error) { report(error.message); } finally { button.disabled=false; busy=false; } }); }
  async function artifacts() {
    const result=await api('/factor-artifacts');
    el('r2-artifact').innerHTML='<option value="">请选择已分析的指标衍生因子制品</option>'+result.items.map(a=>`<option value="${esc(a.artifact_id)}">${esc(a.name)} · ${esc(a.start_date)}～${esc(a.end_date)} · ${a.registered?'已选用':'未选用'} · ${esc(a.artifact_id)}</option>`).join('');
  }
  function describe() {
    const d=definitions.find(x => x.indicator_id===el('r2-definition').value);
    if (!d) return;
    el('r2-parameters').innerHTML=Object.entries(d.parameters).map(([key,value])=>`<label>${esc(parameterNames[key] || key)}<input data-r2-parameter="${esc(key)}" type="number" min="${key==='deviations'?'0.01':'1'}" max="${key==='deviations'?'10':'252'}" step="${key==='deviations'?'any':'1'}" value="${esc(value)}" required></label>`).join('');
    el('r2-definition-info').textContent=`来源：${d.source_reference}；${d.source_note || ''}；公式：${d.formula}；输出：${d.outputs.join(', ')}；单位：${d.unit}；${d.missing_policy}`;
  }
  function outputs() {
    const c=configs.find(x => x.config_id===el('r2-config').value);
    el('r2-output').innerHTML=(c?.definition.outputs || []).map(x=>`<option>${esc(x)}</option>`).join('');
  }
  async function refresh() {
    [definitions,configs]=await Promise.all([api(''),api('/registrations')]).then(results=>results.map(x=>x.items));
    const selected=el('r2-definition').value;
    el('r2-definition').innerHTML=definitions.map(d=>`<option value="${esc(d.indicator_id)}">${esc(d.name)}</option>`).join('');
    if (definitions.some(d=>d.indicator_id===selected)) el('r2-definition').value=selected;
    describe();
    for (const id of ['r2-config','r2-browser-config']) {
      const previous=el(id).value;
      el(id).innerHTML='<option value="">请选择已注册配置</option>'+configs.map(c=>`<option value="${esc(c.config_id)}">${esc(c.name)} · ${esc(JSON.stringify(c.definition.parameters))} · ${esc(c.adjustment)}${c.enabled?'':' · 已停用'}</option>`).join('');
      if (configs.some(c=>c.config_id===previous)) el(id).value=previous;
    }
    outputs();
    el('r2-config-table').innerHTML=`<table data-vtable-mode="governance"><thead><tr><th>配置 ID</th><th>指标</th><th>参数</th><th>复权</th><th>最少历史</th><th>状态</th></tr></thead><tbody>${configs.map(c=>`<tr><td>${esc(c.config_id)}</td><td>${esc(c.name)}</td><td>${esc(JSON.stringify(c.definition.parameters))}</td><td>${esc(c.adjustment)}</td><td>${esc(c.definition.minimum_history)}</td><td>${c.enabled?'已注册；查询时检查输入':'已停用'}</td></tr>`).join('')}</tbody></table>`;
    if(!configs.length) el('r2-config-table').innerHTML='<p>尚未注册指标配置。选择指标、设置参数和复权后，即可查值并供策略使用。</p>';
    window.AppVTable?.enhanceAll(document);
    await artifacts();
  }
  function init() {
    const datasets=el('page-strategy-datasets'), browser=el('dc-view-assets');
    if (!datasets || !browser) return;
    const manager=document.createElement('section'); manager.className='panel panel-wide'; manager.id='r2-indicator-library';
    manager.innerHTML=`<h2>指标库与数据集注册</h2><p>独立实现的日线指标；固定参数、复权与算法口径。注册后按需计算，行情更新后自动重算；无需手动发布。</p>
      <p id="r2-status" role="status" aria-live="polite"></p><button id="r2-refresh" type="button">刷新指标库</button>
      <form id="r2-register"><label>指标<select id="r2-definition"></select></label><p id="r2-definition-info"></p><div id="r2-parameters"></div><label>复权<select id="r2-adjustment"><option value="raw">不复权</option><option value="qfq">前复权</option><option value="hfq">后复权</option></select></label><button type="submit">注册至数据集</button></form>
      <details><summary>创建自定义指标（受限表达式）</summary><form id="r2-create"><label>名称<input name="name" required></label><label>来源说明<input name="source_reference" required></label><label>表达式<input name="expression" placeholder="close / mean(close, 20) - 1" required></label><label>数值样例 JSON<textarea name="test_cases" required placeholder='[{"bars":[{"trade_date":"2026-01-01","close":10}],"expected":{"2026-01-01":10}}]'></textarea></label><p>只允许行情字段及 lag/mean/std/min/max/abs；样例必须包含明确的预期值。</p><button type="submit">校验并创建</button></form></details>
      <div id="r2-config-table"></div><div class="r2-actions"><label>已注册配置<select id="r2-config"></select></label><button id="r2-enabled" type="button">切换启用／停用</button><button id="r2-example" type="button">导入策略调用示例</button></div>
      <details id="r2-factor-flow"><summary>可选：指标转因子、分析及成果选用</summary><div class="r2-actions"><label>因子输出<select id="r2-output"></select></label><label>转换<select id="r2-transform"><option value="identity">原值</option><option value="negate">取负</option><option value="price_ratio">价格偏离（收盘价／指标－1）</option></select></label><button id="r2-factor" type="button">生成对应因子</button></div><p>生成后到因子面板分析；不自动认定有效，不自动供策略选用。</p>
      <button id="r2-artifact-refresh" type="button">刷新分析成果</button><form id="r2-approve"><label>分析完成的精确制品<select id="r2-artifact" required></select></label><label>选用依据<input id="r2-reason" required></label><button type="submit">将研究成果注册至策略数据集</button></form><button id="r2-factor-example" type="button" disabled>导入已选用因子的策略示例</button></details><pre id="r2-result"></pre>`;
    datasets.prepend(manager);
    const view=document.createElement('section'); view.className='panel panel-wide r2-indicator-browser';
    view.innerHTML=`<h2>指标值浏览（衍生数据）</h2><p>指标不是外部原始行情；这里查阅其计算结果、参数、复权与输入批次。配置请在数据集页注册。</p><p id="r2-browser-status" role="status" aria-live="polite"></p><form id="r2-query"><label>指标配置<select id="r2-browser-config" required></select></label><label>证券代码<input id="r2-symbol" value="000001" required pattern="[0-9]{6}"></label><label>开始日期<input id="r2-start" type="date"></label><label>结束日期<input id="r2-end" type="date"></label><button type="submit">查询指标值</button></form><div id="r2-values"></div>`;
    browser.prepend(view);
    bind('r2-refresh', refresh); bind('r2-definition', describe, 'change'); bind('r2-config', outputs, 'change');
    bind('r2-artifact-refresh',artifacts);
    bind('r2-register', async()=>{ const parameters=Object.fromEntries([...el('r2-parameters').querySelectorAll('input')].map(input=>[input.dataset.r2Parameter,Number(input.value)])); const c=await api('/registrations',{indicator_id:el('r2-definition').value,parameters,adjustment:el('r2-adjustment').value}); await refresh(); el('r2-config').value=c.config_id; el('r2-browser-config').value=c.config_id; outputs(); report('已注册：'+c.config_id); }, 'submit');
    bind('r2-create', async e=>{const body=Object.fromEntries(new FormData(e.currentTarget)); body.test_cases=JSON.parse(body.test_cases); await api('',body); await refresh(); report('自定义指标样例校验通过，已加入指标库。');}, 'submit');
    bind('r2-enabled', async()=>{const c=configs.find(x=>x.config_id===el('r2-config').value); if(!c) throw Error('请选择配置'); await api('/registrations/'+c.config_id,{enabled:!c.enabled},'PUT'); await refresh(); report('配置状态已更新；停用不删除历史研究成果。');});
    bind('r2-example', async()=>{const result=await api('/registrations/'+el('r2-config').value+'/strategy-example'); el('r2-result').textContent=result.source_code; if(typeof startNewStrategy==='function') { activatePage('backtest'); if(typeof activateStage76Workspace==='function') activateStage76Workspace('strategy'); startNewStrategy({name:'指标调用示例',source_code:result.source_code,description:result.note}); } report('已导入调用示例；复权须为 '+result.adjustment+'，最低历史 '+result.minimum_history+' 根。');});
    bind('r2-factor', async()=>{const config=configs.find(c=>c.config_id===el('r2-config').value); if(!config) throw Error('请选择配置'); const result=await api('/registrations/'+config.config_id+'/factor',{output:el('r2-output').value,transform:el('r2-transform').value}); el('r2-result').textContent='已创建因子：'+(result.definition.name || config.name)+'（'+result.definition.factor_id+'）'; if(typeof window.loadFactors==='function') { await window.loadFactors({factor_id:result.definition.factor_id}); const form=el('factor-research-form'); if(form) { form.elements.factor_id.value=result.definition.factor_id; form.elements.factor_id.dispatchEvent(new Event('change')); form.elements.factor_adjustment.value=config.adjustment; } activatePage('factor'); window.activateFactorView?.('detail'); } report('因子已创建，配置已填入分析面板；检查范围后显式启动分析。');});
    let selectedDeclaration=null;
    bind('r2-approve', async()=>{const result=await api('/factor-artifacts/'+encodeURIComponent(el('r2-artifact').value.trim())+'/register',{reason:el('r2-reason').value}); selectedDeclaration=result.declaration; el('r2-factor-example').disabled=!selectedDeclaration; el('r2-result').textContent='已选用研究制品：'+result.artifact_id+'\n选用依据：'+el('r2-reason').value; await artifacts(); report('研究制品已明确选用，可导入绑定该精确制品的策略示例。');},'submit');
    bind('r2-factor-example',async()=>{if(!selectedDeclaration) throw Error('请先明确选用研究成果'); activatePage('backtest'); if(typeof activateStage76Workspace==='function') activateStage76Workspace('strategy'); startNewStrategy({name:'指标衍生因子示例',source_code:selectedDeclaration.source_code,parameters:selectedDeclaration.parameters,description:'用户已选用的精确因子制品'});});
    bind('r2-query', async()=>{const result=await api('/registrations/'+el('r2-browser-config').value+'/values',{symbol:el('r2-symbol').value,start_date:el('r2-start').value,end_date:el('r2-end').value,limit:2000}); const fields=result.config.definition.outputs; el('r2-values').innerHTML=`<p>输入批次：${esc(result.data_version_id)}；复权：${esc(result.config.adjustment)}；${result.cache_hit?'缓存已核对':'已重算'}；显示 ${result.row_count}/${result.total} 行；${esc(result.reason)}</p><table data-vtable-mode="governance"><thead><tr><th>日期</th>${fields.map(f=>`<th>${esc(f)}</th>`).join('')}<th>状态</th><th>可用时间</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.trade_date)}</td>${fields.map(f=>`<td>${esc(r.values[f] ?? '—')}</td>`).join('')}<td>${esc(r.status)}</td><td>${esc(r.available_at)}</td></tr>`).join('')}</tbody></table>`; window.AppVTable?.enhanceAll(document); report('查询完成；缺值不填零，收盘后数据用于下一交易时点。');},'submit');
    refresh().catch(e=>report(e.message));
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
