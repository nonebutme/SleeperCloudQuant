// 执行当前页面函数，验证克隆、乱序响应、轮询和分页；不访问正式服务。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = readFileSync(resolve(root, 'web/app.js'), 'utf8');
function code(name) {
  const pattern = new RegExp('^([ \\t]*)(?:async )?function ' + name + '\\([^\\n]*\\) *\\{[\\s\\S]*?^\\1\\}', 'm');
  const match = source.match(pattern);
  assert.ok(match, `missing page function ${name}`);
  return match[0];
}
const noop = () => {};
const nodes = {};
const node = (id) => nodes[id] ||= { innerHTML: '', textContent: '', querySelectorAll: () => [], dispatchEvent: noop };
let parameterInput = { dataset: { paramKey: 'period' }, type: 'number', value: '99' };
const c = {
  console, Event: class {}, document: { querySelectorAll: (s) => s === '[data-param-key]' ? [parameterInput] : [], querySelector: node },
  $: node, window: {}, currentBacktestView: 'single', stage76SelectedTask: null, stage76TaskCatalog: [],
  stage76TaskPollTimer: 1, stage76TaskTotal: 0, stage76TaskPage: 1, stage76TaskPageSize: 20,
  stage76TaskRequestSequence: 0, backtestResultSelectionSequence: 0, backtestTableRequestSequence: 0,
  stage76ActionSequence: 0, stage76ReportRequestSequence: 0,
  currentSingleTask: null, currentScreeningTask: null, currentPortfolioTask: null,
  selectedStrategy: { strategy_id: 'B', parameter_schema: {} }, activateBacktestView: noop,
  updateStage75Url: noop, newTaskId: () => 'new', setFeedback: noop, renderStage76TaskTable: noop,
  renderSummaryGrid: noop, renderTaskProgress: noop, renderBacktestDataVersion: noop, renderSeriesChart: noop,
  renderTable: () => '', shortTechnicalId: (x) => x, openStage75ResultDock: noop,
  buildQuery: (o) => new URLSearchParams(o).toString(), currentBacktestResultRunId: '', currentBacktestRunIdPrefix: '',
  currentBacktestTableLimit: 50, currentBacktestTableOffset: 0,
  setTimeout: () => { c.timerScheduled = true; return 2; }, clearTimeout: () => { c.timerCleared = true; },
  FormData: class { entries() { return [['status', 'completed']][Symbol.iterator](); } },
  renderStage76ResultDetails: (r) => { c.displayedRun = r.summary?.run_id; },
  coerceParameterValue: Number, escapeHtml: String, saveStage75Draft: noop,
  setStage76ModeTaskState: noop, backtestStatusInfo: () => ({ label: '运行中' }),
  renderScreeningTask: noop, renderPortfolioTask: noop,
  selectStrategy: async (strategy) => { c.selectedStrategy = strategy; parameterInput.value = String(strategy.parameters.period); },
};
vm.createContext(c);
for (const name of ['fillStage75TaskForm', 'restoreClonedBacktestConfig', 'syncStage76CommonFields', 'activateStage76CreateMode',
  'activateStage76Workspace', 'handleStage76TaskAction', 'collectStrategyParameters', 'loadStage76Tasks',
  'loadBacktestResultPanel', 'loadBacktestResultTable', 'loadIndependentScreeningResultWorkspace']) vm.runInContext(code(name), c);

const form = node('#backtest-run-form');
form.elements = {};
for (const key of ['run_id', 'strategy_id', 'strategy_version', 'start_date', 'end_date', 'adjustment', 'initial_cash', 'commission_rate']) form.elements[key] = { value: '' };
for (const [key, value] of Object.entries({ start: '2026-01-01', end: '2026-10-01', adjustment: 'raw', cash: '200000' })) node('#backtest-common-' + key).value = value;
const original = { strategy_id: 'A', strategy_version: 'v3', date_window: { start_date: '2020-01-01', end_date: '2020-12-31' },
  adjustment: 'qfq', initial_cash: 10000, parameters: { period: 5, factor_artifact_id: 'frozen-artifact' }, extra_config: { rqalpha_local: { commission_rate: .002 } } };
