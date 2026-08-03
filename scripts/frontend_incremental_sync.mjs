const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9224/json";
const action = process.argv[4] || "preview";
const adjustment = process.argv[5] || "qfq";
const targetDate = process.argv[6] || "2026-07-30";

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
const setValue = (selector, value) => `(() => {
  const element = document.querySelector(${JSON.stringify(selector)});
  if (!element) throw new Error("missing " + ${JSON.stringify(selector)});
  element.value = ${JSON.stringify(value)};
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
})()`;

await command("Page.enable");
await command("Runtime.enable");
await command("Page.navigate", { url: `${baseUrl}/?page=market&dc_view=sync` });
await wait(3500);
await evaluate(setValue('#dc-sync-form [name="dataset"]', "a_share_daily"));
await evaluate(setValue('#dc-sync-form [name="mode"]', "incremental"));
await evaluate(setValue('#dc-sync-form [name="target_trade_date"]', targetDate));
await evaluate(setValue('#dc-sync-form [name="scope"]', "all_current"));
await evaluate(setValue('#dc-sync-form [name="adjustments"]', adjustment));
await evaluate('document.querySelector("#dc-sync-form button[type=submit]").click()');
for (let index = 0; index < 180; index += 1) {
  await wait(500);
  if (await evaluate('!document.querySelector("#dc-sync-create")?.disabled')) break;
  if (index === 179) throw new Error("preview timeout");
}
const preview = await evaluate(`({
  output: document.querySelector("#dc-sync-preview-output")?.textContent?.trim() || "",
  shards: [...document.querySelectorAll("#dc-sync-shards tbody tr")].slice(0, 20).map((row) => row.textContent.trim()),
})`);
if (action === "create") {
  await evaluate("window.confirm = () => true");
  await evaluate('document.querySelector("#dc-sync-create").click()');
  await wait(1800);
}
console.log(JSON.stringify({ action, form: { dataset: "a_share_daily", mode: "incremental", scope: "all_current", adjustment, targetDate }, preview }, null, 2));
socket.close();
