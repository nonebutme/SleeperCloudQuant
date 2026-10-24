const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9233/json";
const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("no debugging page available");

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
  if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params?.exceptionDetails?.text || "runtime exception");
});
function command(method, params = {}) {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
async function evaluate(expression) {
  const result = await command("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function waitFor(expression, label, timeout = 15000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(expression)) return;
    await wait(150);
  }
  throw new Error(`timeout waiting for ${label}`);
}

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: `${baseUrl}/?page=factor&factor_view=dashboard` });
await waitFor(`document.readyState === "complete" && document.documentElement.classList.contains("quant-ui-standard")`, "quant UI page ready");
await wait(500);

const desktop = await evaluate(`(() => {
  document.querySelector('[data-page="factor"]').click();
  const top = [...document.querySelectorAll('.nav-tabs > .nav-tab')];
  const submenu = document.querySelector('[data-nav-submenu="factor"]');
  const children = [...submenu.querySelectorAll(':scope > button')];
  const style = (node) => getComputedStyle(node);
  return {
    topCount: top.length,
    topLabels: top.map((node) => node.textContent.trim()),
    topGroups: top.map((node) => node.dataset.navGroup),
    topHeights: [...new Set(top.map((node) => Math.round(node.getBoundingClientRect().height)))],
    topFonts: [...new Set(top.map((node) => style(node).fontSize))],
    topRadii: [...new Set(top.map((node) => style(node).borderRadius))],
    activeTop: top.filter((node) => node.classList.contains('is-active')).length,
    expanded: document.querySelector('[data-page="factor"]').getAttribute('aria-expanded'),
    visibleSubmenus: [...document.querySelectorAll('[data-nav-submenu]')].filter((node) => !node.hidden).length,
    childCount: children.length,
    childHeights: [...new Set(children.map((node) => Math.round(node.getBoundingClientRect().height)))],
    childFonts: [...new Set(children.map((node) => style(node).fontSize))],
    childRadii: [...new Set(children.map((node) => style(node).borderRadius))],
    childColumns: style(submenu).gridTemplateColumns.split(' ').length,
    sidebarWidth: Math.round(document.querySelector('.sidebar').getBoundingClientRect().width),
  };
})()`);

const flows = await evaluate(`(async () => {
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const waitUntil = async (predicate, timeout = 15000) => {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      if (predicate()) return true;
      await pause(150);
    }
    return false;
  };
  const activeGroup = () => document.querySelector('.nav-tab.is-active')?.dataset.navGroup || '';
  document.querySelector('.nav-tab[data-nav-group="datasets"]').click();
  await waitUntil(() => document.querySelectorAll('[data-sd-dataset]').length > 0);
  document.querySelector('[data-strategy-dataset-view="detail"]').click();
  await waitUntil(() => !document.querySelector('#sd-detail-view')?.hidden);
  const datasets = {
    group: activeGroup(),
    detailVisible: !document.querySelector('#sd-detail-view')?.hidden,
    child: document.querySelector('[data-strategy-dataset-view].is-active')?.dataset.strategyDatasetView,
    title: document.querySelector('#page-title')?.textContent,
  };

  document.querySelector('.nav-tab[data-nav-group="market-data"]').click();
  await pause(400);
  document.querySelector('[data-market-category="行业板块"]').click();
  await pause(300);
  const marketData = {
    group: activeGroup(),
    title: document.querySelector('#page-title')?.textContent,
    assetView: document.querySelector('#dc-view-assets')?.classList.contains('is-active'),
    category: document.querySelector('[data-market-category].is-active')?.dataset.marketCategory,
    assetTitle: document.querySelector('#dc-m4-title')?.textContent,
  };

  document.querySelector('.nav-tab[data-nav-group="market"]').click();
  document.querySelector('[data-nav-submenu="market"] [data-dc-view="routes"]').click();
  await pause(500);
  const dataCenter = {
    group: activeGroup(),
    routes: document.querySelector('#dc-view-routes')?.classList.contains('is-active'),
    child: document.querySelector('[data-nav-submenu="market"] [data-dc-view].is-active')?.dataset.dcView,
  };

  document.querySelector('.nav-tab[data-nav-group="backtest"]').click();
  document.querySelector('[data-stage76-workspace="results"]').click();
  await pause(900);
  const backtest = {
    group: activeGroup(),
    child: document.querySelector('[data-stage76-workspace].is-active')?.dataset.stage76Workspace,
    taskPanelVisible: !document.querySelector('#stage76-task-workbench')?.hidden,
  };

  document.querySelector('[data-nav-context="backtest"]').click();
  await pause(250);
  const backtestAnalysis = {
    group: activeGroup(),
    pageVisible: document.querySelector('#page-reporting')?.classList.contains('is-active'),
    childActive: document.querySelector('[data-nav-context="backtest"]')?.classList.contains('is-active'),
  };

  document.querySelector('.nav-tab[data-nav-group="reporting"]').click();
  document.querySelector('[data-nav-submenu="reporting"] [data-route-page="report-management"]').click();
  await pause(250);
  const reporting = {
    group: activeGroup(),
    pageVisible: document.querySelector('#page-report-management')?.classList.contains('is-active'),
  };

  document.querySelector('.nav-tab[data-nav-group="config"]').click();
  await pause(150);
  const settings = {
    group: activeGroup(),
    pageVisible: document.querySelector('#page-config')?.classList.contains('is-active'),
  };
  return { marketData, dataCenter, datasets, backtest, backtestAnalysis, reporting, settings };
})()`);

