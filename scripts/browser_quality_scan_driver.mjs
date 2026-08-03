const endpoint = process.env.CDP_ENDPOINT || "http://127.0.0.1:9224/json";
const action = process.argv[2] || "status";
const scanId = process.argv[3] || "";

const tabs = await (await fetch(endpoint)).json();
const tab = tabs.find((item) => item.type === "page" && item.url.includes("127.0.0.1:8010"));
if (!tab) throw new Error("app page not found");

const socket = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = reject;
});

let sequence = 0;
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const listener = (event) => {
      const response = JSON.parse(event.data);
      if (response.id !== id) return;
      socket.removeEventListener("message", listener);
      if (response.error) reject(new Error(JSON.stringify(response.error)));
      else resolve(response.result);
    };
    socket.addEventListener("message", listener);
    socket.send(JSON.stringify({ id, method, params }));
  });
}

const expression = action === "retry"
  ? `(() => { const node = [...document.querySelectorAll('[data-quality-scan-run]')].find((item) => item.dataset.qualityScanRun === ${JSON.stringify(scanId)}); if (!node) return JSON.stringify({clicked:false}); node.click(); return JSON.stringify({clicked:true}); })()`
  : action === "refresh"
    ? `(() => { const node = document.querySelector('[data-dc-view="quality"]'); if (!node) return JSON.stringify({clicked:false}); node.click(); return JSON.stringify({clicked:true}); })()`
  : action === "all-details"
    ? `(async () => { const nodes = [...document.querySelectorAll('[data-issue]')]; const items = []; for (const node of nodes) { node.click(); await new Promise((resolve) => setTimeout(resolve, 150)); items.push({issueId:node.dataset.issue,detail:document.querySelector('#dc-quality-output')?.innerText||''}); } return JSON.stringify(items); })()`
  : action === "detail"
    ? `(() => { const node = document.querySelector('[data-issue]'); if (!node) return JSON.stringify({clicked:false}); node.click(); return JSON.stringify({clicked:true,issueId:node.dataset.issue}); })()`
  : action === "issues"
    ? `(() => { const node = [...document.querySelectorAll('[data-quality-scan-issues]')].find((item) => item.dataset.qualityScanIssues === ${JSON.stringify(scanId)}); if (!node) return JSON.stringify({clicked:false}); node.click(); return JSON.stringify({clicked:true}); })()`
    : `JSON.stringify({url:location.href,feedback:document.querySelector('#global-feedback')?.innerText||'',feedbackClass:document.querySelector('#global-feedback')?.className||'',current:document.querySelector('#dc-quality-scan-current')?.innerText||'',history:document.querySelector('#dc-quality-scan-list')?.innerText||'',issues:document.querySelector('#dc-quality-summary')?.innerText||'',issueList:document.querySelector('#dc-quality-list')?.innerText||'',detail:document.querySelector('#dc-quality-output')?.innerText||''})`;

const evaluated = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
process.stdout.write(evaluated.result.value || "");
socket.close();
