const baseUrl = process.argv[2] || "http://127.0.0.1:8018";
const targets = await fetch("http://127.0.0.1:9223/json").then((response) => response.json());
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
async function wait(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}
async function openReport(task) {
  const before = exceptions.length;
  await evaluate(`(async () => { stage76SelectedTask = ${JSON.stringify(task)}; await handleStage76TaskAction(stage76SelectedTask, "analysis"); })()`, true);
  await wait(12000);
  await evaluate(`(() => {
    document.querySelectorAll(".report-analysis-shell details").forEach((node) => {
      node.open = true;
    });
  })()`);
  await wait(500);
  const audit = await evaluate(`(() => {
    const shell = document.querySelector(".report-analysis-shell");
    const text = shell?.innerText || "";
    const criticalOverflow = [...document.querySelectorAll(".report-analysis-shell *")]
      .filter((node) => node.scrollWidth > node.clientWidth + 2 && getComputedStyle(node).overflowX === "visible")
      .slice(0, 10).map((node) => ({ tag: node.tagName, className: String(node.className).slice(0, 80), delta: node.scrollWidth - node.clientWidth }));
    return {
      text,
      shell: Boolean(shell),
      clientWidth: document.body.clientWidth,
      scrollWidth: document.body.scrollWidth,
      criticalOverflow,
      svgCount: document.querySelectorAll(".report-analysis-shell svg").length,
      tableCount: document.querySelectorAll(".report-analysis-shell table").length,
    };
  })()`);
  audit.newExceptions = exceptions.slice(before);
  return audit;
}

await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", { url: `${baseUrl}/?page=backtest` });
await wait(6000);

const single = await openReport({
  task_id: "stage80-82-signal-ohlc-20260728",
  run_id: "stage80-82-signal-ohlc-20260728-run",
  mode: "single",
  mode_label: "单品种测试",
  name: "阶段80/82原始分数与OHLC真实验收",
  status: "completed",
  date_window: { start_date: "2026-01-01", end_date: "2026-07-24" },
});
const portfolio = await openReport({
  task_id: "stage83-vwap-capacity-20260728",
  run_id: "stage83-vwap-capacity-20260728-shared-portfolio",
  mode: "shared-portfolio",
  mode_label: "投资组合回测",
  name: "阶段83 VWAP与容量真实验收",
  status: "completed",
  date_window: { start_date: "2026-05-01", end_date: "2026-07-24" },
});

const checks = {
  single: {
    shell: single.shell,
    noOverflow: single.scrollWidth <= single.clientWidth + 2 && !single.criticalOverflow.length,
    hasMonthly: single.text.includes("月度收益热力图"),
    hasOos: single.text.includes("out_of_sample") || single.text.includes("样本外"),
    noOldLabels: !single.text.includes("独立选股") && !single.text.includes("共享资金池"),
    noExceptions: !single.newExceptions.length,
  },
  portfolio: {
    shell: portfolio.shell,
    noOverflow: portfolio.scrollWidth <= portfolio.clientWidth + 2 && !portfolio.criticalOverflow.length,
    hasVwap: portfolio.text.includes("VWAP"),
    hasCapacity: portfolio.text.includes("资金倍数") || portfolio.text.includes("容量"),
    hasStress: portfolio.text.includes("佣金倍数") || portfolio.text.includes("成本敏感性"),
    noOldLabels: !portfolio.text.includes("独立选股") && !portfolio.text.includes("共享资金池"),
    noExceptions: !portfolio.newExceptions.length,
  },
};
if (Object.values(checks).some((group) => Object.values(group).some((value) => value !== true))) {
  throw new Error(JSON.stringify({ checks, exceptions, singleDiag: { clientWidth: single.clientWidth, scrollWidth: single.scrollWidth, criticalOverflow: single.criticalOverflow }, portfolioDiag: { clientWidth: portfolio.clientWidth, scrollWidth: portfolio.scrollWidth, criticalOverflow: portfolio.criticalOverflow }, singleText: single.text.slice(0, 2000), portfolioText: portfolio.text.slice(0, 2000) }, null, 2));
}
console.log(JSON.stringify({
  checks,
  single: { svgCount: single.svgCount, tableCount: single.tableCount },
  portfolio: { svgCount: portfolio.svgCount, tableCount: portfolio.tableCount },
}, null, 2));
socket.close();
