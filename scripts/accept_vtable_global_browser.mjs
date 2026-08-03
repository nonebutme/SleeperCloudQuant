const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9231/json";
const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("no Edge debugging page available");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
let sequence = 0;
const pending = new Map();
const exceptions = [];
socket.addEventListener("message", (event) => {
  const message = JSON.parse(String(event.data));
  if (message.id && pending.has(message.id)) {
    const item = pending.get(message.id);
    pending.delete(message.id);
    message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result || {});
  }
  if (message.method === "Runtime.exceptionThrown") {
    exceptions.push(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text || "Runtime exception");
  }
});
function command(method, params = {}) {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
async function evaluate(expression) {
  const response = await command("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: `${baseUrl}/?page=market` });
await wait(8000);

await evaluate(`document.querySelector('[data-dc-view="assets"]').click()`);
await wait(2500);
const assets = await evaluate(`(() => {
  const view = document.querySelector("#dc-view-assets");
  return {
    active: view?.classList.contains("is-active"),
    tables: view?.querySelectorAll("table").length || 0,
    enhanced: view?.querySelectorAll(".app-vtable-host").length || 0,
    canvases: view?.querySelectorAll(".app-vtable-host canvas").length || 0,
    visibleTables: Array.from(view?.querySelectorAll("table") || []).filter((table) => table.getClientRects().length > 0).length,
    visibleHosts: Array.from(view?.querySelectorAll(".app-vtable-host") || []).filter((host) => host.getClientRects().length > 0).length,
    visibleNative: Array.from(view?.querySelectorAll("table") || []).filter((table) => table.getClientRects().length > 0 && !table.classList.contains("app-vtable-source")).length,
  };
})()`);

await evaluate(`document.querySelector('[data-dc-view="quality"]').click()`);
await wait(1800);
const quality = await evaluate(`(() => {
  const view = document.querySelector("#dc-view-quality");
  return {
    tables: view?.querySelectorAll("table").length || 0,
    enhanced: view?.querySelectorAll(".app-vtable-host").length || 0,
    canvases: view?.querySelectorAll(".app-vtable-host canvas").length || 0,
    sourceActions: view?.querySelectorAll(".app-vtable-source button").length || 0,
  };
})()`);

await evaluate(`(() => {
  const probe = document.createElement("div");
  probe.id = "vtable-runtime-probe";
  probe.className = "table-wrap";
  probe.innerHTML = '<table><thead><tr><th>名称</th><th>操作</th></tr></thead><tbody><tr><td>动态行一</td><td><button type="button">确认</button><button type="button">隔离</button></td></tr><tr><td>动态行二</td><td>—</td></tr></tbody></table>';
  document.querySelector("main").append(probe);
})()`);
await wait(1200);
await evaluate(`document.querySelector("#vtable-runtime-probe tbody").insertAdjacentHTML("beforeend", "<tr><td>动态行三</td><td>—</td></tr><tr><td>动态行四</td><td>—</td></tr><tr><td>动态行五</td><td>—</td></tr><tr><td>动态行六</td><td>—</td></tr>")`);
await wait(1200);
const dynamic = await evaluate(`(() => {
  const probe = document.querySelector("#vtable-runtime-probe");
  const table = probe?.querySelector("table");
  return {
    sourceEnhanced: table?.classList.contains("app-vtable-source"),
    hosts: probe?.querySelectorAll(".app-vtable-host").length || 0,
    canvases: probe?.querySelectorAll("canvas").length || 0,
    hostHeight: probe?.querySelector(".app-vtable-host")?.getBoundingClientRect().height || 0,
    actionCount: table?.querySelectorAll("button").length || 0,
    version: window.AppVTable?.version,
    instanceCount: window.AppVTable?.instanceCount?.(),
    globalReady: Boolean(window.VTable?.ListTable),
  };
})()`);

const checks = {
  vtableGlobalReady: dynamic.globalReady && dynamic.version === "1.23.1",
  assetsActive: assets.active,
  assetsFullyEnhanced: assets.visibleTables >= 1 && assets.visibleHosts >= assets.visibleTables && assets.canvases >= assets.visibleTables,
  noVisibleNativeTables: assets.visibleNative === 0,
  qualityEmptyOrEnhanced: quality.tables === 0 || (quality.enhanced === quality.tables && quality.canvases >= quality.tables),
  qualityActionsPreservedWhenPresent: quality.sourceActions === 0 || quality.enhanced >= 1,
  runtimeMutationEnhanced: dynamic.sourceEnhanced && dynamic.hosts === 1 && dynamic.canvases >= 1 && dynamic.hostHeight > 200,
  multipleActionsPreserved: dynamic.actionCount === 2,
  instancesRegistered: dynamic.instanceCount >= assets.enhanced + 1,
  noRuntimeExceptions: exceptions.length === 0,
};
if (Object.values(checks).some((value) => value !== true)) {
  throw new Error(JSON.stringify({ checks, assets, quality, dynamic, exceptions }, null, 2));
}
console.log(JSON.stringify({ checks, assets, quality, dynamic }, null, 2));
socket.close();
