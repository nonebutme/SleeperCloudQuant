const debugUrl = process.argv[2] || "http://127.0.0.1:9226/json";
const targets = await fetch(debugUrl).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("no page target");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
const expression = `(() => ({
  url: location.href,
  screeningId: currentScreeningTaskId,
  screeningTask: currentScreeningTask && {task_id: currentScreeningTask.task_id, mode: currentScreeningTask.mode, status: currentScreeningTask.status, run_id: currentScreeningTask.run_id},
  selected: stage76SelectedTask && {task_id: stage76SelectedTask.task_id, mode: stage76SelectedTask.mode, status: stage76SelectedTask.status, run_id: stage76SelectedTask.run_id},
  result: {run_id: stage76CurrentResult?.run_id, summary_run: stage76CurrentResult?.summary?.run_id},
  resultButtons: [...document.querySelectorAll("[data-independent-result-run]")].map((node) => ({run_id: node.dataset.independentResultRun, selected: node.classList.contains("is-selected")})),
  reportText: (document.querySelector("#report-result-overview")?.innerText || "").slice(0, 200),
  feedback: document.querySelector("#feedback")?.innerText || "",
}))()`;
const result = await new Promise((resolve, reject) => {
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data));
    if (message.id !== 1) return;
    if (message.error || message.exceptionDetails) reject(new Error(JSON.stringify(message)));
    else resolve(message.result?.result?.value);
  });
  socket.send(JSON.stringify({ id: 1, method: "Runtime.evaluate", params: { expression, returnByValue: true } }));
});
console.log(JSON.stringify(result, null, 2));
socket.close();
