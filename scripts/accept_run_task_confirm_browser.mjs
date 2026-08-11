const baseUrl=process.argv[2]||"http://127.0.0.1:8010";
const debugUrl=process.argv[3]||"http://127.0.0.1:9224/json";
const debugOrigin=new URL(debugUrl).origin;
const target=await fetch(`${debugOrigin}/json/new?${encodeURIComponent("about:blank")}`,{method:"PUT"}).then(r=>r.json());
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener("open",resolve,{once:true});socket.addEventListener("error",reject,{once:true})});
let sequence=0;const pending=new Map(),exceptions=[];
socket.addEventListener("message",event=>{const message=JSON.parse(String(event.data));if(message.id&&pending.has(message.id)){const request=pending.get(message.id);pending.delete(message.id);message.error?request.reject(new Error(JSON.stringify(message.error))):request.resolve(message.result||{})}if(message.method==="Runtime.exceptionThrown")exceptions.push(message.params?.exceptionDetails?.exception?.description||message.params?.exceptionDetails?.text||"Runtime exception")});
const command=(method,params={})=>{const id=++sequence;socket.send(JSON.stringify({id,method,params}));return new Promise((resolve,reject)=>pending.set(id,{resolve,reject}))};
const evaluate=async expression=>{const response=await command("Runtime.evaluate",{expression,returnByValue:true});if(response.exceptionDetails)throw new Error(JSON.stringify(response.exceptionDetails));return response.result?.value};
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
try{
  await command("Page.enable");await command("Runtime.enable");
  await command("Page.addScriptToEvaluateOnNewDocument",{source:`(()=>{const original=window.fetch.bind(window);window.__runRequests=[];window.fetch=async(input,init={})=>{const url=String(input),method=String(init.method||"GET").toUpperCase();if(method==="POST"&&/\\/run(?:\\?|$)/.test(url))window.__runRequests.push(url);return original(input,init)}})();`});
  await command("Emulation.setDeviceMetricsOverride",{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await command("Page.navigate",{url:`${baseUrl}/?page=market&dc_view=sync`});await wait(6500);
  const available=await evaluate(`!!document.querySelector('[data-task-run]')`);
  const baselineRuns=await evaluate(`window.__runRequests.length`);
  if(!available)throw new Error(JSON.stringify({phase:"run-button-not-available",exceptions}));
  await evaluate(`document.documentElement.setAttribute('data-theme','dark');document.querySelector('[data-task-run]').click()`);await wait(400);
  const state=await evaluate(`(()=>{const dialog=document.querySelector('#dc-action-confirm-dialog'),rect=dialog.getBoundingClientRect(),style=getComputedStyle(dialog),backdrop=getComputedStyle(dialog,'::backdrop');return{open:dialog.open,modal:dialog.matches(':modal'),ariaModal:dialog.getAttribute('aria-modal'),panelBackground:style.backgroundColor,panelOpacity:style.opacity,backdrop:backdrop.backgroundColor,backdropPointerEvents:backdrop.pointerEvents,centerX:rect.left+rect.width/2,centerY:rect.top+rect.height/2,viewportX:innerWidth/2,viewportY:innerHeight/2,title:document.querySelector('#dc-action-confirm-title')?.textContent||'',submit:document.querySelector('#dc-action-confirm-submit')?.textContent||'',focused:document.activeElement?.id||''}})()`);
  await evaluate(`document.querySelector('#dc-action-confirm-cancel').click()`);await wait(400);
  const cancelled=await evaluate(`(()=>({open:document.querySelector('#dc-action-confirm-dialog').open,runRequests:window.__runRequests.slice(),runButton:!!document.querySelector('[data-task-run]')}))()`);
  const checks={dialogOpen:state.open,topLayerModal:state.modal,ariaModal:state.ariaModal==="true",whitePanel:state.panelBackground==="rgb(255, 255, 255)",opaquePanel:state.panelOpacity==="1",dimBackdrop:state.backdrop.includes("0.72"),backdropIntercepts:state.backdropPointerEvents!=="none",horizontallyCentered:Math.abs(state.centerX-state.viewportX)<=3,verticallyCentered:Math.abs(state.centerY-state.viewportY)<=3,clearAction:state.title==="运行同步任务"&&state.submit==="确认运行",focusInside:state.focused==="dc-action-confirm-submit",cancelClosed:!cancelled.open,noRunAfterCancel:cancelled.runRequests.length===baselineRuns&&cancelled.runButton,noExceptions:exceptions.length===0};
  if(Object.values(checks).some(value=>value!==true))throw new Error(JSON.stringify({checks,state,cancelled,exceptions},null,2));
  console.log(JSON.stringify({checks,state,cancelled},null,2));
}finally{await command("Page.close").catch(()=>{});socket.close()}