c.requestJson = async (url) => url.endsWith('/versions') ? { versions: [{ strategy_id: 'A', latest_version: 'v3', parameters: {} }] } : { task: { config: original } };
await c.handleStage76TaskAction({ mode: 'single', links: { detail: '/mock' } }, 'clone');
assert.equal(form.elements.start_date.value, '2020-01-01');
assert.equal(form.elements.adjustment.value, 'qfq');
assert.equal(Number(form.elements.initial_cash.value), 10000);
assert.equal(form.elements.commission_rate.value, .002);
assert.equal(c.selectedStrategy.latest_version, 'v3');
assert.equal(c.selectedStrategy.strategy_id, 'A');
assert.equal(c.collectStrategyParameters().period, 5);
assert.equal(c.collectStrategyParameters().factor_artifact_id, 'frozen-artifact');
c.requestJson = async () => ({ versions: [] });
await assert.rejects(() => c.restoreClonedBacktestConfig('single', original), /策略版本不可用/);

// 筛选结果不含当前运行任务，也必须继续刷新；获取到终态后停止。
c.currentSingleTask = { task_id: 'active', status: 'running' };
c.requestJson = async (url) => url.includes('/mode-tasks?') ? { tasks: [], summary: {} } : { task: { task_id: 'active', status: 'running' } };
await c.loadStage76Tasks();
assert.equal(c.timerScheduled, true);
c.timerScheduled = false;
c.requestJson = async (url) => url.includes('/mode-tasks?') ? { tasks: [], summary: {} } : { task: { task_id: 'active', status: 'completed' } };
await c.loadStage76Tasks();
assert.equal(c.currentSingleTask.status, 'completed');
assert.equal(c.timerScheduled, false);

// A 的旧响应不得覆盖 B，分页请求也不能串到另一个 Run。
let releaseA;
c.requestJson = (url) => url.includes('/A/panel') ? new Promise((resolve) => { releaseA = resolve; })
  : Promise.resolve(url.includes('/B/panel') ? { result: { summary: { run_id: 'B' } } } : { result: { rows: [], total: 0 } });
const requestA = c.loadBacktestResultPanel('A');
await c.loadBacktestResultPanel('B');
releaseA({ result: { summary: { run_id: 'A' } } });
assert.equal(await requestA, null);
assert.equal(c.currentBacktestResultRunId, 'B');
assert.equal(c.displayedRun, 'B');
let releaseTable;
c.requestJson = () => new Promise((resolve) => { releaseTable = resolve; });
const oldTable = c.loadBacktestResultTable(0);
c.currentBacktestResultRunId = 'C';
releaseTable({ result: { rows: [{ side: 'OLD' }], total: 1 } });
assert.equal(await oldTable, null);

const calls = [];
c.independentResultSelector = () => node('#selector');
c.loadBacktestResultPanel = async (id) => id;
c.requestJson = async (url) => {
  calls.push(url);
  const offset = Number(new URL('http://local' + url).searchParams.get('offset'));
  return { result: { total: 150, items: Array.from({ length: offset === 0 ? 100 : 50 }, (_, i) => ({ run_id: 'run-' + (offset + i), symbol: 'S' + (offset + i) })) } };
};
assert.equal(await c.loadIndependentScreeningResultWorkspace({ task_id: 'batch' }, 'run-149'), 'run-149');
assert.equal((node('#selector').innerHTML.match(/data-independent-result-run=/g) || []).length, 150);
assert.equal(calls.length, 2);

let directoryUrl;
c.stage76TaskPage = 11;
c.requestJson = async (url) => { directoryUrl = url; return { tasks: [{ task_id: 'old', status: 'completed' }], summary: { task_count: 201 } }; };
await c.loadStage76Tasks();
assert.ok(directoryUrl.includes('offset=200'));
assert.equal(c.stage76TaskTotal, 201);

vm.runInContext(readFileSync(resolve(root, 'web/report-ui.js'), 'utf8'), c);
c.window.ReportUI.updateHeader({ mode: 'single', benchmark: '000300.XSHG', symbol: 'A' }, { benchmark_alignment: { mode: 'same_symbol_buy_hold' }, metrics: { benchmark_return: .1 } });
assert.match(node('#report-benchmark-select').innerHTML, /买入持有（非指数）/);
assert.doesNotMatch(node('#report-benchmark-status').textContent, /真实基准已对齐/);
c.window.ReportUI.updateHeader({ benchmark: '000300.XSHG' }, { metrics: { benchmark_return: .1 } });
assert.match(node('#report-benchmark-status').textContent, /缺少/);
c.window.ReportUI.updateHeader({ benchmark: '000300.XSHG' }, { benchmark_status: 'ready', benchmark_curve: [{ value: 1 }, { value: 1.1 }] });
assert.equal(node('#report-benchmark-status').textContent, '真实基准已对齐');
console.log('backtest UI audit regressions passed: clone, response ordering, polling, result pagination, history pagination, benchmark evidence');
