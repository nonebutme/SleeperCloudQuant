import { readFileSync } from "node:fs";

const baseUrl = process.argv[2] || "http://127.0.0.1:8010";
const debugUrl = process.argv[3] || "http://127.0.0.1:9226/json";
const strategySource = readFileSync(new URL("./fujing_v2_strategy.py", import.meta.url), "utf8");
const symbols = "000001,600000,000333,600519,300750,601318,000858,600036";
const terminals = new Set(["completed", "partial_completed", "partial_failed", "failed", "cancelled"]);

const targets = await fetch(debugUrl).then((response) => response.json());
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
    const item = pending.get(message.id);
    pending.delete(message.id);
    message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result || {});
  }
  if (message.method === "Runtime.exceptionThrown") {
    exceptions.push(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text || "Runtime exception");
  }
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
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function waitFor(expression, label, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  let lastValue;
  while (Date.now() < deadline) {
    try {
      lastValue = await evaluate(expression);
      if (lastValue) return lastValue;
    } catch (_) {}
    await wait(300);
  }
  throw new Error(`timeout waiting for ${label}; last=${JSON.stringify(lastValue)}`);
}
async function click(selector) {
  const clicked = await evaluate(`(() => { const node=document.querySelector(${JSON.stringify(selector)}); if(!node)return false; node.click(); return true; })()`);
  if (!clicked) throw new Error(`missing clickable ${selector}`);
}
async function setValue(selector, value, eventName = "input") {
  const changed = await evaluate(`(() => { const node=document.querySelector(${JSON.stringify(selector)}); if(!node)return false; node.value=${JSON.stringify(value)}; node.dispatchEvent(new Event(${JSON.stringify(eventName)},{bubbles:true})); return true; })()`);
  if (!changed) throw new Error(`missing input ${selector}`);
}
async function api(path) {
  const response = await fetch(new URL(path, baseUrl));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${path}: ${response.status} ${JSON.stringify(payload)}`);
  return payload;
}
async function pollTask(path, label, timeoutMs = 240000) {
  const deadline = Date.now() + timeoutMs;
  let task = null;
  while (Date.now() < deadline) {
    const payload = await api(path);
    task = payload.task || payload.result?.task || payload.result || payload;
    if (terminals.has(task.status)) {
      if (!["completed", "partial_completed"].includes(task.status)) {
        throw new Error(`${label} ended as ${task.status}: ${task.error_message || task.error || "unknown error"}`);
      }
      return task;
    }
    await wait(1000);
  }
  throw new Error(`${label} timeout: ${JSON.stringify(task)}`);
}
async function setCommonConfig() {
  await setValue("#backtest-common-start", "2020-01-01");
  await setValue("#backtest-common-end", "2026-07-24");
  await setValue("#backtest-common-adjustment", "raw", "change");
  await setValue("#backtest-common-cash", "1000000");
  await click("#backtest-common-apply");
  await wait(300);
}
async function inspectResult(mode) {
  const action = `[data-stage76-form-action][data-stage76-action-mode="${mode}"]`;
  const expectedTaskMode = mode === "independent" ? "independent-screening" : mode === "portfolio" ? "shared-portfolio" : "single";
  const previousResultRun = await evaluate(`stage76CurrentResult?.run_id || stage76CurrentResult?.summary?.run_id || ""`);
  await waitFor(`(() => { const node=document.querySelector(${JSON.stringify(action)}); return Boolean(node && !node.disabled); })()`, `${mode} analysis button`, 30000);
  await click(action);
  await waitFor(`(() => {
    const selected = stage76SelectedTask;
    const resultRun = stage76CurrentResult?.run_id || stage76CurrentResult?.summary?.run_id || "";
    if (${JSON.stringify(expectedTaskMode)} === "independent-screening") {
      const selectedRun = document.querySelector("[data-independent-result-run].is-selected")?.dataset.independentResultRun || "";
      return Boolean(resultRun && selectedRun === resultRun && resultRun.startsWith(currentScreeningTaskId));
    }
    if (!selected || selected.mode !== ${JSON.stringify(expectedTaskMode)}) return false;
    return Boolean(selected.run_id && resultRun === selected.run_id && resultRun !== ${JSON.stringify(previousResultRun)});
  })()`, `${mode} result context`, 120000);
  await waitFor(`(() => { const node=document.querySelector("#report-result-overview"); return Boolean(node && node.innerText.length > 80 && !node.innerText.includes("正在加载专业报告")); })()`, `${mode} professional report`, 120000);
  const evidence = await evaluate(`(() => {
    const result=stage76CurrentResult || {};
    const report=document.querySelector("#report-result-overview");
    return {
      selectedTask: stage76SelectedTask ? {task_id:stage76SelectedTask.task_id,mode:stage76SelectedTask.mode,run_id:stage76SelectedTask.run_id,status:stage76SelectedTask.status} : null,
      reportText:(report?.innerText || "").slice(0,4000),
      reportDimensions:report?.querySelectorAll(".stage76-report-dimensions details").length || 0,
      metrics:result.metrics || {},
      summary:result.summary || {},
      tradeCount:(result.trades || []).length,
      positionCount:(result.positions || []).length,
      accountCount:(result.accounts || []).length,
      strategyBinding:result.strategy_binding || result.data_asset_trace?.strategy_binding || {},
      executionRules:result.execution_rules || {},
      executionModes:[...new Set((result.trades || []).map((trade)=>trade.notes?.execution_price_mode).filter(Boolean))],
    };
  })()`);
  for (const tab of ["trades", "positions", "accounts"]) {
    await click(`[data-stage76-result-tab="${tab}"]`);
    await wait(200);
    evidence[`${tab}Text`] = await evaluate(`document.querySelector('[data-stage76-result-section="${tab}"]')?.innerText.slice(0,1200) || ""`);
  }
  await click('[data-stage76-result-tab="analysis"]');
  return evidence;
}

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: `${baseUrl}/?page=strategy-datasets&accept=fujing-v2-${Date.now()}` });
await waitFor(`document.querySelector('.nav-tab[data-page="strategy-datasets"]') !== null`, "strategy dataset navigation", 90000);
await click('.nav-tab[data-page="strategy-datasets"]');
await waitFor(`document.querySelector('[data-sd-dataset="a_share_daily"]') !== null`, "a_share_daily dataset card", 90000);

await click('[data-sd-dataset="a_share_daily"]');
await waitFor(`document.querySelector("#sd-detail-view")?.hidden === false`, "dataset detail");
await click('[data-sd-tab="documentation"]');
await waitFor(`document.querySelector("#sd-doc-code") !== null`, "dataset documentation code");
const documentationEvidence = await evaluate(`({title:document.querySelector("#sd-detail-hero h3")?.textContent || "",codeLines:document.querySelector(".sd-documentation-code .sd-workbench-gutter")?.textContent.split("\\n").filter(Boolean).length || 0,theme:document.querySelector(".sd-documentation-code .sd-workbench-code")?.dataset.theme || ""})`);
await click('[data-sd-tab="examples"]');
await waitFor(`document.querySelector('[data-sd-instantiate="a_share_daily-strategy"]') !== null`, "dataset strategy example");
await click('[data-sd-instantiate="a_share_daily-strategy"]');
await waitFor(`document.querySelector("#strategy-draft-id")?.value.includes("a_share_daily")`, "dataset draft imported", 30000);
await waitFor(`document.querySelector('[data-param-key="execution_price"]') !== null`, "imported execution parameter", 30000);
const importedParameterKeys = await evaluate(`[...document.querySelectorAll("[data-param-key]")].map((node)=>node.dataset.paramKey)`);

await setValue("#strategy-draft-id", "fujing_v2");
await setValue("#strategy-draft-name", "拂经v2");
await setValue("#strategy-draft-description", "通达信拂经v2的本地可执行适配：引用 a_share_daily；WINNER 使用120日成交量加权典型价近似，TROUGHBARS 使用因果滚动低点近似；收盘确认后次日开盘交易，量比排序由共享组合模式取前3名，95%最高价移动止盈止损。");
await setValue("#strategy-editor", strategySource);
await setValue('[data-param-key="position_size"]', "1");
await setValue('[data-param-key="execution_price"]', "open");
await click("#strategy-validate");
await waitFor(`document.querySelector("#strategy-validation-output")?.textContent.includes("校验通过")`, "strategy validation", 30000);
await click("#strategy-save-draft");
await waitFor(`typeof selectedStrategy !== "undefined" && selectedStrategy?.strategy_id === "fujing_v2" && selectedStrategy?.latest_version !== "未保存"`, "strategy saved", 60000);
const strategy = await evaluate(`({strategy_id:selectedStrategy.strategy_id,name:selectedStrategy.name,version:selectedStrategy.latest_version,version_count:selectedStrategy.version_count,source_sha256:selectedStrategy.source_sha256,parameters:selectedStrategy.parameters,datasetDeclared:selectedStrategy.source_code.includes('DATASET_REQUIREMENTS = ["a_share_daily"]')})`);

await click('[data-stage76-workspace="create"]');
await click('[data-stage76-mode="single"]');
await setCommonConfig();
await setValue('#backtest-run-form [name="symbol"]', "000858.XSHE");
await setValue('#backtest-run-form [name="benchmark"]', "000300.XSHG");
const previousSingle = await evaluate(`currentSingleTask?.task_id || ""`);
await click('#backtest-run-form button[type="submit"]');
const singleId = await waitFor(`(() => currentSingleTask?.task_id && currentSingleTask.task_id !== ${JSON.stringify(previousSingle)} ? currentSingleTask.task_id : "")()`, "single task created", 60000);
const singleTask = await pollTask(`/api/backtest/single-backtest-tasks/${encodeURIComponent(singleId)}`, "single backtest");
const singleUi = await inspectResult("single");

await click('[data-stage76-workspace="create"]');
await click('[data-stage76-mode="independent"]');
await setCommonConfig();
await setValue('#screening-task-form [name="symbols"]', symbols);
await setValue('#screening-task-form [name="symbol_limit"]', "8");
await setValue('#screening-task-form [name="max_workers"]', "4");
const previousIndependent = await evaluate(`currentScreeningTaskId || ""`);
await click('#screening-task-form button[type="submit"]');
const independentId = await waitFor(`(() => currentScreeningTaskId && currentScreeningTaskId !== ${JSON.stringify(previousIndependent)} ? currentScreeningTaskId : "")()`, "independent task created", 90000);
await click("#screening-task-run");
const independentTask = await pollTask(`/api/backtest/independent-screening-tasks/${encodeURIComponent(independentId)}`, "independent backtest");
const independentUi = await inspectResult("independent");

await click('[data-stage76-workspace="create"]');
await click('[data-stage76-mode="portfolio"]');
await setCommonConfig();
await setValue('#portfolio-task-form [name="symbols"]', symbols);
await setValue('#portfolio-task-form [name="symbol_limit"]', "8");
await setValue('#portfolio-task-form [name="max_positions"]', "3");
await setValue('#portfolio-task-form [name="portfolio_exposure"]', "1");
await setValue('#portfolio-task-form [name="max_workers"]', "4");
const previousPortfolio = await evaluate(`currentPortfolioTaskId || ""`);
await click('#portfolio-task-form button[type="submit"]');
const portfolioId = await waitFor(`(() => currentPortfolioTaskId && currentPortfolioTaskId !== ${JSON.stringify(previousPortfolio)} ? currentPortfolioTaskId : "")()`, "portfolio task created", 90000);
await click("#portfolio-task-run");
const portfolioTask = await pollTask(`/api/backtest/shared-portfolio-tasks/${encodeURIComponent(portfolioId)}`, "shared portfolio backtest");
const portfolioUi = await inspectResult("portfolio");

const singlePanel = await api(`/api/backtest/results/${encodeURIComponent(singleTask.run_id)}/panel`);
const portfolioPanel = await api(`/api/backtest/results/${encodeURIComponent(portfolioTask.run_id)}/panel`);
const independentReport = await api(`/api/reporting/backtest-modes/independent-screening/${encodeURIComponent(independentId)}`);
const portfolioReport = await api(`/api/reporting/backtest-modes/shared-portfolio/${encodeURIComponent(portfolioId)}`);

const output = {
  checks: {
    datasetDocumentationStyled: documentationEvidence.codeLines > 0 && Boolean(documentationEvidence.theme),
    datasetParametersImported: importedParameterKeys.includes("execution_price") && importedParameterKeys.includes("position_size"),
    strategySaved: strategy.strategy_id === "fujing_v2" && strategy.name === "拂经v2" && strategy.datasetDeclared,
    threeModesCompleted: [singleTask, independentTask, portfolioTask].every((task) => ["completed", "partial_completed"].includes(task.status)),
    reportsOpened: [singleUi, independentUi, portfolioUi].every((item) => item.reportText.length > 80),
    portfolioTopThreeConfigured: Number(portfolioTask.config?.max_positions || portfolioTask.max_positions) === 3,
    openExecutionRecorded: portfolioUi.executionModes.includes("open"),
    noRuntimeExceptions: exceptions.length === 0,
  },
  dataset: { documentationEvidence, importedParameterKeys },
  strategy,
  tasks: {
    single: { task: singleTask, panel: singlePanel.result || singlePanel.panel || singlePanel, ui: singleUi },
    independent: { task: independentTask, report: independentReport.report || independentReport, ui: independentUi },
    portfolio: { task: portfolioTask, panel: portfolioPanel.result || portfolioPanel.panel || portfolioPanel, report: portfolioReport.report || portfolioReport, ui: portfolioUi },
  },
  exceptions,
};
if (Object.values(output.checks).some((value) => value !== true)) {
  throw new Error(JSON.stringify(output, null, 2));
}
console.log(JSON.stringify(output, null, 2));
socket.close();
