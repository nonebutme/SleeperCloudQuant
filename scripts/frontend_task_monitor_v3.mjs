const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9224/json";
const jobId = process.argv[4];
const intervalMs = Number(process.argv[5] || 50000);
if (!jobId) throw new Error("missing job id");
const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("no Edge page");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
let id = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(String(event.data));
  if (!message.id || !pending.has(message.id)) return;
  const callback = pending.get(message.id);
  pending.delete(message.id);
  message.error ? callback.reject(new Error(JSON.stringify(message.error))) : callback.resolve(message.result || {});
});
const call = (method, params = {}) => {
  const requestId = ++id;
  socket.send(JSON.stringify({ id: requestId, method, params }));
  return new Promise((resolve, reject) => pending.set(requestId, { resolve, reject }));
};
const evaluate = async (expression) => {
  const response = await call("Runtime.evaluate", { expression, returnByValue: true });
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result?.value;
};
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const read = () => evaluate(`(() => {
  const detail = [...document.querySelectorAll("[data-task-detail]")]
    .find((button) => button.dataset.taskDetail === ${JSON.stringify(jobId)});
  const card = detail?.closest(".dc-task-card");
  return card ? {
    text: card.textContent.trim(),
    terminal: !card.querySelector("[data-task-stop]"),
    canRetry: Boolean(card.querySelector("[data-task-retry]")),
  } : null;
})()`);
await call("Page.enable");
await call("Runtime.enable");
await call("Page.navigate", { url: `${baseUrl}/?page=market&dc_view=sync` });
let snapshot = null;
for (let attempt = 0; attempt < 60 && !snapshot; attempt += 1) {
  await wait(1000);
  snapshot = await read();
}
if (!snapshot) throw new Error(`task card not found: ${jobId}`);
while (true) {
  console.log(JSON.stringify({ at: new Date().toISOString(), jobId, ...snapshot }));
  if (snapshot.terminal) break;
  await wait(intervalMs);
  await call("Page.reload", { ignoreCache: false });
  snapshot = null;
  for (let attempt = 0; attempt < 30 && !snapshot; attempt += 1) {
    await wait(1000);
    snapshot = await read();
  }
  if (!snapshot) throw new Error(`task card disappeared: ${jobId}`);
}
socket.close();
