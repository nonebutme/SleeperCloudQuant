const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9222/json";
const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("no browser debugging page available");

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
await wait(5000);
await evaluate(`document.querySelector('[data-dc-view="assets"]').click()`);
await wait(5000);

const initial = await evaluate(`(() => ({
  active: document.querySelector(".dc-view.is-active")?.id,
  nodes: document.querySelectorAll("[data-m4-node]").length,
  title: document.querySelector("#dc-m4-title")?.textContent || "",
  unavailable: !document.querySelector('[data-m4-view="unavailable"]')?.hidden,
  panoramaOpen: document.querySelector("#dc-m4-panorama")?.open,
  candles: document.querySelectorAll("#a-share-daily-chart [data-kline-date]").length,
  ready: document.querySelector("#dc-m4-availability")?.textContent || "",
  bodyWidth: document.body.clientWidth,
  scrollWidth: document.body.scrollWidth,
  legacyDrawer: document.body.textContent.includes("A 股数据基座与兼容工具"),
  legacyForm: Boolean(document.querySelector("#market-query-form")),
}))()`);

await evaluate(`document.querySelector('[data-m4-title="沪深 A 股"]').click()`);
await wait(3000);
const list = await evaluate(`(() => ({
  visible: !document.querySelector('[data-m4-view="list"]')?.hidden,
  rows: document.querySelectorAll("#a-share-symbol-body tr").length,
  vtables: document.querySelectorAll('[data-vtable-enhanced="true"]').length,
  emptyText: document.querySelector("#a-share-symbol-body")?.textContent || "",
}))()`);

const firstSymbol = await evaluate(`document.querySelector("[data-a-share-symbol]")?.dataset.aShareSymbol || ""`);
if (firstSymbol) {
  await evaluate(`document.querySelector("[data-a-share-symbol]").click()`);
  await wait(3000);
}
const chart = await evaluate(`(() => ({
  visible: !document.querySelector('[data-m4-view="chart"]')?.hidden,
  candles: document.querySelectorAll("#a-share-daily-chart [data-kline-date]").length,
  svg: Boolean(document.querySelector("#a-share-daily-chart svg")),
  title: document.querySelector("#dc-m4-title")?.textContent || "",
}))()`);
if (chart.candles) {
  await evaluate(`document.querySelector("#a-share-daily-chart [data-kline-date]").dispatchEvent(new MouseEvent("click", { bubbles: true }))`);
  await wait(300);
}
await evaluate(`document.querySelector("#dc-m4-frequency").value = "weekly"; document.querySelector("#dc-m4-frequency").dispatchEvent(new Event("change", { bubbles: true }))`);
await wait(200);
const weekly = await evaluate(`(() => ({ candles: document.querySelectorAll("#a-share-daily-chart [data-kline-date]").length, period: document.querySelector("#dc-m4-chart-period")?.textContent || "" }))()`);

const panorama = await evaluate(`(() => ({
  open: document.querySelector("#dc-m4-panorama")?.open,
  date: document.querySelector("#dc-m4-panorama-date")?.textContent || "",
  cards: document.querySelectorAll(".dc-m4-panorama-card").length,
}))()`);

await evaluate(`document.querySelector("#dc-m4-search").value = "MSCI"; document.querySelector("#dc-m4-search").dispatchEvent(new Event("input", { bubbles: true }))`);
const search = await evaluate(`(() => ({
  visibleNodes: Array.from(document.querySelectorAll("[data-m4-node]")).filter((node) => !node.hidden).length,
  text: Array.from(document.querySelectorAll("[data-m4-node]")).filter((node) => !node.hidden).map((node) => node.textContent).join(" "),
}))()`);

await command("Emulation.setDeviceMetricsOverride", { width: 741, height: 900, deviceScaleFactor: 1, mobile: false });
await wait(300);
const narrow = await evaluate(`(() => ({ bodyWidth: document.body.clientWidth, scrollWidth: document.body.scrollWidth }))()`);

await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await evaluate(`document.querySelector('[data-dc-view="overview"]').click()`);
await wait(3000);
const overview = await evaluate(`(() => ({
  active: document.querySelector(".dc-view.is-active")?.id,
  source: document.querySelector("#a-share-source-state")?.textContent || "",
  cards: document.querySelectorAll("#a-share-overview .summary-item").length,
  rows: document.querySelectorAll("#a-share-adjustment-body tr").length,
  legacyDrawer: document.body.textContent.includes("A 股数据基座与兼容工具"),
}))()`);

const checks = {
  m4Active: initial.active === "dc-view-assets",
  legacyCompatibilityRemoved: !initial.legacyDrawer && !initial.legacyForm,
  m0BaseOverviewWorks: overview.active === "dc-view-overview" && overview.source.length > 0 && overview.cards >= 6 && overview.rows >= 3 && !overview.legacyDrawer,
  treeComplete: initial.nodes >= 25,
  governedIndexDefault: initial.title.includes("沪深300") && !initial.unavailable && initial.candles > 0 && initial.ready.includes("可查询"),
  panoramaInitiallyCollapsed: initial.panoramaOpen === false,
  listWorks: list.visible && (list.rows > 0 || list.emptyText.length > 0),
  vtableActive: list.vtables >= 1,
  chartWorksWhenDataExists: !firstSymbol || (chart.visible && chart.svg && chart.candles > 0),
  panoramaDrilldown: !chart.candles || (panorama.open && panorama.cards === 5 && panorama.date.length > 0),
  periodFilter: !chart.candles || (weekly.candles > 0 && weekly.candles < chart.candles && weekly.period.includes("周线")),
  searchWorks: search.visibleNodes === 2 && search.text.includes("MSCI全球") && search.text.includes("MSCI新兴"),
  desktopNoOverflow: initial.scrollWidth <= initial.bodyWidth + 2,
  narrowNoOverflow: narrow.scrollWidth <= narrow.bodyWidth + 2,
  noRuntimeExceptions: exceptions.length === 0,
};
if (Object.values(checks).some((value) => value !== true)) {
  throw new Error(JSON.stringify({ checks, initial, list, firstSymbol, chart, weekly, panorama, search, narrow, overview, exceptions }, null, 2));
}
console.log(JSON.stringify({ checks, initial, list, chart, weekly, panorama, search, narrow, overview }, null, 2));
socket.close();
