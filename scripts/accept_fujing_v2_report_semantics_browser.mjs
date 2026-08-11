const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9226/json";
const taskId = process.argv[4] || "portfolio-20260809015504-r6kw";

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
    exceptions.push(message.params?.exceptionDetails?.exception?.description || "Runtime exception");
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

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
const rowSelector = `[data-stage76-task="${taskId}"][data-stage76-mode-value="shared-portfolio"]`;
const expectedOrigin = new URL(baseUrl).origin;
const taskAlreadyOpen = await evaluate(`(() => {
  return location.origin === ${JSON.stringify(expectedOrigin)}
    && stage76SelectedTask?.task_id === ${JSON.stringify(taskId)}
    && (stage76CurrentResult?.run_id || stage76CurrentResult?.summary?.run_id) === stage76SelectedTask?.run_id;
})()`);
if (!taskAlreadyOpen) {
  await command("Page.navigate", { url: `${baseUrl}/?page=backtest&workspace=tasks&accept=fujing-v2-report-${Date.now()}` });
  await waitFor(`document.querySelector(${JSON.stringify(rowSelector)}) !== null`, "portfolio task row");
  const clicked = await evaluate(`(() => {
    const row = document.querySelector(${JSON.stringify(rowSelector)});
    const button = row?.querySelector('[data-stage76-action="analysis"]');
    if (!button) return false;
    button.click();
    return true;
  })()`);
  if (!clicked) throw new Error("portfolio analysis button missing");
}

await waitFor(`(() => {
  const text = document.querySelector("#report-result-overview")?.innerText || "";
  return text.includes("胜率") && text.includes("57.65%") && text.includes("盈利平仓 / 已完成交易") && !text.includes("正在加载专业报告");
})()`, "fixed report win-rate semantics", 240000);

const evidence = await evaluate(`(() => ({
  selected_task: stage76SelectedTask?.task_id || "",
  selected_mode: stage76SelectedTask?.mode || "",
  report_text: (document.querySelector("#report-result-overview")?.innerText || "").slice(0, 1600),
}))()`);
const checks = {
  selectedTask: evidence.selected_task === taskId && evidence.selected_mode === "shared-portfolio",
  reportOpened: evidence.report_text.length > 80,
  closedTradeWinRate: evidence.report_text.includes("胜率") && evidence.report_text.includes("57.65%") && evidence.report_text.includes("盈利平仓 / 已完成交易"),
  noEstimatedWinRate: !evidence.report_text.includes("估算胜率 73.97%"),
  noRuntimeExceptions: exceptions.length === 0,
};
const output = { checks, task_id: taskId, evidence, exceptions };
console.log(JSON.stringify(output, null, 2));
socket.close();
if (Object.values(checks).some((value) => !value)) process.exitCode = 1;
