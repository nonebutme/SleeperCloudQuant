const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9226/json";
const symbols = "000001,600000,000333,600519,300750,601318,000858,600036";
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
  if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params?.exceptionDetails?.exception?.description || "Runtime exception");
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
async function waitFor(expression, label, timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const value = await evaluate(expression);
      if (value) return value;
    } catch (_) {}
    await wait(300);
  }
  throw new Error(`timeout waiting for ${label}`);
}
async function click(selector) {
  const found = await evaluate(`(() => { const node=document.querySelector(${JSON.stringify(selector)}); if(!node)return false; node.click(); return true; })()`);
  if (!found) throw new Error(`missing ${selector}`);
}
async function setValue(selector, value, eventName = "input") {
  const found = await evaluate(`(() => { const node=document.querySelector(${JSON.stringify(selector)}); if(!node)return false; node.value=${JSON.stringify(value)}; node.dispatchEvent(new Event(${JSON.stringify(eventName)},{bubbles:true})); return true; })()`);
  if (!found) throw new Error(`missing ${selector}`);
}
async function api(path) {
  const response = await fetch(new URL(path, baseUrl));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${path}: ${response.status} ${JSON.stringify(payload)}`);
  return payload;
}

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: `${baseUrl}/?page=backtest&workspace=strategy&accept=fujing-v2-portfolio-${Date.now()}` });
await waitFor(`document.querySelector('[data-strategy-id="fujing_v2"]') !== null`, "fujing strategy");
await click('[data-strategy-id="fujing_v2"]');
await waitFor(`selectedStrategy?.strategy_id === "fujing_v2"`, "strategy selected");
await click('[data-stage76-workspace="create"]');
await click('[data-stage76-mode="portfolio"]');
await setValue("#backtest-common-start", "2020-01-01");
await setValue("#backtest-common-end", "2026-07-24");
await setValue("#backtest-common-adjustment", "raw", "change");
await setValue("#backtest-common-cash", "1000000");
await click("#backtest-common-apply");
await setValue('#portfolio-task-form [name="symbols"]', symbols);
await setValue('#portfolio-task-form [name="symbol_limit"]', "8");
await setValue('#portfolio-task-form [name="max_positions"]', "3");
await setValue('#portfolio-task-form [name="portfolio_exposure"]', "1");
await setValue('#portfolio-task-form [name="max_workers"]', "4");
const previousId = await evaluate(`currentPortfolioTaskId || ""`);
await click('#portfolio-task-form button[type="submit"]');
const taskId = await waitFor(`(() => currentPortfolioTaskId && currentPortfolioTaskId !== ${JSON.stringify(previousId)} ? currentPortfolioTaskId : "")()`, "portfolio task created");
await click("#portfolio-task-run");

let task = null;
const deadline = Date.now() + 240000;
while (Date.now() < deadline) {
  task = (await api(`/api/backtest/shared-portfolio-tasks/${encodeURIComponent(taskId)}`)).task;
  if (["completed", "failed", "partial_completed", "partial_failed"].includes(task.status)) break;
  await wait(1000);
}
if (!task || task.status !== "completed") throw new Error(`portfolio ended as ${task?.status}: ${task?.error_message || "unknown"}`);

const action = '[data-stage76-form-action][data-stage76-action-mode="portfolio"]';
await waitFor(`(() => { const node=document.querySelector(${JSON.stringify(action)}); return Boolean(node && !node.disabled); })()`, "portfolio analysis enabled", 30000);
await click(action);
await waitFor(`(() => { const run=stage76CurrentResult?.run_id || stage76CurrentResult?.summary?.run_id; return stage76SelectedTask?.mode === "shared-portfolio" && run === stage76SelectedTask.run_id; })()`, "portfolio result context");
await waitFor(`(() => { const node=document.querySelector("#report-result-overview"); return Boolean(node && node.innerText.length > 80 && !node.innerText.includes("正在加载专业报告")); })()`, "portfolio report");

const evidence = await evaluate(`(() => {
  const result=stage76CurrentResult || {};
  const trades=result.trades || [];
  const pingAn=trades.filter((trade)=>String(trade.order_book_id).startsWith("000001"));
  return {
    run_id:result.run_id || result.summary?.run_id,
    summary:result.summary || {},
    metrics:result.metrics || {},
    trade_count:trades.length,
    execution_modes:[...new Set(trades.map((trade)=>trade.notes?.execution_price_mode).filter(Boolean))],
    symbols:[...new Set(trades.map((trade)=>trade.order_book_id))],
    ping_an_prices:pingAn.map((trade)=>trade.price),
    first_trade:trades[0] || null,
    report_text:(document.querySelector("#report-result-overview")?.innerText || "").slice(0,1000),
  };
})()`);
const checks = {
  completed: task.status === "completed",
  correctRun: evidence.run_id === task.run_id,
  sharedEightStocks: evidence.summary.universe === "shared:8 A-shares",
  topThree: Number(task.config?.max_positions) === 3 && Number(evidence.metrics?.max_positions) === 3,
  openExecution: evidence.execution_modes.length === 1 && evidence.execution_modes[0] === "open",
  pingAnNotIndex: evidence.ping_an_prices.length > 0 && Math.max(...evidence.ping_an_prices) < 100,
  reportOpened: evidence.report_text.length > 80,
  noRuntimeExceptions: exceptions.length === 0,
};
const output = { checks, strategy_version: task.config?.strategy_version, task_id: task.task_id, run_id: task.run_id, evidence, exceptions };
if (Object.values(checks).some((value) => value !== true)) throw new Error(JSON.stringify(output, null, 2));
console.log(JSON.stringify(output, null, 2));
socket.close();
