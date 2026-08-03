const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9224/json";
const action = process.argv[4] || "status";
const args = process.argv.slice(5);

const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("没有可用的 Edge 页面");
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
    const request = pending.get(message.id);
    pending.delete(message.id);
    message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result || {});
  }
  if (message.method === "Runtime.exceptionThrown") {
    exceptions.push(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text);
  }
});
const command = (method, params = {}) => {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
};
const evaluate = async (expression, awaitPromise = false) => {
  const result = await command("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
};
const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const navigate = async (view) => {
  await command("Page.navigate", { url: `${baseUrl}/?page=market&dc_view=${view}` });
  await wait(3500);
};
const setFormValue = (selector, value) => `
  (() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!element) throw new Error("缺少控件 " + ${JSON.stringify(selector)});
    element.value = ${JSON.stringify(value)};
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  })()
`;
const syncForm = async (adjustment, startDate, endDate, mode = "historical_gap") => {
  await evaluate(setFormValue('#dc-sync-form [name="mode"]', mode));
  await evaluate(setFormValue('#dc-sync-form [name="start_trade_date"]', startDate));
  await evaluate(setFormValue('#dc-sync-form [name="target_trade_date"]', endDate));
  await evaluate(setFormValue('#dc-sync-form [name="scope"]', "all_current"));
  await evaluate(setFormValue('#dc-sync-form [name="adjustments"]', adjustment));
};
const waitPreview = async () => {
  // Give the submit handler a chance to enter its loading state before
  // accepting an enabled create button; otherwise a previous preview can be
  // mistaken for the new result on a fast CDP round-trip.
  await wait(250);
  for (let index = 0; index < 180; index += 1) {
    const state = await evaluate(`(() => ({
      enabled: !document.querySelector("#dc-sync-create")?.disabled,
      feedback: document.querySelector("#app-feedback")?.textContent?.trim() || "",
      output: document.querySelector("#dc-sync-preview-output")?.textContent?.trim() || ""
    }))()`);
    if (state.enabled && state.output) return state;
    if (/失败|错误/.test(state.feedback)) throw new Error(state.feedback);
    await wait(1000);
  }
  throw new Error("预览等待超时");
};
const previewResult = () => evaluate(`(() => ({
  output: document.querySelector("#dc-sync-preview-output")?.textContent?.trim() || "",
  shards: [...document.querySelectorAll("#dc-sync-shards tbody tr")].slice(0, 20).map(row => {
    const cells = [...row.querySelectorAll("td")].map(cell => cell.textContent.trim());
    return { shard: cells[1], start: cells[2], end: cells[3], missing: cells[4] };
  }),
  feedback: document.querySelector("#app-feedback")?.textContent?.trim() || ""
}))()`);
const taskSnapshot = (jobId = "") => evaluate(`(() => {
  const jobId = ${JSON.stringify(jobId)};
  const buttons = [...document.querySelectorAll("[data-task-detail]")];
  const detailButton = jobId ? buttons.find(button => button.dataset.taskDetail === jobId) : buttons[0];
  const card = detailButton?.closest(".dc-task-card");
  return {
    jobId: detailButton?.dataset.taskDetail || "",
    cardText: card?.textContent?.trim() || "",
    canRun: !!card?.querySelector("[data-task-run]"),
    canRetry: !!card?.querySelector("[data-task-retry]"),
    canStop: !!card?.querySelector("[data-task-stop]"),
    activeText: document.querySelector("#dc-sync-active")?.textContent?.trim() || "",
    detailText: document.querySelector("#dc-sync-task-detail")?.textContent?.trim() || "",
    feedback: document.querySelector("#app-feedback")?.textContent?.trim() || ""
  };
})()`);

await command("Page.enable");
await command("Runtime.enable");

let result;
  await evaluate('document.querySelector("#dc-sync-preview-output").textContent = ""');
if (action === "preview" || action === "create") {
  const [adjustment = "qfq", startDate = "2015-01-01", endDate = "2026-07-29"] = args;
  await navigate("sync");
  await syncForm(adjustment, startDate, endDate);
  await evaluate('document.querySelector("#dc-sync-form button[type=submit]").click()');
  await waitPreview();
  const preview = await previewResult();
  if (action === "preview") {
    result = { form: { dataset: "a_share_daily", mode: "historical_gap", adjustment, scope: "all_current", startDate, endDate }, preview };
  } else {
    await evaluate("window.confirm = () => true");
    await evaluate('document.querySelector("#dc-sync-create").click()');
    for (let index = 0; index < 60; index += 1) {
      await wait(500);
      const snapshot = await taskSnapshot();
      if (snapshot.jobId) {
        result = { form: { dataset: "a_share_daily", mode: "historical_gap", adjustment, scope: "all_current", startDate, endDate }, preview, task: snapshot };
        break;
      }
    }
    if (!result) throw new Error("创建任务后未看到任务卡");
  }
} else if (action === "run" || action === "retry" || action === "stop") {
  const [jobId] = args;
  if (!jobId) throw new Error("缺少 job id");
  await navigate("sync");
  const attribute = action === "run" ? "data-task-run" : action === "retry" ? "data-task-retry" : "data-task-stop";
  await evaluate("window.confirm = () => true");
  const clicked = await evaluate(`(() => {
    const button = [...document.querySelectorAll("[${attribute}]")].find(item => item.getAttribute("${attribute}") === ${JSON.stringify(jobId)});
    if (!button) return false;
    button.click();
    return true;
  })()`);
  if (!clicked) throw new Error(`页面没有 ${action} 按钮`);
  await wait(2500);
  result = await taskSnapshot(jobId);
} else if (action === "task") {
  const [jobId = ""] = args;
  await navigate("sync");
  if (jobId) {
    await evaluate(`(() => {
      const button = [...document.querySelectorAll("[data-task-detail]")].find(item => item.dataset.taskDetail === ${JSON.stringify(jobId)});
      button?.click();
    })()`);
    await wait(800);
  }
  result = await taskSnapshot(jobId);
} else if (action === "m4") {
  const [symbol, startDate = "2015-01-01", endDate = "2026-07-29", adjustment = "qfq"] = args;
  if (!symbol) throw new Error("缺少股票代码");
  await navigate("assets");
  await evaluate('document.querySelector(\'[data-m4-mode="list"][data-m4-market=""]\')?.click()');
  await wait(1000);
  await evaluate(setFormValue('#a-share-symbol-form [name="query"]', symbol));
  await evaluate('document.querySelector("#a-share-symbol-form button[type=submit]").click()');
  await wait(1200);
  const opened = await evaluate(`(() => {
    const button = [...document.querySelectorAll("[data-a-share-symbol]")].find(item => item.dataset.aShareSymbol === ${JSON.stringify(symbol)});
    if (!button) return false;
    button.click();
    return true;
  })()`);
  if (!opened) throw new Error("股票目录未找到 " + symbol);
  await wait(600);
  await evaluate(setFormValue('#a-share-daily-form [name="start_date"]', startDate));
  await evaluate(setFormValue('#a-share-daily-form [name="end_date"]', endDate));
  await evaluate(setFormValue('#a-share-daily-form [name="adjustment"]', adjustment));
  await evaluate(setFormValue('#a-share-daily-form [name="limit"]', "2000"));
  await evaluate('document.querySelector("#a-share-daily-form button[type=submit]").click()');
  await wait(2500);
  result = await evaluate(`(() => ({
    form: Object.fromEntries(new FormData(document.querySelector("#a-share-daily-form")).entries()),
    title: document.querySelector("#dc-m4-title")?.textContent?.trim() || "",
    summary: document.querySelector("#a-share-daily-summary")?.textContent?.trim() || "",
    rawEvidence: document.querySelector("#a-share-daily-output")?.textContent?.trim() || "",
    firstDates: [...document.querySelectorAll("#a-share-daily-body tr td:first-child")].slice(0, 10).map(x => x.textContent.trim()),
    chartCandles: document.querySelectorAll("#a-share-daily-chart [data-kline-date]").length,
    feedback: document.querySelector("#app-feedback")?.textContent?.trim() || ""
  }))()`);
} else if (action === "quality") {
  const [startDate = "2015-01-01", endDate = "2026-07-29", taskId = ""] = args;
  await navigate("quality");
  await evaluate(setFormValue('#dc-quality-filter [name="date_from"]', startDate));
  await evaluate(setFormValue('#dc-quality-filter [name="date_to"]', endDate));
  if (taskId) await evaluate(setFormValue('#dc-quality-filter [name="source_task_id"]', taskId));
  await evaluate('document.querySelector("#dc-quality-filter button[type=submit]").click()');
  await wait(1800);
  result = await evaluate(`(() => ({
    form: Object.fromEntries(new FormData(document.querySelector("#dc-quality-filter")).entries()),
    summary: document.querySelector("#dc-quality-summary")?.textContent?.trim() || "",
    list: document.querySelector("#dc-quality-list")?.textContent?.trim() || "",
    feedback: document.querySelector("#app-feedback")?.textContent?.trim() || ""
  }))()`);
} else {
  await navigate("sync");
  result = await taskSnapshot();
}

console.log(JSON.stringify({ action, result, exceptions }, null, 2));
socket.close();
