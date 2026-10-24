import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const definition = {
  factor_id: 'fixture_momentum', name: '夹具动量因子', category: '动量', factor_version: 'v2',
  status: 'frozen', definition_type: 'expression', expression: 'close / mean(close, 20) - 1',
  formula: 'close / mean(close, 20) - 1', description: '浏览器交互夹具', input_fields: ['close'],
  minimum_history: 20, direction: 'positive', metadata_hash: 'fixture-v2-hash', registered_at: '2026-10-15T08:00:00Z',
};
const versions = [
  { ...definition, factor_version: 'v1', metadata_hash: 'fixture-v1-hash', registered_at: '2026-10-14T08:00:00Z' },
  definition,
];
let reportRequests = 0;

const page = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/quant-ui-candidate.css">
<link rel="stylesheet" href="/vtable-adapter.css"><link rel="stylesheet" href="/factor_research.css">
<style>body{padding:20px}.factor-workspace{width:1800px}.page-section{display:block}.factor-view[hidden]{display:none!important}</style>
</head><body class="quant-ui-standard"><div id="global-feedback"></div><h2 id="page-title">因子分析</h2><nav><button data-factor-view-target="dashboard">因子库</button><button data-factor-view-target="development">因子开发</button><button data-factor-view-target="detail">因子研究</button><button data-factor-view-target="tasks">研究任务</button><button data-factor-view-target="report">研究报告</button></nav><section id="page-factor" class="page-section is-active"><div class="factor-workspace">
<section class="factor-view" data-factor-view="dashboard"><form id="factor-dashboard-form"><select name="factor_id"></select><select name="pool_type"><option value="">全部</option></select><select name="context_id"></select></form><button id="factor-dashboard-refresh"></button><div id="factor-dashboard-summary"></div>
<div class="table-wrap"><table data-vtable-mode="factor"><thead><tr><th data-vtable-width="180">因子</th><th>分类</th><th>版本</th><th>研究状态</th><th>Rank IC</th><th>方向 Rank IC</th><th>ICIR</th><th>覆盖率</th><th>最大回撤</th><th>成员换手率</th><th data-vtable-cell-type="button" data-vtable-button-kind="secondary">详情</th><th data-vtable-cell-type="button">研究</th><th data-vtable-cell-type="button" data-vtable-button-kind="secondary">报告</th></tr></thead><tbody id="factor-dashboard-body"></tbody></table></div>
<dialog id="factor-profile-dialog" class="factor-profile-dialog"><h3 id="factor-profile-title"></h3><button id="factor-profile-close">关闭</button><nav class="factor-profile-tabs"><button class="is-active" data-factor-profile-tab="overview">基本信息</button><button data-factor-profile-tab="evidence">研究证据</button><button data-factor-profile-tab="versions">版本记录</button></nav>
<section data-factor-profile-panel="overview"><div id="factor-profile-content"></div></section>
<section data-factor-profile-panel="evidence" hidden><button id="factor-profile-evidence-refresh"></button><div id="factor-profile-evidence-summary"></div><div class="table-wrap"><table data-vtable-mode="factor"><thead><tr><th>证据来源</th><th>状态</th><th>留出期</th><th>完整退出</th><th>Rank IC</th><th>20bp 超额</th><th>40bp 超额</th><th>未知退出</th><th>显著性</th></tr></thead><tbody id="r3-study-body"></tbody></table></div><div id="factor-profile-report-action"></div></section>
<section data-factor-profile-panel="versions" hidden><div class="table-wrap"><table data-vtable-mode="factor"><thead><tr><th>版本</th><th>状态</th><th>类型</th><th>公式</th><th>登记时间</th><th>定义哈希</th></tr></thead><tbody id="factor-profile-version-body"></tbody></table></div></section>
<button id="factor-profile-create-version"></button><button id="factor-profile-start-research"></button></dialog></section>
<section class="factor-view" data-factor-view="development" hidden><button id="factor-definition-new"></button><form id="factor-definition-form"><input name="factor_id"><input name="name"><input name="category"><select name="direction"><option value="positive">正向</option><option value="negative">负向</option></select><textarea name="expression"></textarea><input name="description"><button id="factor-definition-validate" type="button"></button></form><pre id="factor-definition-output" hidden></pre></section>
<section class="factor-view" data-factor-view="detail" hidden><div id="factor-definition-detail"></div><form id="factor-research-form"><select name="factor_id"></select></form></section>
<section class="factor-view" data-factor-view="tasks" hidden><select id="factor-task-select"></select><div id="factor-task-progress"></div><pre id="factor-task-output"></pre><table><tbody id="factor-task-body"></tbody></table></section>
<section class="factor-view" data-factor-view="report" hidden><button id="factor-report-back">返回研究任务</button><div id="factor-report-context"></div><div id="factor-oos-reveal-toolbar"></div><div id="factor-report-credibility"></div><div id="factor-report-summary"></div><div id="factor-acceptance-summary"></div><table><tbody id="factor-acceptance-body"></tbody></table><table><tbody id="factor-sample-body"></tbody></table><table><tbody id="factor-distribution-body"></tbody></table><table><tbody id="factor-group-body"></tbody></table><div id="factor-ic-chart"></div><div id="factor-nav-chart"></div><table><tbody id="factor-decay-body"></tbody></table><table><tbody id="factor-industry-body"></tbody></table><table><tbody id="factor-annual-body"></tbody></table><table><tbody id="factor-cost-stress-body"></tbody></table><table><tbody id="factor-stock-body"></tbody></table><span id="factor-report-state"></span><pre id="factor-report-output"></pre></section>
</div></section>
<script>
function buildQuery(values){return new URLSearchParams(Object.entries(values).filter(([,value])=>value!==''&&value!=null)).toString()}
async function requestJson(url,options){const response=await fetch(url,{headers:{'Content-Type':'application/json'},...options});if(!response.ok)throw new Error(await response.text());return response.json()}
function renderSummaryGrid(target,items){if(target)target.innerHTML=items.map(item=>'<span>'+item.label+':'+item.value+'</span>').join('')}
function renderSeriesChart(target,rows){if(target)target.textContent='series:'+rows.length}
function setFeedback(message,state){const node=document.querySelector('#global-feedback');node.textContent=message;node.dataset.state=state}
</script><script src="/vendor/vtable/vtable.min.js"></script><script src="/vtable-adapter.js"></script><script src="/factor_research.js"></script><script>window.loadFactors().catch(error=>setFeedback(error.message,'error'))</script>
</body></html>`;

const server = createServer((request, response) => {
  const asset = request.url.split('?')[0].slice(1);
  if (request.url === '/') {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    return response.end(page);
  }
  if (['styles.css', 'quant-ui-candidate.css', 'vtable-adapter.css', 'factor_research.css',
    'vtable-adapter.js', 'factor_research.js', 'vendor/vtable/vtable.min.js'].includes(asset)) {
    response.setHeader('Content-Type', asset.endsWith('.js') ? 'application/javascript' : 'text/css');
    return response.end(readFileSync(join(root, 'web', asset)));
  }
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (request.url === '/api/factor-research/definitions') {
    return response.end(JSON.stringify({ items: [definition], capabilities: { index_pools: { status: 'ready' }, industry_neutralization: { status: 'ready' } } }));
  }
  if (request.url === '/api/factor-research/definitions/fixture_momentum') {
    return response.end(JSON.stringify({ definition, versions }));
  }
  if (request.url.startsWith('/api/factor-research/dashboard')) {
    return response.end(JSON.stringify({ filters: { context_id: 'fixture-context', contexts: [{ context_id: 'fixture-context', label: '夹具口径' }] }, items: [{ ...definition, latest_status: 'research_ready', latest_report_id: 'report-fixture', rank_ic_mean: 0.041, direction_aligned_rank_ic_mean: 0.041, icir: 0.71, factor_coverage: 0.98, max_drawdown: -0.06, turnover: 0.22 }] }));
  }
  if (request.url.startsWith('/api/factor-research/tasks')) return response.end(JSON.stringify({ items: [{ task_id: 'task-fixture', status: 'completed', report_id: 'report-fixture', data_version_id: 'data-fixture', config: { factor_id: 'fixture_momentum', pool_type: 'all_a' }, progress: { phase: 'completed', processed_symbols: 10, total_symbols: 10 } }] }));
  if (request.url === '/api/factor-research/r3-studies') {
    return response.end(JSON.stringify({ status: 'ready', items: [{ factor_id: 'fixture_momentum', name: '夹具动量因子', status: '研究完成·未验收', accepted: false, data_version_id: 'r3-fixture', holdout: { periods: 30, known_periods: 30, rank_ic: 0.03, mean_net_excess: 0.012, mean_stress_excess: 0.006, unknown_exits: 0, holm_p: 0.08 } }] }));
  }
  if (request.url === '/api/factor-research/reports/report-fixture') {
    reportRequests += 1;
    return response.end(JSON.stringify({ status: 'ready', payload: { definition, config: { forward_horizons: [5], research_mode: 'governed', pool_type: 'all_a' }, analysis: { ic: { '5': { rank_ic_mean: 0.041, direction_aligned_rank_ic_mean: 0.041, icir: 0.71, series: [] } } }, acceptance: { decision: 'research_ready', strategy_eligible: false, checks: [] } } }));
  }
  response.statusCode = 404;
  response.end(JSON.stringify({ detail: request.url }));
});

await new Promise(resolveListen => server.listen(0, '127.0.0.1', resolveListen));
const profile = mkdtempSync(join(tmpdir(), 'scq-factor-library-'));
const browser = spawn(process.env.SCQ_TEST_BROWSER || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ['--headless=new', '--disable-gpu', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  { windowsHide: true, stdio: 'ignore' });
const wait = milliseconds => new Promise(resolveWait => setTimeout(resolveWait, milliseconds));
let socket;
try {
  let port;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try { port = readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]; break; } catch {}
    await wait(100);
  }
  assert.ok(port, 'isolated headless browser did not start');
  const targets = await fetch(`http://127.0.0.1:${port}/json`).then(response => response.json());
  socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolveSocket, rejectSocket) => { socket.onopen = resolveSocket; socket.onerror = rejectSocket; });
  const pending = new Map(); let sequence = 0;
  socket.onmessage = event => { const data = JSON.parse(event.data), pair = pending.get(data.id); if (pair) { pending.delete(data.id); data.error ? pair.reject(data.error) : pair.resolve(data.result); } };
  const command = (method, params = {}) => new Promise((resolveCommand, rejectCommand) => { const id = ++sequence; pending.set(id, { resolve: resolveCommand, reject: rejectCommand }); socket.send(JSON.stringify({ id, method, params })); });
  const evaluate = async expression => { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails)); return result.result.value; };
  const clickActionColumn = async ratio => {
    const point = await evaluate(`(()=>{const r=document.querySelector('[data-factor-view="dashboard"] .app-vtable-host').getBoundingClientRect();return{x:r.left+r.width*${ratio},y:r.top+64}})()`);
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', clickCount: 1 });
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'left', clickCount: 1 });
  };

  await command('Page.enable');
  await command('Emulation.setDeviceMetricsOverride', { width: 1900, height: 1000, deviceScaleFactor: 1, mobile: false });
  await command('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
  await wait(900);
  const dashboardState = await evaluate(`(()=>({
    hosts:document.querySelectorAll('[data-factor-view="dashboard"] .app-vtable-host').length,
    rows:document.querySelectorAll('#factor-dashboard-body tr').length,
    source:document.querySelector('[data-factor-view="dashboard"] table')?.className||'',
    feedback:document.querySelector('#global-feedback')?.textContent||'',
    vtable:Boolean(window.VTable?.ListTable),adapter:Boolean(window.AppVTable),
    href:location.href,title:document.title,body:document.body?.textContent?.slice(0,120)||''
  }))()`);
  assert.equal(dashboardState.hosts, 1, JSON.stringify(dashboardState));

  await clickActionColumn(0.816);
  await wait(300);
  assert.equal(await evaluate('document.querySelector("#factor-profile-dialog").open'), true, '详情应打开因子详情');
  assert.ok(await evaluate('document.querySelector("#factor-profile-content").textContent.includes("夹具动量因子")'));
  await evaluate('document.querySelector(\'[data-factor-profile-tab="evidence"]\').click()');
  await wait(200);
  assert.ok(await evaluate('document.querySelector("#r3-study-body").textContent.includes("R3 封存研究")'));
  await evaluate('document.querySelector(\'[data-factor-profile-tab="versions"]\').click()');
  await wait(200);
  assert.equal(await evaluate('document.querySelectorAll("#factor-profile-version-body tr").length'), 2);
  await evaluate('document.querySelector("#factor-profile-create-version").click()');
  assert.equal(await evaluate('document.querySelector(\'[data-factor-view="development"]\').hidden'), false);
  assert.equal(await evaluate('document.querySelector(\'#factor-definition-form [name="factor_id"]\').readOnly'), true);

  await evaluate('window.activateFactorView("dashboard")'); await wait(250);
  await clickActionColumn(0.889); await wait(250);
  assert.equal(await evaluate('document.querySelector(\'[data-factor-view="detail"]\').hidden'), false, '研究应进入因子研究');
  assert.equal(await evaluate('document.querySelector(\'#factor-research-form [name="factor_id"]\').value'), 'fixture_momentum');

  await evaluate('window.activateFactorView("dashboard")'); await wait(250);
  await clickActionColumn(0.963); await wait(350);
  assert.equal(reportRequests, 1, '报告应请求最新研究报告');
  const reportState = await evaluate(`({hidden:document.querySelector('[data-factor-view="report"]').hidden,feedback:document.querySelector('#global-feedback').textContent})`);
  assert.equal(reportState.hidden, false, '报告应进入报告页：' + JSON.stringify(reportState));
  assert.equal(await evaluate('document.querySelector("#factor-report-state").textContent'), 'report-fixture');
  assert.equal(await evaluate('document.querySelector(\'[data-factor-view-target="report"]\').classList.contains("is-active")'), true, '报告菜单应处于选中状态');
  assert.equal(await evaluate('document.querySelector("#page-title").textContent'), '因子分析 / 研究报告');
  assert.equal(await evaluate('document.querySelector("#factor-report-back").textContent'), '返回因子库');
  await evaluate('document.querySelector("#factor-report-back").click()');
  assert.equal(await evaluate('document.querySelector(\'[data-factor-view="dashboard"]\').hidden'), false);

  await evaluate('window.activateFactorView("tasks")');
  await evaluate('document.querySelector("#factor-task-body [data-factor-open-report]").click()');
  await wait(350);
  assert.equal(reportRequests, 2, '研究任务打开报告应读取报告');
  assert.equal(await evaluate('document.querySelector("#factor-report-back").textContent'), '返回研究任务');
  assert.ok(await evaluate('document.querySelector("#factor-report-context").textContent.includes("来源任务：task-fixture")'));
  await evaluate('document.querySelector("#factor-report-back").click()');
  assert.equal(await evaluate('document.querySelector(\'[data-factor-view="tasks"]\').hidden'), false);
  console.log('factor library browser: detail, research, report navigation, evidence tabs and version workflow passed');
} finally {
  socket?.close(); browser.kill(); server.close();
  await wait(700);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }); } catch {}
}
