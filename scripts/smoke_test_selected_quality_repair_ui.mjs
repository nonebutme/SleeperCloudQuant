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
const assets = ['styles.css','quant-ui-candidate.css','data_center.css','vtable-adapter.css','vtable-adapter.js','vendor/vtable/vtable.min.js'];
const requests=[];
const issues=['one','two','unselected'].map((issue_id,n)=>({issue_id,dataset:'a_share_daily',rule_id:'ohlcv_validity',symbol:'00000'+(n+1),observation_at:'2026-01-08',status:'open',severity:'error',evidence:{adjustment:'raw'}}));
const server=createServer((req,res)=>{
  const asset=req.url.slice(1);
  if(assets.includes(asset)){res.setHeader('Content-Type',asset.endsWith('.js')?'application/javascript':'text/css');return res.end(readFileSync(join(root,'web',asset)))}
  if(req.url==='/quality.js'){
    res.setHeader('Content-Type','application/javascript');
    const code=readFileSync(join(root,'web/data_center_stage_c.js'),'utf8');
    return res.end(code.replace('window.openDataCenterView=openView;', 'window.__selectedTest={state,loadQuality,bulkQuality,renderQualitySelection};window.openDataCenterView=openView;'));
  }
  if(req.url.startsWith('/api/')){
    res.setHeader('Content-Type','application/json');
    if(req.method==='GET')return res.end(JSON.stringify(req.url.includes('/issues?')?{items:issues}:{result:{}}));
    let raw='';req.on('data',x=>raw+=x);req.on('end',()=>{
      const body=JSON.parse(raw);requests.push({path:req.url,body});
      if(req.url.endsWith('correct-preview'))return res.end(JSON.stringify({result:{items:body.issue_ids.map(issue_id=>({issue_id,scope:{symbol:issues.find(x=>x.issue_id===issue_id).symbol,start_date:'2026-01-08',adjustments:['raw']},before:{high:9},after:{}}))}}));
      res.end(JSON.stringify({result:{processed_count:body.issue_ids.length,automatically_effective:true}}));
    });return;
  }
  res.setHeader('Content-Type','text/html; charset=utf-8');
  const body=html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace('</body>','<script src="/vendor/vtable/vtable.min.js"></script><script src="/vtable-adapter.js"></script><script src="/quality.js"></script></body>');
  res.end(body);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const profile = mkdtempSync(join(tmpdir(), 'scq-selected-browser-'));
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
  await evaluate(`document.querySelector('#page-market').classList.add('is-active');document.querySelector('#dc-view-quality').classList.add('is-active');window.__selectedTest.state.qualityItems=${JSON.stringify(issues)};window.confirm=()=>{window.confirmCount=(window.confirmCount||0)+1;return true};window.__selectedTest.loadQuality()`);
  await evaluate(`window.__selectedTest.state.selectedIssues=new Set(['one','two']);document.querySelector('#dc-quality-bulk-reason').value='verified evidence';window.__selectedTest.renderQualitySelection();window.__selectedTest.bulkQuality('correct')`);
  assert.equal(await evaluate('window.confirmCount||0'),0,'preview must not confirm or mutate');
  await evaluate(`window.__selectedTest.state.selectedIssues=new Set(['unselected']);document.querySelector('[name="correction-0"]').value='{"high":10.5}';document.querySelector('[name="correction-1"]').value='{"high":10.5}';document.querySelector('#dc-selected-correction-form').requestSubmit()`);
  await wait(500);
  const corrections=requests.filter(x=>x.path.endsWith('/correct'));
  assert.equal(corrections.length,1);
  assert.deepEqual(corrections[0].body.issue_ids,['one','two']);
  assert.deepEqual(corrections[0].body.corrections.map(x=>x.issue_id),['one','two']);
  assert.equal(await evaluate('window.confirmCount'),1,'one confirmation for batch correction');
  await evaluate(`window.__selectedTest.state.selectedIssues=new Set(['one','two']);window.__selectedTest.bulkQuality('refetch')`);
  const refetch=requests.filter(x=>x.path.endsWith('/refetch'));
  assert.equal(refetch.length,1);assert.deepEqual(refetch[0].body.issue_ids,['one','two']);
  assert.equal(refetch[0].body.run_now,true);
  assert.equal(await evaluate('window.confirmCount'),2);
  assert.ok(await evaluate('window.AppVTable.instanceCount()>0'));
  assert.ok(await evaluate('document.querySelector("#dc-quality-list canvas")!==null'));
  console.log('selected repair browser: frozen IDs, one confirmation, automatic refetch, actual VTable passed');

} finally {
  socket?.close(); browser.kill(); server.close();
  await wait(1000);
  assert.ok(profile.startsWith(join(tmpdir(), 'scq-selected-browser-')));
  try { rmSync(profile, {recursive: true, force: true, maxRetries: 10, retryDelay: 300}); }
  catch { console.warn(`browser-owned temporary profile retained: ${profile}`); }
}
