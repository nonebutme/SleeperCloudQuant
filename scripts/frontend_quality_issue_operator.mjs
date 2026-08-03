const baseUrl=process.argv[2]||"http://127.0.0.1:8010";
const debugUrl=process.argv[3]||"http://127.0.0.1:9224/json";
const action=process.argv[4]||"inspect";
const requestedTarget=process.argv[5]||"";
const issueId=process.argv[6]||"";
const disposition=process.argv[7]||"";
const reason=process.argv.slice(8).join(" ");
const origin=new URL(debugUrl).origin;
let target;
if(requestedTarget){target=(await fetch(debugUrl).then(r=>r.json())).find(item=>item.id===requestedTarget)}else{target=await fetch(`${origin}/json/new?${encodeURIComponent("about:blank")}`,{method:"PUT"}).then(r=>r.json())}
if(!target)throw new Error("找不到指定的独立浏览器标签页");
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener("open",resolve,{once:true});socket.addEventListener("error",reject,{once:true})});
let sequence=0;const pending=new Map(),exceptions=[];
socket.addEventListener("message",event=>{const message=JSON.parse(String(event.data));if(message.id&&pending.has(message.id)){const request=pending.get(message.id);pending.delete(message.id);message.error?request.reject(new Error(JSON.stringify(message.error))):request.resolve(message.result||{})}if(message.method==="Runtime.exceptionThrown")exceptions.push(message.params?.exceptionDetails?.exception?.description||message.params?.exceptionDetails?.text||"Runtime exception")});
const command=(method,params={})=>{const id=++sequence;socket.send(JSON.stringify({id,method,params}));return new Promise((resolve,reject)=>pending.set(id,{resolve,reject}))};
const evaluate=async(expression,awaitPromise=false)=>{const response=await command("Runtime.evaluate",{expression,awaitPromise,returnByValue:true});if(response.exceptionDetails)throw new Error(JSON.stringify(response.exceptionDetails));return response.result?.value};
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
await command("Page.enable");await command("Runtime.enable");
if(!requestedTarget){await command("Emulation.setDeviceMetricsOverride",{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await command("Page.navigate",{url:`${baseUrl}/?page=market&dc_view=quality`});await wait(6000)}
if(action==="inspect"){
  const ids=await evaluate(`[...document.querySelectorAll('[data-issue]')].map(node=>node.dataset.issue)`),issues=[];
  for(const id of ids){await evaluate(`(()=>{const node=[...document.querySelectorAll('[data-issue]')].find(item=>item.dataset.issue===${JSON.stringify(id)});if(!node)throw new Error('异常入口不存在');node.click()})()`);await wait(500);issues.push(await evaluate(`(()=>({issueId:${JSON.stringify(id)},status:document.querySelector('#dc-quality-output .dc-status-pill')?.textContent?.trim()||'',heading:document.querySelector('#dc-quality-output .dc-detail-heading')?.textContent?.trim()||'',rule:[...document.querySelectorAll('#dc-quality-output dt')].find(x=>x.textContent.trim()==='规则')?.nextElementSibling?.textContent?.trim()||'',evidence:document.querySelector('#dc-quality-output pre')?.textContent?.trim()||'',history:document.querySelector('#dc-quality-output .dc-history-list')?.textContent?.trim()||'',canProcess:!!document.querySelector('#dc-disposition-form')}))()`))}
  console.log(JSON.stringify({targetId:target.id,url:target.url,count:ids.length,summary:await evaluate(`document.querySelector('#dc-quality-summary')?.textContent?.trim()||''`),issues,exceptions},null,2));
}else if(action==="inspect-scan"){
  const scanId=issueId;if(!scanId)throw new Error("inspect-scan 需要 scanId");
  await evaluate(`(()=>{const node=[...document.querySelectorAll('[data-quality-scan-issues]')].find(item=>item.dataset.qualityScanIssues===${JSON.stringify(scanId)});if(!node)throw new Error('检查任务的异常入口不存在');node.click()})()`);await wait(1300);
  const ids=await evaluate(`[...document.querySelectorAll('[data-issue]')].map(node=>node.dataset.issue)`),issues=[];
  for(const id of ids){await evaluate(`(()=>{const node=[...document.querySelectorAll('[data-issue]')].find(item=>item.dataset.issue===${JSON.stringify(id)});node?.click()})()`);await wait(450);issues.push(await evaluate(`(()=>({issueId:${JSON.stringify(id)},detail:document.querySelector('#dc-quality-output')?.textContent?.trim()||'',evidence:document.querySelector('#dc-quality-output pre')?.textContent?.trim()||''}))()`))}
  console.log(JSON.stringify({targetId:target.id,scanId,issues,exceptions},null,2));}else if(action==="scan"){
  const symbol=issueId,dateValue=disposition;
  if(!symbol||!dateValue)throw new Error("scan 需要 targetId、symbol、date");
  await evaluate(`(()=>{const form=document.querySelector('#dc-quality-scan-form');window.confirm=()=>true;form.elements.dataset.value='a_share_daily';form.elements.date_from.value=${JSON.stringify(dateValue)};form.elements.date_to.value=${JSON.stringify(dateValue)};form.elements.scope.value='symbols';form.elements.scope.dispatchEvent(new Event('change',{bubbles:true}));form.elements.symbols.value=${JSON.stringify(symbol)};[...form.querySelectorAll('input[name="adjustments"],input[name="rules"]')].forEach(node=>node.checked=true);form.requestSubmit()})()`);await wait(1200);
  let snapshot={};
  for(let index=0;index<90;index+=1){snapshot=await evaluate(`(()=>{const row=document.querySelector('#dc-quality-scan-list tbody tr'),status=row?.querySelector('.dc-status-pill')?.textContent?.trim()||'',scanId=row?.querySelector('code')?.textContent?.trim()||'';return{status,scanId,rowText:row?.textContent?.trim()||'',feedback:document.querySelector('#global-feedback')?.textContent?.trim()||''}})()`);if(["检查通过","发现问题","检查失败"].includes(snapshot.status)&&snapshot.rowText.includes(dateValue))break;await wait(1000)}
  console.log(JSON.stringify({targetId:target.id,symbol,date:dateValue,snapshot,exceptions},null,2));}else if(action==="refetch"){
  if(!issueId)throw new Error("refetch 需要 targetId 和 issueId");
  await evaluate(`(()=>{const node=[...document.querySelectorAll('[data-issue]')].find(item=>item.dataset.issue===${JSON.stringify(issueId)});if(!node)throw new Error('异常不在当前列表');node.click()})()`);await wait(600);
  const before=await evaluate(`(()=>({detail:document.querySelector('#dc-quality-output')?.textContent?.trim()||'',evidence:document.querySelector('#dc-quality-output pre')?.textContent?.trim()||'',canRefetch:!!document.querySelector('#dc-refetch')}))()`);
  if(!before.canRefetch)throw new Error(JSON.stringify({phase:"before-refetch",before}));
  await evaluate(`(()=>{window.confirm=()=>true;document.querySelector('#dc-refetch').click()})()`);await wait(2200);
  const after=await evaluate(`(()=>({feedback:document.querySelector('#global-feedback')?.textContent?.trim()||'',detail:document.querySelector('#dc-quality-output')?.textContent?.trim()||'',taskIds:[...document.querySelectorAll('[data-refetch-task]')].map(node=>node.dataset.refetchTask)}))()`);
  console.log(JSON.stringify({targetId:target.id,issueId,before,after,exceptions},null,2));}else if(action==="recheck-scan"){
  const scanId=issueId;if(!scanId)throw new Error("recheck-scan 需要 targetId 和 scanId");
  await evaluate(`(()=>{window.confirm=()=>true;const node=[...document.querySelectorAll('[data-quality-scan-recheck]')].find(item=>item.dataset.qualityScanRecheck===${JSON.stringify(scanId)});if(!node)throw new Error('复查按钮不存在');node.click()})()`);await wait(1300);
  let snapshot={};
  for(let index=0;index<90;index+=1){snapshot=await evaluate(`(()=>{const rows=[...document.querySelectorAll('#dc-quality-scan-list tbody tr')],row=rows[0],status=row?.querySelector('.dc-status-pill')?.textContent?.trim()||'',newScanId=row?.querySelector('code')?.textContent?.trim()||'';return{status,newScanId,rowText:row?.textContent?.trim()||'',feedback:document.querySelector('#global-feedback')?.textContent?.trim()||''}})()`);if(snapshot.newScanId&&snapshot.newScanId!==scanId&&["检查通过","发现问题","检查失败"].includes(snapshot.status))break;await wait(1000)}
  await evaluate(`(()=>{const form=document.querySelector('#dc-quality-filter'),status=form.elements.status;[...status.options].forEach(option=>option.selected=option.value==='corrected');const task=form.elements.source_task_id;if([...task.options].some(option=>option.value===${JSON.stringify(scanId)}))task.value=${JSON.stringify(scanId)};form.requestSubmit()})()`);await wait(1300);
  const issues=await evaluate(`(()=>[...document.querySelectorAll('[data-issue]')].map(node=>({issueId:node.dataset.issue,row:node.closest('tr')?.textContent?.trim()||''})))()`);
  if(issues.length)await evaluate(`document.querySelector('[data-issue]')?.click()`);await wait(500);
  const result=await evaluate(`(()=>({summary:document.querySelector('#dc-quality-summary')?.textContent?.trim()||'',list:document.querySelector('#dc-quality-list')?.textContent?.trim()||'',detail:document.querySelector('#dc-quality-output')?.textContent?.trim()||'',status:document.querySelector('#dc-quality-output .dc-status-pill')?.textContent?.trim()||''}))()`);
  console.log(JSON.stringify({targetId:target.id,parentScanId:scanId,snapshot,issues,result,exceptions},null,2));}else if(action==="process"){
  if(!issueId||!disposition||!reason)throw new Error("process 需要 targetId、issueId、action、reason");
  await evaluate(`(()=>{const node=[...document.querySelectorAll('[data-issue]')].find(item=>item.dataset.issue===${JSON.stringify(issueId)});if(!node)throw new Error('异常不在当前列表');node.click()})()`);await wait(600);
  const before=await evaluate(`(()=>({detail:document.querySelector('#dc-quality-output')?.textContent?.trim()||'',evidence:document.querySelector('#dc-quality-output pre')?.textContent?.trim()||'',canProcess:!!document.querySelector('#dc-disposition-form')}))()`);
  if(!before.canProcess)throw new Error(JSON.stringify({phase:"before",before}));
  await evaluate(`(()=>{const form=document.querySelector('#dc-disposition-form');form.elements.action.value=${JSON.stringify(disposition)};form.elements.action.dispatchEvent(new Event('change',{bubbles:true}));form.elements.reason.value=${JSON.stringify(reason)};form.requestSubmit()})()`);await wait(1800);
  const after=await evaluate(`(()=>({feedback:document.querySelector('#global-feedback')?.textContent?.trim()||'',summary:document.querySelector('#dc-quality-summary')?.textContent?.trim()||'',list:document.querySelector('#dc-quality-list')?.textContent?.trim()||'',detail:document.querySelector('#dc-quality-output')?.textContent?.trim()||'',status:document.querySelector('#dc-quality-output .dc-status-pill')?.textContent?.trim()||'',formStillPresent:!!document.querySelector('#dc-disposition-form')}))()`);
  console.log(JSON.stringify({targetId:target.id,issueId,disposition,reason,before,after,exceptions},null,2));
  await command("Page.close").catch(()=>{});
}else{throw new Error(`未知操作：${action}`)}
socket.close();