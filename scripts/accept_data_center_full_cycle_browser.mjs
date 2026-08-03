const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9224/json";
const action = process.argv[4] || "inspect";
const dataset = process.argv[5] || "a_share_daily";
const syncMode = action === "preview-history" ? "historical_gap" : "incremental";

const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("没有可用的 Edge 调试页面");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let sequence = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(String(event.data));
  if (message.id && pending.has(message.id)) {
    const request = pending.get(message.id);
    pending.delete(message.id);
    message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result || {});
  }
});
const command = (method, params = {}) => {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
};
const evaluate = async (expression, awaitPromise = false) => {
  const response = await command("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result?.value;
};
const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const text = (selector) => `document.querySelector(${JSON.stringify(selector)})?.textContent?.trim() || ""`;

await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", { url: `${baseUrl}/?page=market&dc_view=sync` });
await wait(3500);

if (action === "preview-history" || action === "preview-incremental") {
  await evaluate(`(() => {
    const set = (selector, value) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error("missing " + selector);
      element.value = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const datasetButton = document.querySelector('[data-ds-mode="sync"][data-ds-id="${dataset}"]');
    if (!datasetButton) throw new Error("missing sync dataset " + ${JSON.stringify(dataset)});
    datasetButton.click();
    setTimeout(() => {
    set('#dc-sync-form [name="mode"]', ${JSON.stringify(syncMode)});
    set('#dc-sync-form [name="start_trade_date"]', '2026-07-28');
    set('#dc-sync-form [name="target_trade_date"]', '2026-07-30');
    set('#dc-sync-form [name="scope"]', 'all_current');
    set('#dc-sync-form [name="adjustments"]', 'qfq');
    document.querySelector('#dc-sync-form button[type="submit"]').click();
    }, 800);
  })()`);
  await wait(1200);
  for (let index = 0; index < 120; index += 1) {
    await wait(1000);
    const state = await evaluate(`(() => ({
      output: ${text("#dc-sync-preview-output")},
      feedback: ${text("#app-feedback")},
      enabled: !document.querySelector("#dc-sync-create")?.disabled,
      previewButton: document.querySelector("#dc-sync-form button[type=submit]")?.textContent || ""
    }))()`);
    if (/执行模式/.test(state.output) || /加载失败|请求失败|发生错误/.test(state.output + state.feedback)) {
      console.log(JSON.stringify({ action, dataset, state }, null, 2));
      socket.close();
      process.exit(/加载失败|请求失败|发生错误/.test(state.output + state.feedback) ? 2 : 0);
    }
  }
  throw new Error("历史缺口预览超时");
}

const result = await evaluate(`(() => ({
  url: location.href,
  active: document.querySelector(".dc-view.is-active")?.id,
  dataset: document.querySelector('#dc-sync-form [name="dataset"]')?.value,
  datasetOptions: [...document.querySelectorAll('#dc-sync-form [name="dataset"] option')].map(x => ({value:x.value,text:x.textContent,disabled:x.disabled})), 
  modeOptions: [...document.querySelectorAll('#dc-sync-form [name="mode"] option')].map(x => ({value:x.value,text:x.textContent,disabled:x.disabled})),
  taskCount: document.querySelectorAll(".dc-task-card").length,
  feedback: ${text("#app-feedback")}
}))()`);
console.log(JSON.stringify({ action, result }, null, 2));
socket.close();
