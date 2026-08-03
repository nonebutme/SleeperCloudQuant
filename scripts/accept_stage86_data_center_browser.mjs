const baseUrl = process.argv[2] || "http://127.0.0.1:8019";
const debugUrl = process.argv[3] || "http://127.0.0.1:9224/json";
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
    exceptions.push(message.params?.exceptionDetails?.text || "Runtime exception");
  }
});
function command(method, params = {}) {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
async function evaluate(expression, awaitPromise = false) {
  const response = await command("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: `${baseUrl}/?page=market` });
await wait(8000);

const desktop = await evaluate(`(() => ({
  tabs: document.querySelectorAll("[data-dc-view]").length,
  active: document.querySelector(".dc-view.is-active")?.id,
  metrics: document.querySelectorAll("#dc-overview-metrics > *").length,
  version: document.querySelector("#dc-default-version")?.textContent || "",
  health: document.querySelector("#dc-health")?.textContent || "",
  sidebarItems: document.querySelectorAll(".dc-sidebar-subnav [data-dc-view]").length,
  topSubnav: document.querySelectorAll(".dc-subnav").length,
  globalStatusItems: document.querySelectorAll(".dc-global-status span").length,
  globalStatusText: document.querySelector(".dc-global-status")?.textContent || "",
  bodyWidth: document.body.clientWidth,
  scrollWidth: document.body.scrollWidth,
}))()`);

await evaluate(`document.querySelector('[data-dc-view="routes"]').click()`);
await wait(1200);
const routes = await evaluate(`(() => ({
  active: document.querySelector(".dc-view.is-active")?.id,
  entries: document.querySelectorAll("#dc-route-list tbody tr").length || document.querySelectorAll("#dc-route-list .app-vtable-host").length,
  text: document.querySelector("#dc-route-list")?.textContent || "",
}))()`);
await evaluate(`document.querySelector('[data-dc-view="sync"]').click()`);
await wait(600);
await evaluate(`document.querySelector("#dc-sync-form").requestSubmit()`);
await wait(1500);
const preview = await evaluate(`(() => ({
  active: document.querySelector(".dc-view.is-active")?.id,
  text: document.querySelector("#dc-sync-preview-output")?.textContent || "",
  taskText: document.querySelector("#dc-sync-task-list")?.textContent || "",
}))()`);
await evaluate(`document.querySelector('[data-dc-view="quality"]').click()`);
await wait(800);
const quality = await evaluate(`(() => ({ active: document.querySelector(".dc-view.is-active")?.id, text: document.querySelector("#dc-quality-list")?.textContent || "" }))()`);
await evaluate(`document.querySelector('[data-dc-view="versions"]').click()`);
await wait(800);
const versions = await evaluate(`(() => ({ active: document.querySelector(".dc-view.is-active")?.id, cards: document.querySelectorAll("#dc-version-list tbody tr").length, text: document.querySelector("#dc-version-list")?.textContent || "" }))()`);

await command("Emulation.setDeviceMetricsOverride", { width: 741, height: 900, deviceScaleFactor: 1, mobile: false });
await wait(500);
const narrow = await evaluate(`(() => ({
  bodyWidth: document.body.clientWidth,
  scrollWidth: document.body.scrollWidth,
  sidebarMenuVisible: document.querySelectorAll(".dc-sidebar-subnav [data-dc-view]").length === 6,
  active: document.querySelector(".dc-view.is-active")?.id,
}))()`);

const checks = {
  sixViews: desktop.tabs === 6,
  overviewActive: desktop.active === "dc-view-overview",
  overviewLoaded: desktop.metrics >= 4 && desktop.version.includes("scq-"),
  healthVisible: desktop.health.length > 0 && !desktop.health.includes("读取中"),
  sidebarTree: desktop.sidebarItems === 6 && desktop.topSubnav === 0,
  globalStatus: desktop.globalStatusItems === 3 && desktop.globalStatusText.length > 10,
  routesLoaded: routes.active === "dc-view-routes" && routes.entries >= 1 && routes.text.includes("stock_info_a_code_name"),
  syncLoaded: preview.taskText.length > 0,
  previewIsReadOnly: preview.active === "dc-view-sync" && preview.text.length > 0,
  qualityLoaded: quality.active === "dc-view-quality" && quality.text.length > 0,
  versionsLoaded: versions.active === "dc-view-versions" && versions.cards >= 1 && versions.text.length > 0,
  desktopNoOverflow: desktop.scrollWidth <= desktop.bodyWidth + 2,
  narrowNoOverflow: narrow.scrollWidth <= narrow.bodyWidth + 2,
  narrowSidebarTree: narrow.sidebarMenuVisible,
  noRuntimeExceptions: exceptions.length === 0,
};
if (Object.values(checks).some((value) => value !== true)) {
  throw new Error(JSON.stringify({ checks, desktop, routes, preview, quality, versions, narrow, exceptions }, null, 2));
}
console.log(JSON.stringify({ checks, desktop, narrow }, null, 2));
socket.close();
