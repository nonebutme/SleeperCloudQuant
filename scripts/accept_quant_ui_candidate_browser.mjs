import fs from "node:fs";
import path from "node:path";

const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9233/json";
const outputDir = process.argv[4] || "tmp";
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
async function screenshot(name) {
  const result = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  fs.mkdirSync(outputDir, { recursive: true });
  fs.writeFileSync(path.join(outputDir, name), Buffer.from(result.data, "base64"));
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: `${baseUrl}/?page=dashboard` });
await wait(8000);
if (await evaluate(`document.documentElement.dataset.theme === "dark"`)) {
  await evaluate(`document.querySelector(".quant-ui-theme-toggle").click()`);
  await wait(1200);
}

const light = await evaluate(`(() => {
  const root = document.documentElement;
  const sidebar = document.querySelector(".sidebar");
  const panel = document.querySelector(".panel");
  const button = document.querySelector(".workflow-strip button");
  const metrics = Array.from(document.querySelectorAll("#dashboard-metrics .summary-item"));
  return {
    candidate: root.classList.contains("quant-ui-standard"),
    theme: root.dataset.theme,
    bodyBg: getComputedStyle(document.body).backgroundColor,
    sidebarWidth: Math.round(sidebar.getBoundingClientRect().width),
    panelRadius: getComputedStyle(panel).borderRadius,
    buttonHeight: Math.round(button.getBoundingClientRect().height),
    metricCount: metrics.length,
    metricMinHeight: Math.min(...metrics.map((item) => Math.round(item.getBoundingClientRect().height))),
    reviewBadge: document.querySelector(".quant-ui-standard-badge")?.textContent || "",
    themeButton: document.querySelector(".quant-ui-theme-toggle")?.textContent || "",
    bodyWidth: document.body.clientWidth,
    scrollWidth: document.body.scrollWidth,
  };
})()`);
await screenshot("quant-ui-standard-dashboard-light.png");

await evaluate(`document.querySelector('[data-page="market"]').click()`);
await wait(1500);
await evaluate(`document.querySelector('[data-dc-view="assets"]').click()`);
await wait(2500);
const market = await evaluate(`(() => ({
  active: document.querySelector("#dc-view-assets")?.classList.contains("is-active"),
  tables: document.querySelectorAll("#dc-view-assets table").length,
  vtables: document.querySelectorAll('#dc-view-assets .app-vtable-host[data-vtable-mode="market"]').length,
  canvases: document.querySelectorAll("#dc-view-assets .app-vtable-host canvas").length,
}))()`);

await evaluate(`document.querySelector(".quant-ui-theme-toggle").click()`);
await wait(1600);
const dark = await evaluate(`(() => ({
  theme: document.documentElement.dataset.theme,
  bodyBg: getComputedStyle(document.body).backgroundColor,
  cardBg: getComputedStyle(document.querySelector("#dc-view-assets .panel")).backgroundColor,
  canvases: document.querySelectorAll("#dc-view-assets .app-vtable-host canvas").length,
  buttonText: document.querySelector(".quant-ui-theme-toggle")?.textContent || "",
}))()`);
await screenshot("quant-ui-standard-market-dark.png");

await evaluate(`document.querySelector(".quant-ui-theme-toggle").click()`);
await wait(1000);
const pageAudit = await evaluate(`(async () => {
  const results = [];
  for (const page of ["dashboard", "backtest", "reporting", "config", "factor"]) {
    document.querySelector('[data-page="' + page + '"]').click();
    await new Promise((resolve) => setTimeout(resolve, 350));
    const section = document.querySelector("#page-" + page);
    results.push({
      page,
      active: section?.classList.contains("is-active"),
      panels: section?.querySelectorAll(".panel").length || 0,
      width: section ? Math.round(section.getBoundingClientRect().width) : 0,
      scrollWidth: section?.scrollWidth || 0,
    });
  }
  return results;
})()`);
await screenshot("quant-ui-standard-factor-light.png");

await command("Emulation.setDeviceMetricsOverride", { width: 741, height: 900, deviceScaleFactor: 1, mobile: false });
await wait(1000);
const narrow = await evaluate(`(() => ({
  bodyWidth: document.body.clientWidth,
  scrollWidth: document.body.scrollWidth,
  navColumns: getComputedStyle(document.querySelector(".nav-tabs")).gridTemplateColumns.split(" ").length,
  themeButtonVisible: document.querySelector(".quant-ui-theme-toggle")?.getBoundingClientRect().height > 0,
}))()`);

const checks = {
  candidateMounted: light.candidate,
  lightTheme: light.theme === "light" && light.bodyBg === "rgb(242, 243, 245)",
  sidebar256: light.sidebarWidth === 256,
  atomicGeometry: light.panelRadius === "6px" && light.buttonHeight === 32,
  metricCards: light.metricCount >= 4 && light.metricCount % 4 === 0 && light.metricMinHeight >= 120,
  globalStandardVisible: light.reviewBadge.includes("全局生效"),
  marketVTableMode: market.active && market.tables >= 3 && market.vtables === market.tables && market.canvases >= market.tables,
  darkTheme: dark.theme === "dark" && dark.bodyBg === "rgb(23, 23, 26)" && dark.cardBg === "rgb(35, 35, 36)",
  darkVTablesRecreated: dark.canvases >= market.tables,
  corePagesStyled: pageAudit.every((item) => item.active && item.panels >= 1 && item.scrollWidth <= item.width + 2),
  narrowNoPageOverflow: narrow.scrollWidth <= narrow.bodyWidth + 2,
  narrowControlsVisible: narrow.themeButtonVisible && narrow.navColumns >= 2,
  noRuntimeExceptions: exceptions.length === 0,
};
if (Object.values(checks).some((value) => value !== true)) {
  throw new Error(JSON.stringify({ checks, light, market, dark, pageAudit, narrow, exceptions }, null, 2));
}
console.log(JSON.stringify({ checks, light, market, dark, pageAudit, narrow }, null, 2));
socket.close();
