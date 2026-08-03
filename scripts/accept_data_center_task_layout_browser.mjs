const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9224/json";
const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page" && item.url.includes("127.0.0.1:8010")) || targets.find((item) => item.type === "page");
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
async function evaluate(expression, awaitPromise = false) {
  const response = await command("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}
const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: `${baseUrl}/?page=market&dc_view=sync` });
await wait(7000);

const sync = await evaluate(`(() => {
  const catalog = document.querySelector('.dc-sync-catalog')?.getBoundingClientRect();
  const create = document.querySelector('.dc-sync-create-column > .dc-surface')?.getBoundingClientRect();
  const preview = document.querySelector('.dc-sync-preview-surface')?.getBoundingClientRect();
  const list = document.querySelector('.dc-task-list-section')?.getBoundingClientRect();
  const first = document.querySelector('.dc-task-card');
  return {
    active: document.querySelector('.dc-view.is-active')?.id,
    catalogLeftOfCreate: !!catalog && !!create && catalog.right <= create.left + 2,
    previewBelowCreate: !!preview && !!create && preview.top >= create.bottom,
    listBelowBuilder: !!list && !!preview && list.top >= preview.bottom,
    taskTitle: document.querySelector('.dc-task-list-section h4')?.textContent || '',
    cardCount: document.querySelectorAll('.dc-task-card').length,
    cardColumns: first ? getComputedStyle(first).gridTemplateColumns : '',
    cardText: first?.textContent || '',
    rawId: first?.querySelector('code')?.textContent || '',
    taskListText: document.querySelector('#dc-sync-task-list')?.textContent || '',
    feedback: document.querySelector('#global-feedback')?.textContent || '',
    bodyWidth: document.body.clientWidth,
    scrollWidth: document.body.scrollWidth,
  };
})()`);

await evaluate(`document.querySelector('[data-task-detail]')?.click()`);
await wait(1200);
const dialog = await evaluate(`(() => ({
  open: document.querySelector('#dc-sync-task-dialog')?.open === true,
  title: document.querySelector('#dc-sync-task-dialog-title')?.textContent || '',
  text: document.querySelector('#dc-sync-task-detail')?.textContent || '',
  table: !!document.querySelector('#dc-sync-task-detail table, #dc-sync-task-detail .app-vtable-host'),
}))()`);
await evaluate(`document.querySelector('#dc-sync-task-dialog-close')?.click()`);

await evaluate(`document.querySelector('[data-dc-view="quality"]').click()`);
await wait(1800);
const quality = await evaluate(`(() => ({
  active: document.querySelector('.dc-view.is-active')?.id,
  flowSteps: document.querySelectorAll('.dc-quality-flow-guide > div').length,
  currentText: document.querySelector('#dc-quality-scan-current')?.textContent || '',
  historyText: document.querySelector('#dc-quality-scan-list')?.textContent || '',
  ruleTags: document.querySelectorAll('#dc-quality-scan-list .dc-rule-tag').length,
  summaryCards: document.querySelectorAll('#dc-quality-summary > button').length,
  bodyWidth: document.body.clientWidth,
  scrollWidth: document.body.scrollWidth,
}))()`);

await command("Emulation.setDeviceMetricsOverride", { width: 741, height: 1000, deviceScaleFactor: 1, mobile: false });
await wait(700);
const narrow = await evaluate(`(() => ({ bodyWidth: document.body.clientWidth, scrollWidth: document.body.scrollWidth }))()`);

const checks = {
  syncActive: sync.active === "dc-view-sync",
  requestedLayout: sync.catalogLeftOfCreate && sync.previewBelowCreate && sync.listBelowBuilder,
  taskListRenamed: sync.taskTitle === "任务列表",
  splitTaskCard: sync.cardCount > 0 && sync.cardColumns.split(" ").length >= 2,
  taskTimesVisible: sync.cardText.includes("创建时间") && sync.cardText.includes("开始时间") && sync.cardText.includes("执行时长"),
  readableAndRawId: sync.cardText.includes("同步") && sync.rawId.includes("sync-"),
  detailDialog: dialog.open && dialog.title.length > 0 && dialog.text.includes("工作项"),
  qualityActive: quality.active === "dc-view-quality",
  qualityFlow: quality.flowSteps === 4,
  qualityReadableTimes: quality.currentText.includes("开始时间") && quality.currentText.includes("执行时长") && quality.historyText.includes("耗时"),
  qualityRulesReadable: quality.ruleTags > 0,
  qualitySummary: quality.summaryCards === 6,
  desktopNoOverflow: sync.scrollWidth <= sync.bodyWidth + 2 && quality.scrollWidth <= quality.bodyWidth + 2,
  narrowNoOverflow: narrow.scrollWidth <= narrow.bodyWidth + 2,
  noRuntimeExceptions: exceptions.length === 0,
};
if (Object.values(checks).some((value) => value !== true)) {
  throw new Error(JSON.stringify({ checks, sync, dialog, quality, narrow, exceptions }, null, 2));
}
console.log(JSON.stringify({ checks, sync, dialog, quality, narrow }, null, 2));
socket.close();
