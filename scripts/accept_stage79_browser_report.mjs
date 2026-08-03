import fs from "node:fs";

const [baseUrl, taskId, screenshotPath] = process.argv.slice(2);
if (!baseUrl || !taskId || !screenshotPath) {
  throw new Error("usage: node accept_stage79_browser_report.mjs <baseUrl> <taskId> <screenshotPath>");
}

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
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result || {});
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

await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", { url: `${baseUrl}/?page=backtest&view=independent` });
await new Promise((resolve) => setTimeout(resolve, 7000));

const openExpression = `
(async () => {
  const task = {
    task_id: ${JSON.stringify(taskId)},
    mode: "independent-screening",
    mode_label: "独立账户批量回测",
    name: "双均线 + ATR动态止损 独立账户批量回测",
    status: "partial_failed",
    strategy_binding: { strategy_id: "dual_ma_atr_dynamic_stop", strategy_version: "v1" },
    date_window: { start_date: "2023-01-01", end_date: "2026-07-01" },
    links: { report: "/api/reporting/backtest-modes/independent-screening/${taskId}" }
  };
  await openBacktestModeReport(task);
  return true;
})()`;
const opened = await command("Runtime.evaluate", {
  expression: openExpression,
  awaitPromise: true,
  returnByValue: true,
});
if (opened.exceptionDetails) throw new Error(JSON.stringify(opened.exceptionDetails));
await new Promise((resolve) => setTimeout(resolve, 3000));

const audit = await command("Runtime.evaluate", {
  expression: `(() => {
    const text = document.body.innerText;
    const overflowing = [...document.querySelectorAll("body *")]
      .filter((node) => node.scrollWidth > node.clientWidth + 2 && getComputedStyle(node).overflowX === "visible")
      .slice(0, 20)
      .map((node) => ({ tag: node.tagName, id: node.id, className: String(node.className).slice(0, 120), delta: node.scrollWidth - node.clientWidth }));
    return {
      title: document.title,
      bodyClientWidth: document.body.clientWidth,
      bodyScrollWidth: document.body.scrollWidth,
      bodyClientHeight: document.body.clientHeight,
      bodyScrollHeight: document.body.scrollHeight,
      criticalOverflow: overflowing,
      hasTaskId: text.includes(${JSON.stringify(taskId)}),
      hasIndependentMode: text.includes("独立账户批量回测"),
      hasIc: text.includes("IC") && text.includes("Rank IC"),
      hasLayering: text.includes("Q1") && text.includes("Q5"),
      hasSampleCount: text.includes("5533") || text.includes("5,533"),
      hasFailureDisclosure: text.includes("12") && (text.includes("失败") || text.includes("部分失败")),
      oldLabelsPresent: text.includes("独立选股") || text.includes("共享资金池"),
      qSnippets: text.split("\\n").filter((line) => line.includes("Q1") || line.includes("Q5")).slice(0, 12),
      failureSnippets: text.split("\\n").filter((line) => line.includes("失败") || line.includes("部分失败")).slice(0, 12),
      svgCount: document.querySelectorAll("svg").length,
      reportTextLength: text.length
    };
  })()`,
  returnByValue: true,
});
const result = audit.result?.value;
if (!result) throw new Error("browser audit returned no value");
if (
  result.bodyScrollWidth > result.bodyClientWidth + 2
  || result.criticalOverflow.length
  || !result.hasIndependentMode
  || !result.hasIc
  || !result.hasLayering
  || !result.hasSampleCount
  || !result.hasFailureDisclosure
  || result.oldLabelsPresent
  || exceptions.length
) {
  throw new Error(JSON.stringify({ result, exceptions }, null, 2));
}

const screenshot = await command("Page.captureScreenshot", {
  format: "png",
  captureBeyondViewport: true,
});
fs.writeFileSync(screenshotPath, Buffer.from(screenshot.data, "base64"));
console.log(JSON.stringify({ ...result, exceptions, screenshotPath }, null, 2));
socket.close();
