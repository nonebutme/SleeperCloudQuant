import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

// Isolated browser fixture: only local mock APIs are used and no project database is opened.
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const sources = [
  {
    source_id: 'source-a', display_name: '数据源 A', upstream_name: 'fixture-a',
    verification_status: 'verified', enabled: true, requests_per_minute: 20,
    concurrency: 2, retry_count: 1, notes: 'fixture source a', allowed_hosts: [],
    secret_env_names: [], credential_states: [],
    capabilities: [{ dataset_id: 'a_share_daily', endpoint_id: 'daily-a', enabled: true, verification_status: 'verified' }],
  },
  {
    source_id: 'source-b', display_name: '数据源 B', upstream_name: 'fixture-b',
    verification_status: 'verified', enabled: true, requests_per_minute: 30,
    concurrency: 1, retry_count: 2, notes: 'fixture source b', allowed_hosts: [],
    secret_env_names: [], credential_states: [],
    capabilities: [
      { dataset_id: 'index_daily', endpoint_id: 'daily-b', enabled: true, verification_status: 'verified' },
      { dataset_id: 'trade_calendar', endpoint_id: 'calendar-b', enabled: true, verification_status: 'verified' },
      { dataset_id: 'index_components', endpoint_id: 'components-b', enabled: false, verification_status: 'candidate' },
      { dataset_id: 'industry_board', endpoint_id: 'industry-b', enabled: true, verification_status: 'verified' },
    ],
  },
];
const datasets = [{
  dataset_id: 'a_share_daily', layer_id: 'L1', layer_name: '行情', display_name: 'A股日线行情',
  sync_enabled: true, availability_status: 'connected', producer_type: 'external',
}];
let routes = [{
  route_id: 'fixture-route', dataset: 'a_share_daily', source_id: 'source-a', provider: 'fixture',
  endpoint: 'daily-a', upstream: 'fixture-upstream', lifecycle_stage: 'P0', mapping_version: 'v1',
  priority: 10, enabled: true, fallback_policy: 'primary', requests_per_minute: 20,
  concurrency: 1, timeout_seconds: 10, retry_count: 1, backoff_seconds: 1.5,
  last_success_at: '2026-10-12T00:00:00Z', last_failure_at: null, last_latency_ms: 18,
  last_error: null, updated_at: '2026-10-12T00:00:00Z',
}, {
  route_id: 'fixture-route-fallback', dataset: 'a_share_daily', source_id: 'source-a', provider: 'fixture',
  endpoint: 'daily-a', upstream: 'fixture-upstream', lifecycle_stage: 'P1', mapping_version: 'v2',
  priority: 20, enabled: false, fallback_policy: 'on_failure', requests_per_minute: 10,
  concurrency: 1, timeout_seconds: 15, retry_count: 2, backoff_seconds: 2.5,
  last_success_at: null, last_failure_at: null, last_latency_ms: null,
  last_error: null, updated_at: '2026-10-12T00:00:00Z',
}];
let testCalls = 0;
const routePutBodies = [];
const routeTestBodies = [];

