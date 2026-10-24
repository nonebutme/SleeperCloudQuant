import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFileSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

// 仅访问本脚本的本机模拟接口；不启动正式应用、不触碰正式数据库。
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const html = readFileSync(join(root, 'web/index.html'), 'utf8');
const marker = '<section class="dc-surface" aria-labelledby="dc-maintenance-title">';
const start = html.indexOf(marker), end = html.indexOf('</section>', start) + 10;
assert.ok(start >= 0 && end > start);
const fragment = html.slice(start, end);
let items = [], starts = 0, resumes = 0;
const server = createServer((req, res) => {
  const assets = ['styles.css','quant-ui-candidate.css','data_center.css','vtable-adapter.css','vtable-adapter.js','vendor/vtable/vtable.min.js'];
  const asset = req.url.slice(1);
  if (assets.includes(asset)) {
    res.setHeader('Content-Type', asset.endsWith('.js') ? 'application/javascript' : 'text/css');
    return res.end(readFileSync(join(root, 'web', asset)));
  }
  if (req.url === '/data-maintenance.js') {
    res.setHeader('Content-Type', 'application/javascript');
    return res.end(readFileSync(join(root, 'web/data-maintenance.js')));
  }
  if (req.url.startsWith('/api/')) {
    res.setHeader('Content-Type', 'application/json');
    if (req.method === 'GET') return res.end(JSON.stringify({items}));
    req.resume();
    req.on('end', () => {
      if (req.url.endsWith('/resume')) { resumes++; items[0].status = 'running'; }
      else { starts++; items = [{batch_id: 'maintenance-fixture', status: 'running', phase: 'prices',
        created_at: '2026-09-13', request: {target_trade_date: '2026-01-08'}, result: {}}]; }
      res.end(JSON.stringify({result: items[0]}));
    });
    return;
  }
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(`<!doctype html><html lang="zh-CN"><head><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/quant-ui-candidate.css"><link rel="stylesheet" href="/data_center.css"><link rel="stylesheet" href="/vtable-adapter.css"></head><body><main>${fragment}</main><script src="/vendor/vtable/vtable.min.js"></script><script src="/vtable-adapter.js"></script><script src="/data-maintenance.js"></script></body></html>`);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const profile = mkdtempSync(join(tmpdir(), 'scq-r1-browser-'));
const browser = spawn(process.env.SCQ_TEST_BROWSER || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ['--headless=new', '--disable-gpu', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  {windowsHide: true, stdio: 'ignore'});
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]; break; } catch {}
    await wait(100);
  }
  assert.ok(port, 'isolated headless browser did not start');
  const targets = await fetch(`http://127.0.0.1:${port}/json`).then(r => r.json());
  socket = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  const pending = new Map(); let sequence = 0;
  socket.onmessage = event => {
    const data = JSON.parse(event.data), pair = pending.get(data.id);
    if (pair) { pending.delete(data.id); data.error ? pair.reject(data.error) : pair.resolve(data.result); }
  };
  const command = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence; pending.set(id, {resolve, reject}); socket.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await command('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await command('Page.enable');
  await command('Page.navigate', {url: `http://127.0.0.1:${server.address().port}/`});
  await wait(800);
  assert.ok(await evaluate('document.querySelector("#dc-maintenance-list").textContent.includes("尚无更新记录")'));
  await evaluate('document.querySelector("#dc-maintenance-form").requestSubmit()');
  await wait(500);
  assert.equal(starts, 1);
  assert.equal(await evaluate('document.querySelector("#dc-maintenance-form button").disabled'), true);
  items[0].status = 'failed'; items[0].result.error = '<img src=x onerror=alert(1)>fixture failure';
  await wait(3300);
  assert.equal(await evaluate('document.querySelectorAll("#dc-maintenance-list img").length'), 0);
  await evaluate('document.querySelector("[data-maintenance-resume]").click()');
  await wait(500); assert.equal(resumes, 1);
  items[0].status = 'completed'; items[0].phase = 'done'; items[0].result = {};
  await wait(3300);
  assert.ok(await evaluate('document.querySelector("#dc-maintenance-list").textContent.includes("已更新并生效")'));
  assert.equal(await evaluate('document.querySelector("#dc-maintenance-form button").disabled'), false);
  assert.equal(await evaluate('window.AppVTable.instanceCount()'), 1);
  assert.ok(await evaluate('document.querySelector("#dc-maintenance-list canvas") !== null'));
  const screenshot = await command('Page.captureScreenshot', {format: 'png'});
  const evidence = join(root, 'tmp', 'r1-maintenance-browser.png');
  writeFileSync(evidence, Buffer.from(screenshot.data, 'base64'));
  console.log(`data maintenance isolated browser: start/failure/resume/completion/escaping passed; screenshot=${evidence}`);
} finally {
  socket?.close(); browser.kill(); server.close();
  await wait(1000);
  assert.ok(profile.startsWith(join(tmpdir(), 'scq-r1-browser-')));
  try { rmSync(profile, {recursive: true, force: true, maxRetries: 10, retryDelay: 300}); }
  catch { console.warn(`browser-owned temporary profile retained: ${profile}`); }
}
