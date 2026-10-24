const baseUrl = process.argv[2] || "http://127.0.0.1:8011";
const debugUrl = process.argv[3] || "http://127.0.0.1:9234/json";
const taskId = process.argv[4];
if (!taskId) throw new Error("task id is required");
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
  if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params?.exceptionDetails?.exception?.description || "runtime exception");
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
const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: `${baseUrl}/?page=market&dc_view=sync` });
await wait(4500);
await evaluate(`(() => { const button = document.querySelector('[data-task-detail="${taskId}"]'); if (!button) throw new Error('target task button missing'); button.click(); })()`);
await wait(1200);
const desktop = await evaluate(`(() => {
  const dialog = document.querySelector('#dc-sync-task-dialog');
  const card = dialog?.querySelector('.dc-task-resolution');
  return {
    open: dialog?.open === true,
    resolutionCode: card?.querySelector('.dc-resolution-code')?.textContent || '',
    title: card?.querySelector('h5')?.textContent || '',
    groups: card?.querySelectorAll('.dc-error-groups li').length || 0,
    retryButton: !!card?.querySelector('[data-task-detail-retry]'),
    routesButton: !!card?.querySelector('[data-task-open-routes]'),
    itemRows: dialog?.querySelectorAll('.dc-task-item-table tbody tr').length || dialog?.querySelectorAll('.dc-task-item-table .app-vtable-host').length || 0,
    detailText: document.querySelector('#dc-sync-task-detail')?.textContent || '',
    bodyWidth: document.body.clientWidth,
    scrollWidth: document.body.scrollWidth,
  };
})()`);
await command("Emulation.setDeviceMetricsOverride", { width: 741, height: 900, deviceScaleFactor: 1, mobile: false });
await wait(600);
const narrow = await evaluate(`(() => ({ bodyWidth: document.body.clientWidth, scrollWidth: document.body.scrollWidth, dialogWidth: Math.round(document.querySelector('#dc-sync-task-dialog').getBoundingClientRect().width) }))()`);
const checks = {
  dialogOpened: desktop.open,
  actionableDiagnosis: desktop.resolutionCode === "upstream_connection_interrupted" && desktop.title.length > 0,
  groupedEvidence: desktop.groups >= 1 && desktop.detailText.includes("90"),
  selfServiceActions: desktop.retryButton && desktop.routesButton,
  failedItemsVisible: desktop.itemRows >= 1 && desktop.detailText.includes("curl transport failed (56)"),
  desktopNoOverflow: desktop.scrollWidth <= desktop.bodyWidth + 2,
  narrowNoOverflow: narrow.scrollWidth <= narrow.bodyWidth + 2 && narrow.dialogWidth <= narrow.bodyWidth,
  noRuntimeExceptions: exceptions.length === 0,
};
if (Object.values(checks).some((value) => value !== true)) throw new Error(JSON.stringify({ checks, desktop, narrow, exceptions }, null, 2));
console.log(JSON.stringify({ checks, desktop: { ...desktop, detailText: undefined }, narrow }, null, 2));
socket.close();