const page = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/quant-ui-candidate.css">
<link rel="stylesheet" href="/vtable-adapter.css"><link rel="stylesheet" href="/data_center.css">
<style>body{padding:20px}@media(min-width:1000px){.dc-source-workspace{grid-template-columns:752px 400px!important;width:1166px}.dc-route-workspace{grid-template-columns:280px 800px!important;width:1094px}}</style>
</head><body class="quant-ui-standard">
<div id="global-feedback" class="feedback"></div><button id="open-routes" data-dc-view="routes">打开数据源配置</button>
<div id="dc-view-routes" class="dc-view"><section class="panel">
  <div class="dc-subtabs"><button class="is-active" data-dc-route-tab="sources">数据源配置</button><button data-dc-route-tab="routes">源路由配置</button></div>
  <div id="dc-source-panel" data-dc-route-panel="sources"><div class="dc-source-workspace">
    <section class="dc-surface dc-source-catalog"><div class="dc-surface-title"><h4>受控数据源</h4></div><div id="dc-source-list"></div></section>
    <section class="dc-surface dc-source-history"><div class="dc-surface-title"><div><h4>最近探测历史</h4><p id="dc-source-probe-context"></p></div></div><div id="dc-source-probe-history"></div></section>
  </div></div>
  <div id="dc-route-panel" data-dc-route-panel="routes" hidden><div class="dc-route-workspace"><aside class="dc-surface dc-route-tree-panel"><div id="dc-route-dataset-tree" class="dc-dataset-tree"></div></aside><section class="dc-surface dc-route-editor-panel"><div class="dc-surface-title dc-route-table-heading"><div><h4>路由表与参数</h4><p id="dc-route-selection-context">请选择路由</p></div><div class="dc-header-actions"><button id="dc-route-check" type="button">检查配置</button><button id="dc-route-test" type="button" disabled>连接测试</button></div></div><div id="dc-route-list" class="dc-route-table"></div></section></div></div>
  <dialog id="dc-route-dialog" class="dc-task-dialog dc-route-dialog"><div class="dc-dialog-head"><h4 id="dc-route-dialog-title">路由详情</h4><button id="dc-route-dialog-close" type="button">关闭</button></div><form id="dc-route-form" class="dc-route-dialog-body" novalidate><div id="dc-route-detail"></div><p id="dc-route-form-error" class="dc-dialog-inline-error" role="alert" hidden></p><div class="dc-source-dialog-actions"><button id="dc-route-dialog-cancel" type="button">取消</button><button id="dc-route-save" type="submit">应用当前配置</button></div></form></dialog>
  <dialog id="dc-route-test-dialog" class="dc-task-dialog dc-route-test-dialog"><div class="dc-dialog-head"><h4 id="dc-route-test-dialog-title">查看连接测试结果</h4><button id="dc-route-test-dialog-close" type="button">关闭</button></div><div id="dc-route-test-detail" class="dc-route-test-body"></div></dialog>
  <dialog id="dc-source-dialog" class="dc-task-dialog dc-source-dialog"><div class="dc-dialog-head"><h4 id="dc-source-dialog-title"></h4><button id="dc-source-dialog-close" type="button">关闭</button></div><form id="dc-source-form"><div id="dc-source-detail"></div><button id="dc-source-dialog-cancel" type="button">取消</button><button id="dc-source-save" type="button">保存</button></form></dialog>
  <dialog id="dc-source-capability-dialog" class="dc-task-dialog dc-source-capability-dialog"><div class="dc-dialog-head"><h4 id="dc-source-capability-title"></h4><button id="dc-source-capability-close" type="button">关闭</button></div><div id="dc-source-capability-detail" class="dc-source-capability-body"></div></dialog>
  <dialog id="dc-source-probe-dialog" class="dc-task-dialog dc-source-probe-dialog"><div class="dc-dialog-head"><h4 id="dc-source-probe-dialog-title"></h4><button id="dc-source-probe-dialog-close" type="button">关闭</button></div><div id="dc-source-probe-detail" class="dc-source-probe-body"></div></dialog>
