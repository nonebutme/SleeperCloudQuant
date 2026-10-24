// 正式入口只读 UI 检查；不注册指标、不提交任务、不更新行情。
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawn} from 'node:child_process';
const profile=mkdtempSync(join(tmpdir(),'scq-r2-live-'));
const pictures=mkdtempSync(join(resolve('tmp'),'r2-ui-'));
const browser=spawn(process.env.SCQ_TEST_BROWSER || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
const wait=ms=>new Promise(r=>setTimeout(r,ms)); let socket;
try {
  let port; for(let i=0;i<100;i++){try{port=readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{} await wait(100);}
  assert.ok(port,'isolated browser startup');
  const targets=await fetch(`http://127.0.0.1:${port}/json`).then(r=>r.json());
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
  const pending=new Map(),errors=[]; let sequence=0;
  socket.onmessage=event=>{const d=JSON.parse(event.data),p=pending.get(d.id);if(d.method==='Runtime.exceptionThrown') errors.push(d.params.exceptionDetails.text); if(p){pending.delete(d.id);d.error?p.reject(d.error):p.resolve(d.result);}};
  const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;};
  await command('Runtime.enable'); await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:'http://127.0.0.1:8010/?page=strategy-datasets'});
  let loaded=false;
  for(let i=0;i<100;i++){loaded=await evaluate('Boolean(document.querySelector("#r2-definition")?.options.length>=8)');if(loaded) break;await wait(200);}
  assert.ok(loaded,'formal indicator library loaded');
  let catalogLoaded=false;
  for(let i=0;i<100;i++){catalogLoaded=await evaluate('Boolean(document.querySelector("[data-sd-dataset=indicator_values]"))');if(catalogLoaded) break;await wait(200);}
  assert.ok(catalogLoaded,'indicator product appears in the existing dataset catalog');
  assert.equal(await evaluate('document.querySelector("#page-strategy-datasets").classList.contains("is-active")'),true);
  const screenshot=async name=>{const r=await command('Page.captureScreenshot',{format:'png'});writeFileSync(join(pictures,name),Buffer.from(r.data,'base64'));};
  await screenshot('datasets-light.png');
  await evaluate('activatePage("market");window.openDataCenterView("assets")'); await wait(1000);
  assert.ok(await evaluate('document.querySelector("#r2-query").getBoundingClientRect().height>0'),'formal browser indicator section visible');
  await screenshot('browser-light.png');
  await evaluate('activatePage("strategy-datasets");document.documentElement.dataset.theme="dark"');
  await command('Emulation.setDeviceMetricsOverride',{width:740,height:1000,deviceScaleFactor:1,mobile:false}); await wait(500);
  const overflow=await evaluate('({width:window.innerWidth,scroll:document.documentElement.scrollWidth,indicator:document.querySelector("#r2-indicator-library").getBoundingClientRect().width})');
  await screenshot('datasets-dark-narrow.png');
  assert.ok(overflow.scroll<=overflow.width+1,JSON.stringify(overflow));
  assert.deepEqual(errors,[],'no uncaught page exceptions');
  console.log(JSON.stringify({status:'passed',url:'http://127.0.0.1:8010/',indicator_count:await evaluate('document.querySelector("#r2-definition").options.length'),overflow,screenshots:pictures}));
} finally {
  socket?.close(); browser.kill(); await wait(1000);
  assert.ok(profile.startsWith(join(tmpdir(),'scq-r2-live-')));
  try {rmSync(profile,{recursive:true,force:true,maxRetries:10,retryDelay:300});} catch {console.warn('browser-owned temporary profile retained: '+profile);}
}
