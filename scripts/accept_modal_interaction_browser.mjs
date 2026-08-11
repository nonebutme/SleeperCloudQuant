const baseUrl=process.argv[2]||"http://127.0.0.1:8010";
const debugUrl=process.argv[3]||"http://127.0.0.1:9224/json";
const debugOrigin=new URL(debugUrl).origin;
const target=await fetch(`${debugOrigin}/json/new?${encodeURIComponent("about:blank")}`,{method:"PUT"}).then(r=>r.json());
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener("open",resolve,{once:true});socket.addEventListener("error",reject,{once:true})});
let sequence=0;const pending=new Map(),exceptions=[];
socket.addEventListener("message",event=>{const message=JSON.parse(String(event.data));if(message.id&&pending.has(message.id)){const request=pending.get(message.id);pending.delete(message.id);message.error?request.reject(new Error(JSON.stringify(message.error))):request.resolve(message.result||{})}if(message.method==="Runtime.exceptionThrown")exceptions.push(message.params?.exceptionDetails?.exception?.description||message.params?.exceptionDetails?.text||"Runtime exception")});
const command=(method,params={})=>{const id=++sequence;socket.send(JSON.stringify({id,method,params}));return new Promise((resolve,reject)=>pending.set(id,{resolve,reject}))};
const evaluate=async(expression,awaitPromise=false)=>{const response=await command("Runtime.evaluate",{expression,awaitPromise,returnByValue:true});if(response.exceptionDetails)throw new Error(JSON.stringify(response.exceptionDetails));return response.result?.value};
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
try{
  await command("Page.enable");await command("Runtime.enable");
  await command("Emulation.setDeviceMetricsOverride",{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await command("Page.navigate",{url:`${baseUrl}/?page=market&dc_view=sync`});await wait(6500);
  const available=await evaluate(`!!document.querySelector('[data-task-detail]')`);
  if(!available)throw new Error(JSON.stringify({phase:"detail-button",exceptions}));
  await evaluate(`document.documentElement.setAttribute('data-theme','dark');document.querySelector('[data-task-detail]').click()`);await wait(1200);
  const state=await evaluate(`(()=>{const dialog=document.querySelector('#dc-sync-task-dialog'),panel=getComputedStyle(dialog),backdrop=getComputedStyle(dialog,'::backdrop'),background=document.querySelector('#dc-view-sync');return{open:dialog?.open===true,modal:dialog?.matches(':modal')===true,ariaModal:dialog?.getAttribute('aria-modal'),panelBackground:panel.backgroundColor,panelColor:panel.color,panelOpacity:panel.opacity,backdrop:backdrop.backgroundColor,backdropPointerEvents:backdrop.pointerEvents,backgroundPointerEvents:getComputedStyle(background).pointerEvents,detailText:document.querySelector('#dc-sync-task-detail')?.textContent?.trim().slice(0,120)||'',busy:document.querySelector('#dc-sync-task-detail')?.getAttribute('aria-busy')}})()`);
  const checks={dialogOpen:state.open,topLayerModal:state.modal,ariaModal:state.ariaModal==="true",whitePanel:state.panelBackground==="rgb(255, 255, 255)",opaquePanel:state.panelOpacity==="1",dimBackdrop:state.backdrop.includes("0.68"),backdropIntercepts:state.backdropPointerEvents!=="none",detailRendered:state.detailText.length>0&&!state.busy,noExceptions:exceptions.length===0};
  if(Object.values(checks).some(value=>value!==true))throw new Error(JSON.stringify({checks,state,exceptions},null,2));
  console.log(JSON.stringify({checks,state},null,2));
}finally{await command("Page.close").catch(()=>{});socket.close()}