</section></div>
<script src="/vendor/vtable/vtable.min.js"></script><script src="/vtable-adapter.js"></script><script src="/data_center_stage_c.js"></script>
</body></html>`;

const server = createServer((request, response) => {
  const asset = request.url.split('?')[0].slice(1);
  if (['styles.css', 'quant-ui-candidate.css', 'vtable-adapter.css', 'data_center.css',
    'vtable-adapter.js', 'data_center_stage_c.js', 'vendor/vtable/vtable.min.js'].includes(asset)) {
    response.setHeader('Content-Type', asset.endsWith('.js') ? 'application/javascript' : 'text/css');
    return response.end(readFileSync(join(root, 'web', asset)));
  }
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (request.url === '/api/data-center/sources') return response.end(JSON.stringify({ items: sources }));
  if (request.url === '/api/data-center/datasets') return response.end(JSON.stringify({ items: datasets }));
  if (request.method === 'GET' && request.url === '/api/data-center/routes') return response.end(JSON.stringify({ items: routes }));
  if (request.url.startsWith('/api/data-center/source-probes')) {
    const sourceId = new URL(request.url, 'http://local').searchParams.get('source_id');
    return response.end(JSON.stringify({ items: [{
      probe_id: `${sourceId}-probe`,
      source_id: sourceId, dataset_id: sourceId === 'source-b' ? 'index_daily' : 'a_share_daily',
      endpoint_id: `${sourceId}-endpoint`, mode: 'live_read',
      status: sourceId === 'source-a' ? 'failed' : 'passed',
      error_code: sourceId === 'source-a' ? 'UPSTREAM_TIMEOUT' : null,
      retryable: sourceId === 'source-a', latency_ms: 12,
      evidence: sourceId === 'source-a' ? { message: 'TimeoutError: timed out' } : { writes: 0 },
      created_at: '2026-10-12T00:00:00Z',
    }] }));
  }
  if (request.method === 'POST' && request.url === '/api/data-center/sources/source-b/test') {
    testCalls += 1;
    request.resume();
    return request.on('end', () => response.end(JSON.stringify({ result: { status: 'passed', writes: 0 } })));
  }
  if (request.method === 'PUT' && request.url === '/api/data-center/routes') {
    let body = '';
    request.on('data', chunk => { body += chunk; });
    return request.on('end', () => {
      const payload = JSON.parse(body); routePutBodies.push(payload);
      const update = payload.routes[0]; routes = routes.map(route => route.route_id === update.route_id ? { ...route, ...update } : route);
      response.end(JSON.stringify({ items: routes }));
    });
  }
  if (request.method === 'POST' && request.url === '/api/data-center/routes/test') {
    let body = '';
    request.on('data', chunk => { body += chunk; });
    return request.on('end', () => {
      const payload = JSON.parse(body); routeTestBodies.push(payload);
      const route = routes.find(item => item.route_id === payload.route_id);
      const result = payload.live ? {
        source_id: route.source_id, route_id: route.route_id, dataset: route.dataset,
        endpoint: route.endpoint, dataset_id: route.dataset, endpoint_id: route.endpoint,
        status: 'policy_blocked', mode: 'live_read', writes: 0, sample_rows: 0,
        error_code: 'HOST_NOT_ALLOWED', error_class: 'policy', retryable: false,
        evidence: { writes: 0, required_hosts: ['fixture.example'], allowed_hosts: [] },
      } : {
        source_id: route.source_id, route_id: route.route_id, dataset: route.dataset,
        endpoint: route.endpoint, dataset_id: route.dataset, endpoint_id: route.endpoint,
        status: 'ready', mode: 'contract_only', writes: 0, sample_rows: 0,
        evidence: { writes: 0, route_enabled: route.enabled },
      };
      response.end(JSON.stringify({ result }));
    });
  }
  if (request.url === '/') {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    return response.end(page);
  }
  response.statusCode = 404;
  response.end(JSON.stringify({ detail: `unexpected fixture request: ${request.method} ${request.url}` }));
});

await new Promise(resolveListen => server.listen(0, '127.0.0.1', resolveListen));
const profile = mkdtempSync(join(tmpdir(), 'scq-source-vtable-'));
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
  socket.onmessage = event => {
    const data = JSON.parse(event.data), pair = pending.get(data.id);
    if (pair) { pending.delete(data.id); data.error ? pair.reject(data.error) : pair.resolve(data.result); }
  };
  const command = (method, params = {}) => new Promise((resolveCommand, rejectCommand) => {
    const id = ++sequence; pending.set(id, { resolve: resolveCommand, reject: rejectCommand });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const clickCanvas = async (offsetX, rowIndex) => {
    const point = await evaluate(`(()=>{const r=document.querySelector('#dc-source-list .app-vtable-host').getBoundingClientRect();return{x:r.left+${offsetX},y:r.top+44+(${rowIndex}*44)+22}})()`);
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', clickCount: 1 });
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'left', clickCount: 1 });
  };
  const clickRouteCanvas = async (offsetX, rowIndex) => {
    const point = await evaluate(`(()=>{const r=document.querySelector('#dc-route-list .app-vtable-host').getBoundingClientRect();const offset=${offsetX};return{x:r.left+(offset<0?r.width+offset:offset),y:r.top+44+(${rowIndex}*44)+22}})()`);
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', clickCount: 1 });
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'left', clickCount: 1 });
  };

  await command('Page.enable');
  await command('Emulation.setDeviceMetricsOverride', { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false });
  await command('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
  await wait(500);
  await evaluate('document.querySelector("#open-routes").click()');
  await wait(900);
  assert.equal(await evaluate('document.querySelectorAll("#dc-source-list th").length'), 6);
  assert.equal(await evaluate('document.querySelectorAll("#dc-source-list .app-vtable-host").length'), 1);
  assert.ok(await evaluate('Math.abs(document.querySelector(".dc-source-catalog").getBoundingClientRect().height-document.querySelector(".dc-source-history").getBoundingClientRect().height)<1'));
  assert.equal(await evaluate('document.querySelectorAll("#dc-source-probe-history th").length'), 4);
  assert.equal(await evaluate('document.querySelector("#dc-source-probe-history [data-probe-guidance]").textContent'), 'UPSTREAM_TIMEOUT');
  await evaluate('document.querySelector("#dc-source-probe-history [data-probe-guidance]").click()');
  assert.equal(await evaluate('document.querySelector("#dc-source-probe-dialog").open'), true);
  assert.ok(await evaluate('document.querySelector("#dc-source-probe-detail").textContent.includes("常见原因")'));
  assert.ok(await evaluate('document.querySelector("#dc-source-probe-detail").textContent.includes("上游响应时间超过当前超时限制")'));
  assert.ok(await evaluate('document.querySelector("#dc-source-probe-detail").textContent.includes("处理方法")'));
  await evaluate('document.querySelector("#dc-source-probe-dialog").close()');

  await evaluate('window.__sourceHost=document.querySelector("#dc-source-list .app-vtable-host")');
  await clickCanvas(56, 1);
  await wait(500);
  assert.equal(await evaluate('document.querySelectorAll("[data-source-row]")[1].getAttribute("aria-selected")'), 'true');
  assert.equal(await evaluate('window.__sourceHost.isConnected'), false, 'selection must recreate VTable with the selected-row fill');
  assert.ok(await evaluate('document.querySelector("#dc-source-probe-context").textContent.includes("数据源 B")'));
  assert.equal(await evaluate('document.querySelector("#dc-source-probe-history [data-probe-guidance]").textContent'), '无错误');
  await evaluate('document.querySelector("#dc-source-probe-history [data-probe-guidance]").click()');
  assert.ok(await evaluate('document.querySelector("#dc-source-probe-detail").textContent.includes("无需重试")'));
  await evaluate('document.querySelector("#dc-source-probe-dialog").close()');

  await clickCanvas(431, 1);
  await wait(250);
  assert.equal(await evaluate('document.querySelector("#dc-source-capability-dialog").open'), true);
  assert.equal(await evaluate('document.querySelectorAll("#dc-source-capability-detail article").length'), 4);
  assert.ok(await evaluate('document.querySelector("#dc-source-capability-detail").textContent.includes("components-b")'));
  await evaluate('document.querySelector("#dc-source-capability-dialog").close()');

  await clickCanvas(570, 1);
  await wait(250);
  assert.equal(await evaluate('document.querySelector("#dc-source-dialog").open'), true);
  assert.equal(await evaluate('document.querySelector("#dc-source-dialog-title").textContent'), '数据源 B');
  await evaluate('document.querySelector("#dc-source-dialog").close()');

  await clickCanvas(666, 1);
  await wait(600);
  assert.equal(testCalls, 1);
  assert.ok(await evaluate('document.querySelector("#global-feedback").textContent.includes("连接测试通过")'));

  await evaluate('document.querySelector(\'[data-dc-route-tab="routes"]\').click()');
  await wait(600);
  assert.equal(await evaluate('document.querySelectorAll("#dc-route-list th").length'), 6);
  assert.equal(await evaluate('document.querySelectorAll("#dc-route-list tbody tr").length'), 2);
  assert.equal(await evaluate('document.querySelectorAll("#dc-route-list .app-vtable-host").length'), 1);
  assert.equal(await evaluate('document.querySelectorAll("[data-route-row]")[0].getAttribute("aria-selected")'), 'true');
  assert.ok(await evaluate('document.querySelector("#dc-route-selection-context").textContent.includes("数据源 A")'));
  assert.equal(await evaluate('document.querySelector("#dc-route-check").textContent'), '检查配置');
  assert.equal(await evaluate('document.querySelector("#dc-route-test").textContent'), '连接测试');

  await evaluate('window.__routeHost=document.querySelector("#dc-route-list .app-vtable-host")');
  await clickRouteCanvas(70, 1);
  await wait(350);
  assert.equal(await evaluate('document.querySelectorAll("[data-route-row]")[1].getAttribute("aria-selected")'), 'true');
  assert.equal(await evaluate('window.__routeHost.isConnected'), false, 'route selection must recreate VTable with the selected-row fill');

  for (const offset of [600, 640, 680, 720, 760]) {
    await clickRouteCanvas(offset, 1);
    await wait(100);
    if (await evaluate('document.querySelector("#dc-route-dialog").open')) break;
  }
  assert.equal(await evaluate('document.querySelector("#dc-route-dialog").open'), true);
  assert.ok(await evaluate('document.querySelector("#dc-route-dialog-title").textContent.includes("fixture-route-fallback")'));
  assert.equal(await evaluate('document.querySelector(\'[data-rf="priority"]\').value'), '20');
  assert.equal(await evaluate('document.querySelector(\'[data-rf="backoff_seconds"]\').value'), '2.5');
  assert.equal(await evaluate('document.querySelectorAll(\'[data-rf="source_id"] option\').length'), 1);
  assert.equal(await evaluate('document.querySelector(\'[data-rf="source_id"]\').value'), 'source-a');

  await evaluate(`(()=>{document.querySelector('[data-rf="enabled"]').value='true';document.querySelector('[data-rf="fallback_policy"]').value='primary';document.querySelector('#dc-route-form').requestSubmit()})()`);
  await wait(200);
  assert.equal(routePutBodies.length, 0);
  assert.ok(await evaluate('document.querySelector("#dc-route-form-error").textContent.includes("已有启用的主源")'));
  await evaluate(`(()=>{document.querySelector('[data-rf="fallback_policy"]').value='on_failure';document.querySelector('[data-rf="requests_per_minute"]').value='0';document.querySelector('#dc-route-form').requestSubmit()})()`);
  await wait(200);
  assert.equal(routePutBodies.length, 0);
  assert.ok(await evaluate('document.querySelector("#dc-route-form-error").textContent.includes("每分钟请求")'));
  await evaluate(`(()=>{document.querySelector('[data-rf="requests_per_minute"]').value='12';document.querySelector('[data-rf="priority"]').value='25';document.querySelector('[data-rf="backoff_seconds"]').value='3.5';document.querySelector('#dc-route-form').requestSubmit()})()`);
  await wait(500);
  assert.equal(routePutBodies.length, 1);
  assert.equal(routePutBodies[0].routes[0].route_id, 'fixture-route-fallback');
  assert.equal(routePutBodies[0].routes[0].priority, 25);
  assert.equal(routePutBodies[0].routes[0].backoff_seconds, 3.5);
  assert.equal(await evaluate('document.querySelector("#dc-route-dialog").open'), false);
  assert.equal(await evaluate('document.querySelectorAll("[data-route-row]")[1].getAttribute("aria-selected")'), 'true');

  await evaluate('document.querySelector("#dc-route-check").click()');
  await wait(350);
  assert.equal(routeTestBodies.length, 1);
  assert.equal(routeTestBodies[0].live, false);
  assert.equal(await evaluate('document.querySelector("#dc-route-test-dialog").open'), true);
  assert.ok(await evaluate('document.querySelector("#dc-route-test-detail").textContent.includes("配置契约检查")'));
  assert.ok(await evaluate('document.querySelector("#dc-route-test-detail").textContent.includes("就绪")'));
  await evaluate('document.querySelector("#dc-route-test-dialog").close()');

  await evaluate('document.querySelector("#dc-route-test").click()');
  await wait(350);
  assert.equal(routeTestBodies.length, 2);
  assert.equal(routeTestBodies[1].live, true);
  assert.ok(await evaluate('document.querySelector("#dc-route-test-detail").textContent.includes("策略阻断")'));
  assert.ok(await evaluate('document.querySelector("#dc-route-test-detail").textContent.includes("HOST_NOT_ALLOWED")'));
  assert.ok(await evaluate('document.querySelector("#dc-route-test-detail").textContent.includes("路由需要访问的上游主机")'));
  assert.equal(await evaluate('document.querySelector("#global-feedback").classList.contains("is-error")'), true);
  assert.equal(await evaluate('document.querySelectorAll("#dc-route-list tbody tr").length'), 2, 'test result must not replace the route table');

  await evaluate('document.querySelector("#dc-route-test-dialog").close()');
  await command('Emulation.setDeviceMetricsOverride', { width: 741, height: 900, deviceScaleFactor: 1, mobile: false });
  await wait(350);
  assert.ok(await evaluate('document.body.scrollWidth<=document.body.clientWidth+2'), 'route page must not cause narrow viewport overflow');
  assert.ok(await evaluate('getComputedStyle(document.querySelector(".dc-route-workspace")).gridTemplateColumns.split(" ").length===1'));
  await evaluate('document.querySelectorAll("[data-route-edit]")[1].click()');
  assert.ok(await evaluate(`(()=>{const r=document.querySelector('#dc-route-dialog').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight})()`), 'route dialog must fit the narrow viewport');
  await evaluate('document.querySelector("#dc-route-dialog").close()');

  console.log('data source and route VTable browser: selection, dialogs, validation, save and modal connection results passed');
} finally {
  socket?.close(); browser.kill(); server.close();
  await wait(700);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }); } catch {}
}
