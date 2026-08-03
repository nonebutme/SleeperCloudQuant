const baseUrl = process.argv[2] || "http://127.0.0.1:8020";
const debugUrl = process.argv[3] || "http://127.0.0.1:9225/json";
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
  if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params?.exceptionDetails?.text || "Runtime exception");
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
await command("Page.navigate", { url: baseUrl });
await wait(3500);
const desktop = await evaluate(`(() => ({
  title: document.querySelector("h1")?.textContent || "",
  sections: document.querySelectorAll(".studio-section").length,
  navItems: document.querySelectorAll("#section-nav [data-target]").length,
  datasetText: document.querySelector("#dataset-summary")?.textContent || "",
  manifestText: document.querySelector("#manifest-body")?.textContent || "",
  apiStatus: document.querySelector("#api-status")?.textContent || "",
  fallbackHref: document.querySelector('a[href="/?page=backtest"]')?.getAttribute("href") || "",
  sourceHash: document.querySelector("#source-hash")?.textContent || "",
  bodyWidth: document.body.clientWidth,
  scrollWidth: document.body.scrollWidth,
}))()`);
await evaluate(`document.querySelector('[data-target="code"]').click()`);
await wait(300);
const navigation = await evaluate(`(() => ({ active: document.querySelector("#section-nav .is-active")?.dataset.target || "", hashLength: document.querySelector("#source-hash")?.textContent.length || 0 }))()`);
await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
await wait(500);
const mobile = await evaluate(`(() => ({ bodyWidth: document.body.clientWidth, scrollWidth: document.body.scrollWidth, railWidth: document.querySelector(".studio-rail")?.clientWidth || 0 }))()`);

const checks = {
  title: desktop.title.includes("策略工作室"),
  manifestSections: desktop.sections >= 9 && desktop.navItems === 8,
  datasetCatalog: desktop.datasetText.includes("目录权威：数据中心"),
  manifestLibrary: desktop.manifestText.length > 0,
  apiConnected: desktop.apiStatus.includes("已连接"),
  fallbackPreserved: desktop.fallbackHref === "/?page=backtest",
  sourceHashed: desktop.sourceHash.length === 64 && navigation.hashLength === 64,
  navigation: navigation.active === "code",
  desktopNoOverflow: desktop.scrollWidth <= desktop.bodyWidth + 2,
  mobileNoOverflow: mobile.scrollWidth <= mobile.bodyWidth + 2,
  noRuntimeExceptions: exceptions.length === 0,
};
if (Object.values(checks).some((value) => value !== true)) {
  throw new Error(JSON.stringify({ checks, desktop, navigation, mobile, exceptions }, null, 2));
}
console.log(JSON.stringify({ checks, desktop, mobile }, null, 2));
socket.close();