await command("Page.navigate", { url: `${baseUrl}/?page=market&dc_view=assets&market_tab=${encodeURIComponent("行业板块")}` });
await waitFor(`document.readyState === "complete" && document.documentElement.classList.contains("quant-ui-standard")`, "market data reload");
await waitFor(`document.querySelector('[data-market-category].is-active')?.dataset.marketCategory === "行业板块"`, "market data category restored");
const marketReload = await evaluate(`(() => ({
  group: document.querySelector('.nav-tab.is-active')?.dataset.navGroup,
  submenuVisible: !document.querySelector('[data-nav-submenu="market-data"]')?.hidden,
  category: document.querySelector('[data-market-category].is-active')?.dataset.marketCategory,
  title: document.querySelector('#page-title')?.textContent,
}))()`);
await evaluate(`document.querySelector('[data-page="factor"]').click()`);

await command("Emulation.setDeviceMetricsOverride", { width: 741, height: 900, deviceScaleFactor: 1, mobile: false });
await wait(700);
const narrow = await evaluate(`(() => ({
  bodyWidth: document.body.clientWidth,
  scrollWidth: document.body.scrollWidth,
  navColumns: getComputedStyle(document.querySelector('.nav-tabs')).gridTemplateColumns.split(' ').length,
  submenuColumns: getComputedStyle(document.querySelector('[data-nav-submenu="factor"]')).gridTemplateColumns.split(' ').length,
}))()`);

const checks = {
  eightTopLevels: desktop.topCount === 8,
  approvedOrder: desktop.topLabels.join("|") === "市场数据|数据中心|数据集|因子分析|策略回测|工作台|报告与复盘|系统设置",
  approvedGroups: desktop.topGroups.join("|") === "market-data|market|datasets|factor|backtest|dashboard|reporting|config",
  marketDataFlow: flows.marketData.group === "market-data" && flows.marketData.assetView === true && flows.marketData.category === "行业板块" && flows.marketData.assetTitle === "行业板块",
  dataCenterFlow: flows.dataCenter.group === "market" && flows.dataCenter.routes === true && flows.dataCenter.child === "routes",
  datasetDetailFlow: flows.datasets.group === "datasets" && flows.datasets.detailVisible === true && flows.datasets.child === "detail" && flows.datasets.title === "数据集详情",
  backtestResultFlow: flows.backtest.group === "backtest" && flows.backtest.child === "results" && flows.backtest.taskPanelVisible === true,
  backtestAnalysisFlow: flows.backtestAnalysis.group === "backtest" && flows.backtestAnalysis.pageVisible === true && flows.backtestAnalysis.childActive === true,
  reportingFlow: flows.reporting.group === "reporting" && flows.reporting.pageVisible === true,
  settingsFlow: flows.settings.group === "config" && flows.settings.pageVisible === true,
  marketDataReload: marketReload.group === "market-data" && marketReload.submenuVisible === true && marketReload.category === "行业板块" && marketReload.title === "市场数据 · 行业板块",
  desktopGeometry: String(desktop.topHeights) === "40" && String(desktop.topFonts) === "14px" && String(desktop.topRadii) === "4px",
  singleActiveGroup: desktop.activeTop === 1 && desktop.expanded === "true" && desktop.visibleSubmenus === 1,
  factorSubmenu: desktop.childCount === 7 && String(desktop.childHeights) === "32" && String(desktop.childFonts) === "12px" && String(desktop.childRadii) === "4px",
  sidebarStandard: desktop.sidebarWidth === 256,
  narrowLayout: narrow.navColumns === 3 && narrow.submenuColumns === 3 && narrow.scrollWidth <= narrow.bodyWidth + 2,
  noRuntimeExceptions: exceptions.length === 0,
};
if (Object.values(checks).some((value) => value !== true)) throw new Error(JSON.stringify({ checks, desktop, flows, marketReload, narrow, exceptions }, null, 2));
console.log(JSON.stringify({ checks, desktop, flows, marketReload, narrow }, null, 2));
socket.close();
