import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const cid='ic_'+'a'.repeat(24), requests=[];
const definition={indicator_id:'sma',name:'SMA <样例>',parameters:{period:3},outputs:['value'],formula:'平均',unit:'price',source_reference:'公开定义',minimum_history:3};
let configs=[];
const server=createServer((req,res)=>{
  if(req.url.startsWith('/api/')) {
    res.setHeader('Content-Type','application/json; charset=utf-8'); let raw=''; req.on('data',x=>raw+=x); req.on('end',()=>{
      const body=raw?JSON.parse(raw):null; requests.push({path:req.url,method:req.method,body}); let result;
      if(req.url==='/api/indicators') result={items:[definition]};
      else if(req.url==='/api/indicators/factor-artifacts') result={items:[{artifact_id:'artifact-fixture',name:'指标因子',start_date:'2026-03-02',end_date:'2026-03-20'}]};
      else if(req.url==='/api/indicators/registrations') { if(body) configs=[{config_id:cid,name:definition.name,definition,adjustment:body.adjustment,enabled:true}]; result=body?configs[0]:{items:configs}; }
      else if(req.url.endsWith('/values')) result={config:configs[0],rows:[{trade_date:'2026-03-02',values:{value:12.5},status:'ready',available_at:'2026-03-02T18:00:00+08:00'}],row_count:1,total:1,data_version_id:'fixture-v1',cache_hit:false};
      else if(req.url.endsWith('/strategy-example')) result={source_code:'DATASET_REQUIREMENTS = ["indicator_values"]',adjustment:'raw',minimum_history:3,note:'fixture'};
      else if(req.url.endsWith('/factor')) result={definition:{factor_id:'indicator_test'}};
      else if(req.url.includes('/factor-artifacts/')) result={registered:true,artifact_id:'artifact-fixture'};
      else if(req.method==='PUT') { configs[0].enabled=body.enabled; result=configs[0]; }
      else result={items:[]};
      res.end(JSON.stringify({result}));
    }); return;
  }
  const asset=req.url.slice(1);
  if(['indicators.js','styles.css','quant-ui-candidate.css','indicators.css','vtable-adapter.css','vtable-adapter.js','vendor/vtable/vtable.min.js'].includes(asset)) {
    res.setHeader('Content-Type',asset.endsWith('.js')?'application/javascript':'text/css'); return res.end(readFileSync(join(root,'web',asset)));
  }
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.end(`<!doctype html><html><head><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/quant-ui-candidate.css"><link rel="stylesheet" href="/indicators.css"><link rel="stylesheet" href="/vtable-adapter.css"></head><body><main><section id="page-strategy-datasets"></section><section id="dc-view-assets"></section></main><script>function startNewStrategy(d){window.imported=d} function activatePage(){} function activateStage76Workspace(){}</script><script src="/vendor/vtable/vtable.min.js"></script><script src="/vtable-adapter.js"></script><script src="/indicators.js"></script></body></html>`);
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const profile=mkdtempSync(join(tmpdir(),'scq-r2-browser-'));
const browser=spawn(process.env.SCQ_TEST_BROWSER || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
const wait=ms=>new Promise(r=>setTimeout(r,ms)); let socket;
try {
  let port; for(let i=0;i<100;i++){try{port=readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{} await wait(100);}
  assert.ok(port);
  const targets=await fetch(`http://127.0.0.1:${port}/json`).then(r=>r.json());
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
  const pending=new Map(); let sequence=0;
  socket.onmessage=event=>{const d=JSON.parse(event.data),p=pending.get(d.id);if(p){pending.delete(d.id);d.error?p.reject(d.error):p.resolve(d.result);}};
  const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;};
  await command('Page.navigate',{url:`http://127.0.0.1:${server.address().port}/`}); await wait(800);
  assert.equal(await evaluate('document.querySelector("#r2-definition").options.length'),1);
  await evaluate('document.querySelector("#r2-register").requestSubmit()'); await wait(400);
  assert.equal(configs.length,1); assert.equal(await evaluate('document.querySelector("#r2-config").value'),cid);
  await evaluate('document.querySelector("#r2-query").requestSubmit()'); await wait(500);
  assert.ok(await evaluate('document.querySelector("#r2-values canvas")!==null'),'actual VTable rendered');
  assert.ok(await evaluate('document.querySelector("#r2-values").textContent.includes("fixture-v1")'));
  await evaluate('document.querySelector("#r2-example").click()'); await wait(300);
  assert.ok((await evaluate('window.imported.source_code')).includes('indicator_values'));
  await evaluate('document.querySelector("#r2-factor-flow").open=true;document.querySelector("#r2-factor").click()'); await wait(300);
  assert.equal(requests.find(r=>r.path.endsWith('/factor')).body.output,'value');
  await evaluate('document.querySelector("#r2-artifact").value="artifact-fixture";document.querySelector("#r2-reason").value="已看报告";document.querySelector("#r2-approve").requestSubmit()'); await wait(300);
  assert.equal(requests.filter(r=>r.path.includes('/factor-artifacts/')).length,1);
  await evaluate('document.querySelector("#r2-enabled").click()'); await wait(300); assert.equal(configs[0].enabled,false);
  await command('Emulation.setDeviceMetricsOverride',{width:740,height:900,deviceScaleFactor:1,mobile:false});
  await evaluate('document.documentElement.dataset.theme="dark"'); await wait(200);
  assert.equal(await evaluate('document.querySelector("#r2-config-table").innerHTML.includes("<样例>")'),false,'escaped source labels');
  console.log('R2 browser: registration, values with real VTable, strategy import, factor generation, explicit selection, disable and dark/narrow rendering passed');
} finally {
  socket?.close(); browser.kill(); server.close(); await wait(1000);
  assert.ok(profile.startsWith(join(tmpdir(),'scq-r2-browser-')));
  try {rmSync(profile,{recursive:true,force:true,maxRetries:10,retryDelay:300});} catch {console.warn('browser-owned temporary profile retained: '+profile);}
}
