const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9224/json";
const jobId = process.argv[4];
const intervalMs = Number(process.argv[5] || 10000);
if (!jobId) throw new Error("missing job id");

const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("no Edge page");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
let sequence = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(String(event.data));
  if (!message.id || !pending.has(message.id)) return;
  const request = pending.get(message.id);
  pending.delete(message.id);
  message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result || {});
});
const command = (method, params = {}) => {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
};
const evaluate = async (expression) => {
  const result = await command("Runtime.evaluate", { expression, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
};
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", { url: `${baseUrl}/?page=market&dc_view=sync` });
await wait(3500);
let previous = "";
while (true) {
  const snapshot = await evaluate(`(() => {
    const card = [...document.querySelectorAll(".dc-task-card")]
      .find((item) => item.textContent.includes(${JSON.stringify(jobId)}));
    if (!card) return { missing: true };
    return {
      text: card.textContent.trim(),
      terminal: !card.querySelector("[data-task-stop]"),
      canRetry: Boolean(card.querySelector("[data-task-retry]")),
    };
  })()`);
  if (snapshot.text !== previous) {
    console.log(JSON.stringify({ at: new Date().toISOString(), jobId, ...snapshot }));
    previous = snapshot.text;
  }
  if (snapshot.missing || snapshot.terminal) break;
  await wait(intervalMs);
  await evaluate("document.querySelector('[data-dc-task-refresh]')?.click()");
  await wait(1500);
}
socket.close();
