const pageTitles = { dashboard: "总览工作台", market: "数据中心", factor: "因子分析", backtest: "策略回测", ai: "AI 分析", reporting: "报告中心", config: "配置中心", traceability: "重构溯源" };
const acceptanceMatrix = [
  ["数据中心", "已实现可验收", "K线图、OHLC 表、交易日历、同步状态；已接入 SleeperCloudQuant-old 本地 SQLite 行情源，外部 provider 已有接入门禁，未配置密钥时 fallback。"],
  ["因子分析", "已实现可验收", "因子库、股票池、截面摘要、Top N；真实因子库扩展待接入。"],
  ["策略回测", "已实现可验收", "策略库、编辑、版本、参数扫描、结果报告；已接入本地 SQLite 行情驱动 runtime，真实 rqalpha 包已有探测门禁，未安装时 fallback。"],
  ["AI 分析", "已实现可验收", "TradingAgents 风格 workflow、配置驱动、历史留痕；已接入外部 LLM Provider 网关，未配置密钥时 fallback。"],
  ["报告中心", "已实现可验收", "7维报告、快照、AI联动、研究报告包、manifest、HTML/JSON/PDF/Word导出。"],
  ["配置中心", "已实现可验收", "数据源、LLM、Agent、运行时草稿；真实密钥管理不在 MVP 范围。"],
  ["重构溯源", "已实现可验收", "五仓库来源矩阵、采纳方式和新项目落点已在页面展示。"],
];
const sourceMatrix = [
  ["本地 A 股数据中心", "SleeperCloudQuant-old + TradingAgents-CN-main", "直接采纳/改造后采纳", "data_platform / app.api.market", "数据中心"],
  ["因子分析库", "SleeperCloudQuant-old + vnpy/backtrader 语义参考", "自建为主/体验参考", "factor_lab / app.api.factor", "因子分析"],
  ["策略回测库", "SleeperCloudQuant-old + rqalpha + vnpy", "直接采纳/语义对齐", "backtest_kernel / app.api.backtest", "策略回测"],
  ["AI 分析报告", "TradingAgents-CN-main", "改造后采纳", "AIAnalysisService / app.api.ai", "AI 分析"],
  ["回测分析报告", "SleeperCloudQuant-old", "直接采纳/改造后采纳", "reporting / app.api.reporting", "报告中心"],
  ["配置中心", "TradingAgents-CN-main + SleeperCloudQuant-old", "改造后采纳", "config_center / app.api.config", "配置中心"],
  ["轻量回测体验", "backtrader-master", "冻结参考", "Web 回测体验/指标展示", "策略回测"],
];
let selectedStrategy = null;
let strategyCatalog = [];
let currentScreeningTaskId = null;
let screeningPollTimer = null;
let currentPortfolioTaskId = null;
let portfolioPollTimer = null;
let currentModeTask = null;
let currentBacktestView = "overview";
let currentScreeningTask = null;
let currentPortfolioTask = null;
let modeTaskCatalog = [];
let singleRunTimer = null;
let singleRunState = {
  status: "idle",
  phase: "等待配置",
  runId: "",
  strategyName: "",
  symbol: "",
  startedAt: null,
  elapsedSeconds: 0,
  result: null,
  error: "",
};
const newStrategyTemplate = `def generate_target_weights(bars, parameters):
    position_size = float(parameters.get("position_size", 1.0))
    return [position_size for bar in bars]
`;
let currentReportRunId = "phase1-demo-run-001";
let currentReportExperimentId = "phase1-batch-001";
let currentScanRunIdPrefix = "";
let selectedReportPackageId = "";
let currentBacktestResultRunId = "";
let currentBacktestRunIdPrefix = "";
let currentBacktestTableOffset = 0;
let aShareWorkspaceLoaded = false;
const currentBacktestTableLimit = 5;
const $ = (selector) => document.querySelector(selector);
const globalFeedback = $("#global-feedback");

function setFeedback(message, kind = "") { globalFeedback.textContent = message; globalFeedback.className = kind ? `feedback is-${kind}` : "feedback"; }
function buildQuery(params) { const search = new URLSearchParams(); Object.entries(params).forEach(([key, value]) => { if (value !== "" && value != null) search.set(key, value); }); return search.toString(); }
async function requestJson(path, options = {}) { const response = await fetch(path, { method: options.method || "GET", headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) }, body: options.body }); const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || `请求失败 (${response.status})`); return payload; }
function activatePage(pageId) { document.querySelectorAll(".page-section").forEach((section) => section.classList.toggle("is-active", section.id === `page-${pageId}`)); document.querySelectorAll(".nav-tab").forEach((button) => button.classList.toggle("is-active", button.dataset.page === pageId)); $("#page-title").textContent = pageTitles[pageId] || "SleeperCloudQuant"; }
function financialToneForLabel(label, value) { const text = String(label || "").toLowerCase(); if (/(收益|回报|盈利|盈亏|年化|超额|return|profit|annual)/i.test(text)) return financialToneClass(value); if (/(回撤|亏损|损失|成本|drawdown|loss|cost)/i.test(text) && value !== "-" && value !== "--") return "market-fall"; return ""; }
function renderSummaryGrid(target, items) { target.innerHTML = items.map((item) => '<div class="summary-item ' + (item.tone || financialToneForLabel(item.label, item.value)) + '"><strong>' + item.label + '</strong><span>' + item.value + '</span></div>').join(""); }
function renderList(target, rows) { target.innerHTML = rows.length ? rows.map((item) => `<li>${item}</li>`).join("") : '<li class="empty-cell">暂无数据</li>'; }
function renderCards(target, rows, titleKey, bodyKey, metaKey) { target.innerHTML = rows.map((row) => `<article class="definition-item"><h4>${row[titleKey] || row.name || row.role || row.speaker}</h4><p>${row[bodyKey] || row.summary || row.argument || row.view || ""}</p><span>${row[metaKey] || row.status || row.stance || row.model || ""}</span></article>`).join("") || '<div class="empty-cell">暂无数据</div>'; }
function renderBarChart(target, rows, labelKey, valueKey) { if (!rows.length) { target.innerHTML = '<div class="empty-cell">暂无图表数据</div>'; return; } const max = Math.max(...rows.map((row) => Math.abs(Number(row[valueKey]) || 0)), 1); target.innerHTML = rows.map((row) => { const value = Number(row[valueKey]) || 0; const width = Math.max(6, Math.round(Math.abs(value) / max * 100)); return `<div class="bar-row"><span>${row[labelKey]}</span><div class="bar-track"><i style="width:${width}%"></i></div><strong>${value.toFixed(4)}</strong></div>`; }).join(""); }
function renderSeriesChart(target, rows, labelKey = "snapshot_time", valueKey = "value") {
  if (!target) return;
  if (!rows.length) { target.innerHTML = '<div class="empty-cell">暂无曲线数据</div>'; return; }
  const width = 860, height = 220, pad = 28;
  const values = rows.map((row) => Number(row[valueKey])).filter((value) => Number.isFinite(value));
  if (!values.length) { target.innerHTML = '<div class="empty-cell">暂无曲线数据</div>'; return; }
  const max = Math.max(...values), min = Math.min(...values); const span = max - min || 1;
  const x = (index) => pad + index / Math.max(rows.length - 1, 1) * (width - pad * 2);
  const y = (value) => pad + (max - Number(value)) / span * (height - pad * 2);
  const points = rows.map((row, index) => `${x(index)},${y(row[valueKey])}`).join(" ");
  const labels = rows.filter((_, index) => index === 0 || index === rows.length - 1).map((row, index) => `<text x="${index === 0 ? pad : width - pad}" y="${height - 6}" text-anchor="${index === 0 ? "start" : "end"}" class="axis-label">${String(row[labelKey] || "").slice(0, 10)}</text>`).join("");
  target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="收益曲线"><line x1="${pad}" x2="${width - pad}" y1="${pad}" y2="${pad}" class="grid-line"/><line x1="${pad}" x2="${width - pad}" y1="${height - pad}" y2="${height - pad}" class="grid-line"/><text x="4" y="${pad + 4}" class="axis-label">${max.toFixed(4)}</text><text x="4" y="${height - pad}" class="axis-label">${min.toFixed(4)}</text><polyline points="${points}" fill="none" stroke="#285f8f" stroke-width="3"/>${labels}</svg>`;
}
function renderBacktestDataVersion(result) {
  const summary = result?.summary || {};
  const trace = result?.data_asset_trace || {};
  const snapshot = result?.input_snapshot || {};
  const snapshotPayload = snapshot.payload || {};
  const asset = trace.asset || snapshotPayload.asset || {};
  const sourceCounts = asset.source_counts || snapshot.source_counts || {};
  renderSummaryGrid($("#backtest-data-version-summary"), [
    { label: "数据绑定", value: summary.data_asset_status || trace.status || "not_bound" },
    { label: "数据版本", value: summary.data_version || asset.data_version || snapshot.data_version || "-" },
    { label: "输入快照", value: summary.input_snapshot_id || snapshot.snapshot_id || "-" },
    { label: "质量", value: asset.quality_status || "-" },
    { label: "覆盖", value: asset.coverage_status || "-" },
    { label: "本地行数", value: asset.row_count ?? "-" },
    { label: "来源", value: Object.keys(sourceCounts).length ? JSON.stringify(sourceCounts) : "-" },
  ]);
  $("#backtest-input-snapshot-output").textContent = JSON.stringify({ input_snapshot: snapshot, data_asset_trace: trace }, null, 2);
}
function renderAssetConsistency(consistency = {}, target = $("#backtest-asset-consistency-summary")) {
  if (!target) return;
  renderSummaryGrid(target, [
    { label: "资产一致性", value: consistency.status || "empty" },
    { label: "Run 数", value: consistency.run_count ?? 0 },
    { label: "缺失", value: consistency.missing_count ?? 0 },
    { label: "版本数", value: consistency.data_version_count ?? 0 },
    { label: "快照数", value: consistency.snapshot_count ?? 0 },
    { label: "数据版本", value: (consistency.data_versions || []).join(", ") || "-" },
  ]);
}
function renderAcceptanceMatrix() {
  const target = $("#dashboard-acceptance");
  if (!target) return;
  target.innerHTML = acceptanceMatrix.map((row) => `<article class="definition-item"><h4>${row[0]}</h4><p>${row[2]}</p><span>${row[1]}</span></article>`).join("");
}
function renderTraceability() { $("#traceability-body").innerHTML = sourceMatrix.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join(""); $("#dashboard-sources").innerHTML = sourceMatrix.slice(0, 5).map((row) => `<article class="source-item"><strong>${row[0]}</strong><span>${row[1]}</span></article>`).join(""); }

function renderCandlestick(target, rows) {
  if (!rows.length) { target.innerHTML = '<div class="empty-cell">暂无 K 线数据</div>'; return; }
  const width = 860, height = 280, pad = 28;
  const highs = rows.map((r) => Number(r.high)); const lows = rows.map((r) => Number(r.low));
  const max = Math.max(...highs); const min = Math.min(...lows); const span = max - min || 1;
  const y = (value) => pad + (max - Number(value)) / span * (height - pad * 2);
  const step = (width - pad * 2) / rows.length;
  const candles = rows.map((row, index) => {
    const x = pad + index * step + step / 2; const openY = y(row.open); const closeY = y(row.close); const highY = y(row.high); const lowY = y(row.low);
    const up = Number(row.close) >= Number(row.open); const color = up ? "#c43d3d" : "#16845b"; const bodyY = Math.min(openY, closeY); const bodyH = Math.max(3, Math.abs(openY - closeY));
    return `<g><line x1="${x}" x2="${x}" y1="${highY}" y2="${lowY}" stroke="${color}" stroke-width="2"/><rect x="${x - Math.min(18, step * 0.28)}" y="${bodyY}" width="${Math.min(36, step * 0.56)}" height="${bodyH}" fill="${color}"/><text x="${x}" y="${height - 6}" text-anchor="middle" class="kline-label">${row.date.slice(5)}</text></g>`;
  }).join("");
  target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="K线图"><line x1="${pad}" x2="${width - pad}" y1="${pad}" y2="${pad}" class="grid-line"/><line x1="${pad}" x2="${width - pad}" y1="${height - pad}" y2="${height - pad}" class="grid-line"/><text x="4" y="${pad + 4}" class="axis-label">${max.toFixed(2)}</text><text x="4" y="${height - pad}" class="axis-label">${min.toFixed(2)}</text>${candles}</svg>`;
}

function formatMarketNumber(value) {
  if (value == null || value === "") return "-";
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(number) : String(value);
}

function renderAShareOverview(overview = {}) {
  const raw = overview.adjustments?.raw || {};
  $("#a-share-source-state").textContent = overview.status === "ready" ? (overview.read_only ? "只读源已连接" : "规范库已连接") : "数据源不可用";
  renderSummaryGrid($("#a-share-overview"), [
    { label: "当前股票", value: formatMarketNumber(overview.current_symbol_count) },
    { label: "历史覆盖代码", value: formatMarketNumber(overview.history_symbol_count) },
    { label: "历史/退市代码", value: formatMarketNumber(overview.history_only_symbol_count) },
    { label: "不复权日线", value: formatMarketNumber(raw.row_count) },
    { label: "数据区间", value: raw.min_date && raw.max_date ? raw.min_date + " 至 " + raw.max_date : "-" },
    { label: "数据库", value: overview.read_only ? "只读源库" : "项目规范库" },
  ]);
  const labels = { raw: "不复权", qfq: "前复权", hfq: "后复权" };
  $("#a-share-adjustment-body").innerHTML = Object.entries(overview.adjustments || {}).map(([mode, item]) => "<tr><td>" + (labels[mode] || mode) + "</td><td>" + formatMarketNumber(item.row_count) + "</td><td>" + formatMarketNumber(item.symbol_count) + "</td><td>" + (item.min_date || "-") + "</td><td>" + (item.max_date || "-") + "</td><td>" + formatMarketNumber(item.duplicate_row_count) + "</td><td>" + (item.fresh_coverage_pct ?? "-") + "%</td><td>" + (item.quality_status || "-") + "</td></tr>").join("") || '<tr><td colspan="8" class="empty-cell">暂无总览</td></tr>';
  $("#a-share-overview-output").textContent = JSON.stringify({ database_path: overview.database_path, database_size_bytes: overview.database_size_bytes, provider: overview.provider, acceptance_scope: overview.acceptance_scope }, null, 2);
}

async function loadAShareOverview() {
  const payload = await requestJson("/api/market/a-share/overview");
  renderAShareOverview(payload.overview || {});
  return payload.overview || {};
}

async function loadAShareSymbols(values = {}) {
  const payload = await requestJson("/api/market/a-share/symbols?" + buildQuery({ limit: 50, offset: 0, ...values }));
  const catalog = payload.catalog || {};
  renderSummaryGrid($("#a-share-symbol-summary"), [
    { label: "匹配数量", value: formatMarketNumber(catalog.total) },
    { label: "本页数量", value: formatMarketNumber((catalog.items || []).length) },
    { label: "偏移", value: catalog.offset ?? 0 },
    { label: "市场", value: catalog.market || "全部" },
  ]);
  $("#a-share-symbol-body").innerHTML = (catalog.items || []).map((item) => '<tr><td><button type="button" class="symbol-code-button" data-a-share-symbol="' + item.symbol + '">' + item.symbol + "</button></td><td>" + (item.name || "-") + "</td><td>" + item.market + "</td><td>" + item.rqalpha_symbol + "</td><td>" + item.listing_status + "</td></tr>").join("") || '<tr><td colspan="5" class="empty-cell">没有匹配股票</td></tr>';
  return catalog;
}

async function loadAShareDaily(values = {}) {
  const payload = await requestJson("/api/market/a-share/daily?" + buildQuery({ symbol: "000001", adjustment: "raw", limit: 120, offset: 0, ...values }));
  const daily = payload.daily || {};
  const rows = daily.rows || [];
  renderSummaryGrid($("#a-share-daily-summary"), [
    { label: "股票", value: (daily.symbol || "-") + " / " + (daily.market || "-") },
    { label: "复权口径", value: daily.adjustment || "-" },
    { label: "区间总行数", value: formatMarketNumber(daily.total) },
    { label: "本页", value: formatMarketNumber(rows.length) },
    { label: "去除重复", value: formatMarketNumber(daily.duplicate_rows_removed) },
    { label: "来源", value: daily.provider || daily.source || "-" },
  ]);
  renderCandlestick($("#a-share-daily-chart"), [...rows].reverse());
  $("#a-share-daily-body").innerHTML = rows.map((row) => { const tone = financialToneClass(row.change_pct); return "<tr><td>" + row.date + "</td><td>" + row.open + "</td><td>" + row.high + "</td><td>" + row.low + "</td><td>" + row.close + "</td><td>" + formatMarketNumber(row.volume) + "</td><td>" + formatMarketNumber(row.amount) + "</td><td class='" + tone + "'>" + (row.change_pct ?? "-") + "</td><td>" + (row.turnover_rate ?? "-") + "</td></tr>"; }).join("") || '<tr><td colspan="9" class="empty-cell">该区间没有行情</td></tr>';
  $("#a-share-daily-output").textContent = JSON.stringify({ status: daily.status, read_only: daily.read_only, symbol: daily.symbol, adjustment: daily.adjustment, total: daily.total, duplicate_rows_removed: daily.duplicate_rows_removed, limit: daily.limit, offset: daily.offset }, null, 2);
  return daily;
}

async function loadAShareWorkspace() {
  const dailyForm = $("#a-share-daily-form");
  const symbolForm = $("#a-share-symbol-form");
  await Promise.all([
    loadAShareDaily(Object.fromEntries(new FormData(dailyForm).entries())),
    loadAShareSymbols(Object.fromEntries(new FormData(symbolForm).entries())),
  ]);
  await loadAShareOverview();
  aShareWorkspaceLoaded = true;
}

function renderLocalPriceBarAssets(payload = {}) {
  const assets = payload.assets || [];
  const target = $("#market-assets-list");
  if (!target) return;
  target.innerHTML = assets.map((item) => `<article class="definition-item"><h4>${item.symbol}</h4><p>${item.start_date || "-"} 至 ${item.end_date || "-"}；${item.row_count || 0} 行；来源 ${Object.entries(item.source_counts || {}).map(([key, value]) => `${key}:${value}`).join(", ") || "-"}</p><span>${item.quality_status || "unknown"} / ${item.data_version || "-"}</span></article>`).join("") || '<div class="empty-cell">暂无本地数据资产</div>';
  const manifestTarget = $("#market-assets-output");
  if (manifestTarget) manifestTarget.textContent = JSON.stringify({ asset_count: payload.asset_count || 0, generated_at: payload.generated_at, manifest: payload.manifest || {}, assets }, null, 2);
}
function compactParams(params) {
  return Object.fromEntries(Object.entries(params || {}).filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== ""));
}
function renderBacktestAssetDirectory(payload = {}) {
  const assets = payload.assets || [];
  const summary = payload.summary || {};
  const summaryTarget = $("#backtest-asset-directory-summary");
  if (summaryTarget) renderSummaryGrid(summaryTarget, [
    { label: "状态", value: summary.status || "unknown" },
    { label: "资产数", value: summary.asset_count ?? assets.length },
    { label: "Symbols", value: (summary.symbols || []).join(", ") || "-" },
    { label: "Datasets", value: (summary.datasets || []).join(", ") || "-" },
    { label: "质量", value: (summary.quality_statuses || []).join(", ") || "-" },
    { label: "覆盖", value: (summary.coverage_statuses || []).join(", ") || "-" },
  ]);
  const listTarget = $("#backtest-asset-directory-list");
  if (listTarget) listTarget.innerHTML = assets.map((item) => `<article class="definition-item"><h4>${item.symbol || "-"} / ${item.dataset || "-"}</h4><p>${item.start_date || "-"} 至 ${item.end_date || "-"}；${item.row_count || 0} 行；更新 ${item.updated_at || "-"}</p><span>${item.quality_status || "unknown"} / ${item.coverage_status || "unknown"} / ${item.data_version || "-"}</span></article>`).join("") || '<div class="empty-cell">暂无回测资产目录记录</div>';
  const output = $("#backtest-asset-directory-output");
  if (output) output.textContent = JSON.stringify(payload, null, 2);
}
async function loadBacktestAssetDirectory(params = {}) {
  const query = buildQuery(compactParams({ limit: 50, ...params }));
  const payload = await requestJson(`/api/backtest/data-assets?${query}`);
  renderBacktestAssetDirectory(payload);
  return payload;
}
async function migrateBacktestInputSnapshots(dryRun = true) {
  const form = $("#backtest-asset-directory-form");
  const values = form ? Object.fromEntries(new FormData(form).entries()) : {};
  const payload = compactParams({ run_id_prefix: values.run_id_prefix || "", dry_run: dryRun, limit: values.limit || 100 });
  const result = await requestJson("/api/backtest/data-assets/migrate-input-snapshots", { method: "POST", body: JSON.stringify(payload) });
  $("#backtest-asset-migration-output").textContent = JSON.stringify(result.result || {}, null, 2);
  await loadBacktestAssetDirectory(values);
  return result.result;
}
function renderMarketDataBrowser(browser = {}) {
  const symbols = browser.symbols || [];
  const bars = browser.bars || [];
  const quality = browser.quality || {};
  const syncRuns = browser.sync_runs || [];
  const symbolsTarget = $("#market-browser-symbols");
  if (!symbolsTarget) return;
  symbolsTarget.innerHTML = symbols.map((item) => `<article class="definition-item"><h4>${item.symbol}</h4><p>${item.min_date || "-"} 至 ${item.max_date || "-"}；${item.row_count || 0} 行</p><span>${item.last_synced_at || "未同步"}</span></article>`).join("") || '<div class="empty-cell">暂无本地 symbol</div>';
  renderCandlestick($("#market-browser-chart"), bars);
  $("#market-browser-body").innerHTML = bars.map((row) => `<tr><td>${row.date}</td><td>${row.open}</td><td>${row.high}</td><td>${row.low}</td><td>${row.close}</td><td>${row.volume}</td><td>${row.source || "-"}</td></tr>`).join("") || '<tr><td colspan="7" class="empty-cell">暂无本地行情</td></tr>';
  $("#market-browser-output").textContent = JSON.stringify({ selected_symbol: browser.selected_symbol, quality, sync_runs: syncRuns }, null, 2);
}
async function loadMarket(params = { symbol: "000001.XSHE", start_date: "2020-01-02", end_date: "2020-01-10" }) {
  const query = buildQuery(params);
  const [prices, calendar, syncStatus, localBars, quality, browserPayload, assetsPayload] = await Promise.all([requestJson(`/api/market/price-history?${query}`), requestJson(`/api/market/trading-calendar?start_date=${params.start_date}&end_date=${params.end_date}`), requestJson("/api/market/sync-status/price_history"), requestJson(`/api/market/local-price-bars?${query}`), requestJson(`/api/market/local-price-bars/quality?${query}`), requestJson(`/api/market/data-browser?${query}`), requestJson(`/api/market/local-price-bars/assets?${buildQuery({ symbol: params.symbol, limit: 20 })}`)]);
  const rows = prices.rows || [];
  $("#price-history-body").innerHTML = rows.map((row) => `<tr><td>${row.date}</td><td>${row.open}</td><td>${row.high}</td><td>${row.low}</td><td>${row.close}</td><td>${row.volume}</td></tr>`).join("") || '<tr><td colspan="6" class="empty-cell">暂无行情</td></tr>';
  renderCandlestick($("#candlestick-chart"), rows); renderList($("#trading-calendar-list"), calendar.days || []);
  const status = syncStatus.status || {}; const trace = prices.source_trace || {}; const lastCall = trace.last_call || {}; const primary = trace.primary || {}; const providerLastCall = primary.last_call || {}; renderSummaryGrid($("#market-status"), [{ label: "标的", value: prices.symbol || params.symbol }, { label: "行情行数", value: rows.length }, { label: "交易日", value: (calendar.days || []).length }, { label: "选用来源", value: lastCall.selected_source || (rows.length > 2 ? "fallback" : "demo") }, { label: "切换原因", value: lastCall.reason || "未记录" }, { label: "外部Provider", value: `${primary.provider || "unknown"} / ${primary.status || "unknown"}` }, { label: "外部请求", value: providerLastCall.status ? `${providerLastCall.status} / ${providerLastCall.reason || ""}` : "未调用或未配置" }, { label: "行数对比", value: `${lastCall.primary_row_count ?? "-"} / ${lastCall.fallback_row_count ?? "-"}` }]);
  const localStatus = localBars.storage_status || {}; const qualityReport = quality.report || {}; renderSummaryGrid($("#market-local-storage-status"), [{ label: "本地行数", value: localStatus.row_count ?? 0 }, { label: "最早日期", value: localStatus.min_date || "-" }, { label: "最晚日期", value: localStatus.max_date || "-" }, { label: "最近落库", value: localStatus.last_synced_at || "-" }, { label: "质量状态", value: qualityReport.status || "unknown" }, { label: "缺口", value: qualityReport.missing_count ?? 0 }, { label: "异常", value: qualityReport.invalid_count ?? 0 }]); $("#market-local-bars-output").textContent = JSON.stringify({ symbol: localBars.symbol, rows: localBars.rows || [] }, null, 2); $("#market-quality-output").textContent = JSON.stringify(qualityReport, null, 2); renderMarketDataBrowser(browserPayload.browser || {}); renderLocalPriceBarAssets(assetsPayload.assets || {});
  return { rows, calendar, status };
}

async function repairMarketGaps() {
  const form = $("#market-query-form");
  const values = form ? Object.fromEntries(new FormData(form).entries()) : { symbol: "000001.XSHE", start_date: "2020-01-02", end_date: "2020-01-10" };
  const payload = await requestJson("/api/market/local-price-bars/repair-gaps", { method: "POST", body: JSON.stringify(values) });
  $("#market-quality-output").textContent = JSON.stringify(payload.result || {}, null, 2);
  await loadMarket(values);
  setFeedback(`缺口修复完成：${payload.result?.status || "unknown"}`, payload.result?.after?.status === "passed" ? "success" : "error");
}
async function loadFactors(params = { index_code: "000300.XSHG", trade_date: "2020-01-02", factor_id: "close_to_ma2_bias" }) {
  const [definitions, pool, ranking, summary] = await Promise.all([requestJson("/api/factors/definitions"), requestJson(`/api/factors/pool-members?${buildQuery({ index_code: params.index_code, date: params.trade_date })}`), requestJson(`/api/factors/top-n?${buildQuery({ factor_id: params.factor_id, trade_date: params.trade_date, start_date: "2020-01-01", end_date: params.trade_date, limit: 5, descending: true })}`), requestJson(`/api/factors/cross-section-summary?${buildQuery({ index_code: params.index_code, date: params.trade_date, trade_date: params.trade_date, start_date: "2020-01-01", end_date: params.trade_date })}`)]);
  renderCards($("#factor-definitions-list"), definitions.definitions || [], "factor_id", "name", "version"); renderList($("#factor-pool-list"), pool.symbols || []);
  const rankingRows = ranking.ranking?.rows || []; renderBarChart($("#factor-ranking-chart"), rankingRows, "symbol", "value"); $("#factor-summary-output").textContent = JSON.stringify({ ranking: ranking.ranking, cross_section: summary.summaries }, null, 2);
  return { definitions, pool, ranking, summary };
}

function renderExperimentIndex(experiments = []) {
  const target = $("#backtest-experiment-index-list");
  if (!target) return;
  target.innerHTML = experiments.map((item) => `<article class="definition-item"><h4>${item.name || item.experiment_id}</h4><p>${item.run_id_prefix || "-"}；${(item.tags || []).join(", ")}</p><span>${item.status || "unknown"} / ${item.primary_run_id || "无主 run"}</span><button type="button" data-experiment-review="${item.experiment_id || item.run_id_prefix}">生成复盘</button></article>`).join("") || '<div class="empty-cell">暂无实验索引</div>';
  document.querySelectorAll("[data-experiment-review]").forEach((button) => button.addEventListener("click", () => createExperimentReviewPackage(button.dataset.experimentReview)));
}
async function loadExperimentIndex() {
  const payload = await requestJson("/api/backtest/experiments");
  renderExperimentIndex(payload.experiments || []);
  $("#backtest-experiment-index-output").textContent = JSON.stringify(payload.experiments || [], null, 2);
  return payload.experiments || [];
}
async function createExperimentReviewPackage(experimentId) {
  if (!experimentId) return null;
  const payload = await requestJson(`/api/reporting/experiments/${encodeURIComponent(experimentId)}/review-package`, {
    method: "POST",
    body: JSON.stringify({ title: `${experimentId} 实验复盘报告包`, create_package: true })
  });
  const review = payload.review || {};
  const target = $("#backtest-experiment-review-output") || $("#backtest-experiment-index-output");
  target.textContent = JSON.stringify(review, null, 2);
  if (review.primary_run_id) {
    currentReportRunId = review.primary_run_id;
    selectedReportPackageId = review.report_package?.package_id || selectedReportPackageId;
  }
  setFeedback(`实验复盘已生成：${review.experiment_id || experimentId}`, review.status === "review_ready" ? "success" : "error");
  return review;
}
async function createCurrentExperimentIndex() {
  const prefix = currentBacktestRunIdPrefix || (currentBacktestResultRunId ? currentBacktestResultRunId.replace(/-\d+$/, "") : "web-manual-experiment");
  const payload = await requestJson("/api/backtest/experiments", { method: "POST", body: JSON.stringify({ run_id_prefix: prefix, name: `Web 实验 ${prefix}`, tags: ["web", "manual"], primary_run_id: currentBacktestResultRunId || null }) });
  $("#backtest-experiment-index-output").textContent = JSON.stringify(payload.experiment || {}, null, 2);
  await loadExperimentIndex();
  setFeedback(`实验索引已登记：${payload.experiment?.experiment_id || prefix}`, "success");
}
const backtestStatusMap = {
  idle: { label: "尚未执行", tone: "idle" },
  ready: { label: "待执行", tone: "ready" },
  pending: { label: "排队中", tone: "running" },
  running: { label: "运行中", tone: "running" },
  pause_requested: { label: "正在暂停", tone: "running" },
  paused: { label: "已暂停", tone: "paused" },
  interrupted: { label: "已中断", tone: "warning" },
  cancel_requested: { label: "正在取消", tone: "warning" },
  canceled: { label: "已取消", tone: "muted" },
  completed: { label: "已完成", tone: "success" },
  partial_completed: { label: "部分完成", tone: "warning" },
  partial_failed: { label: "部分失败", tone: "danger" },
  failed: { label: "失败", tone: "danger" },
  loading_result: { label: "载入结果", tone: "running" },
};

function backtestStatusInfo(status) {
  return backtestStatusMap[status] || { label: status || "未知", tone: "muted" };
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value) || 0));
}

function formatTaskSeconds(value) {
  const seconds = Math.max(0, Number(value) || 0);
  if (seconds < 60) return seconds.toFixed(seconds < 10 ? 1 : 0) + " 秒";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  if (minutes < 60) return minutes + " 分 " + remainder + " 秒";
  return Math.floor(minutes / 60) + " 小时 " + (minutes % 60) + " 分";
}

function formatTaskTimestamp(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ").slice(0, 19);
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(date).replaceAll("/", "-");
}

function taskElapsedSeconds(task = {}) {
  const raw = Number(task.progress?.elapsed_seconds || 0);
  if (raw > 0) return raw;
  if (!task.started_at) return 0;
  const start = new Date(task.started_at).getTime();
  const end = task.finished_at ? new Date(task.finished_at).getTime() : Date.now();
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max((end - start) / 1000, 0) : 0;
}

function newTaskId(prefix) {
  const now = new Date();
  const stamp = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, "0"), String(now.getDate()).padStart(2, "0"),
    String(now.getHours()).padStart(2, "0"), String(now.getMinutes()).padStart(2, "0"), String(now.getSeconds()).padStart(2, "0")].join("");
  return prefix + "-" + stamp + "-" + Math.random().toString(36).slice(2, 6);
}

function shortTechnicalId(value) {
  const text = String(value || "");
  if (!text) return "-";
  if (text.length <= 22) return text;
  return text.slice(0, 12) + "..." + text.slice(-6);
}

function strategyDisplayName(strategyId) {
  const id = String(strategyId || "");
  return strategyCatalog.find((item) => item.strategy_id === id)?.name || id || "未命名策略";
}

function taskDisplayTitle(task = {}) {
  const binding = task.strategy_binding || {};
  const strategyId = binding.strategy_id || task.config?.strategy_id || "";
  const strategy = binding.strategy_name || strategyDisplayName(strategyId);
  const mode = task.mode_label || (task.mode === "shared-portfolio" ? "共享资金池" : "独立选股");
  return task.name || (strategy + " · " + mode);
}

function taskExecutionLabel(task = {}) {
  return "创建于 " + formatTaskTimestamp(task.created_at) + " · 批次 " + shortTechnicalId(task.task_id);
}

function financialToneClass(value) {
  const number = Number(String(value ?? "").replace("%", ""));
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "market-rise" : "market-fall";
}

function taskProgressModel(task = {}, mode = "") {
  const status = task.status || "idle";
  const raw = task.progress || {};
  const total = Number(raw.total ?? task.universe_count ?? task.universe?.length ?? 0);
  let processed = Number(raw.processed ?? 0);
  let percent = clampPercent(raw.percent);
  if (!raw.percent && ["completed", "partial_completed", "partial_failed", "canceled"].includes(status)) {
    processed = processed || total;
    percent = 100;
  }
  const indeterminate = ["pending", "running", "pause_requested", "cancel_requested", "loading_result"].includes(status) && percent <= 0;
  let phase = "尚未创建任务";
  if (status === "ready") phase = "任务已创建，等待启动";
  else if (status === "pending") phase = "任务已进入执行队列";
  else if (status === "running" && mode === "independent-screening") phase = "正在并发执行逐股策略";
  else if (status === "running" && mode === "shared-portfolio" && raw.phase === "preparing_symbols") phase = "正在逐股读取行情并计算策略信号";
  else if (status === "running" && mode === "shared-portfolio" && raw.phase === "simulating_account") phase = "股票准备完成，正在推进共享账户交易日";
  else if (status === "running" && mode === "shared-portfolio") phase = "正在执行共享资金池组合回测";
  else if (status === "paused") phase = "任务已暂停，可继续执行";
  else if (status === "completed") phase = "任务执行完成，结果可查看";
  else if (status === "partial_completed") phase = "任务完成，部分标的未完整执行";
  else if (status === "partial_failed") phase = "任务完成，但存在失败标的";
  else if (status === "failed") phase = task.error_message || "任务执行失败";
  else if (status === "canceled") phase = "任务已取消";
  return {
    status,
    percent,
    processed,
    total,
    phase,
    indeterminate,
    elapsed: taskElapsedSeconds(task),
    eta: raw.estimated_remaining_seconds,
    throughput: Number(raw.throughput_per_minute ?? 0),
  };
}

function renderTaskProgress(targetOrSelector, model = {}) {
  const target = typeof targetOrSelector === "string" ? $(targetOrSelector) : targetOrSelector;
  if (!target) return;
  const info = backtestStatusInfo(model.status);
  const percent = clampPercent(model.percent);
  const countText = model.total > 0 ? (model.processed || 0) + " / " + model.total : "阶段进度";
  const etaText = model.eta == null ? "" : "预计剩余 " + formatTaskSeconds(model.eta);
  const throughputText = model.throughput > 0 ? "吞吐 " + Number(model.throughput).toFixed(1) + "/分钟" : "";
  const meta = [countText, model.elapsed > 0 ? "已耗时 " + formatTaskSeconds(model.elapsed) : "", throughputText, etaText].filter(Boolean).join(" · ");
  target.className = "task-progress-shell is-" + info.tone + (model.indeterminate ? " is-indeterminate" : "");
  target.innerHTML =
    '<div class="task-progress-head"><div><strong>' + escapeHtml(info.label) + '</strong><span>' + escapeHtml(model.phase || "") + '</span></div>' +
    '<b>' + (model.indeterminate ? "执行中" : Math.round(percent) + "%") + '</b></div>' +
    '<div class="task-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + Math.round(percent) + '"><i style="width:' + percent + '%"></i></div>' +
    '<div class="task-progress-meta">' + escapeHtml(meta || "等待任务状态") + '</div>';
}

function renderSingleRunProgress() {
  const running = ["running", "loading_result"].includes(singleRunState.status);
  const elapsed = running && singleRunState.startedAt
    ? (Date.now() - singleRunState.startedAt) / 1000
    : singleRunState.elapsedSeconds;
  renderTaskProgress("#single-run-progress", {
    status: singleRunState.status,
    percent: singleRunState.status === "completed" ? 100 : 0,
    phase: singleRunState.phase,
    indeterminate: running,
    elapsed,
    processed: singleRunState.status === "completed" ? 1 : 0,
    total: 1,
  });
  const statusTarget = $("#single-run-status");
  if (statusTarget) statusTarget.textContent = backtestStatusInfo(singleRunState.status).label;
  renderActiveTaskOverview();
  renderBacktestResultsContext();
}

function setSingleRunState(patch) {
  singleRunState = { ...singleRunState, ...patch };
  if (singleRunTimer) {
    clearInterval(singleRunTimer);
    singleRunTimer = null;
  }
  if (["running", "loading_result"].includes(singleRunState.status)) {
    singleRunTimer = setInterval(renderSingleRunProgress, 500);
  }
  renderSingleRunProgress();
  renderBacktestWorkspace();
}

function taskCardHtml(task, index) {
  const mode = task.mode || "";
  const progress = taskProgressModel(task, mode);
  const status = backtestStatusInfo(task.status);
  const binding = task.strategy_binding || {};
  const dates = task.date_window || {};
  const elapsed = taskElapsedSeconds(task);
  const canRun = ["ready", "paused", "interrupted", "failed", "partial_failed"].includes(task.status);
  const canResult = ["completed", "partial_completed", "partial_failed"].includes(task.status);
  return '<article class="task-directory-item is-' + status.tone + '" data-mode-task-select="' + index + '">' +
    '<div class="task-directory-main"><div><span class="task-mode-label">' + escapeHtml(task.mode_label || mode) + '</span><h4>' + escapeHtml(taskDisplayTitle(task)) + '</h4><small>' + escapeHtml(taskExecutionLabel(task)) + '</small></div>' +
    '<span class="task-status-badge is-' + status.tone + '">' + escapeHtml(status.label) + '</span></div>' +
    '<p>' + escapeHtml(binding.strategy_version || "") + ' · ' + escapeHtml(dates.start_date || "-") + " 至 " + escapeHtml(dates.end_date || "-") + ' · ' + (task.universe_count || progress.total || 0) + ' 只' + (elapsed > 0 ? ' · 耗时 ' + escapeHtml(formatTaskSeconds(elapsed)) : '') + '</p>' +
    '<div class="task-card-progress"><div><i style="width:' + progress.percent + '%"></i></div><span>' + Math.round(progress.percent) + '% · ' + progress.processed + "/" + progress.total + '</span></div>' +
    '<div class="task-id-row"><span title="' + escapeHtml(task.task_id) + '">任务编号 ' + escapeHtml(shortTechnicalId(task.task_id)) + '</span>' + (task.run_id ? '<span title="' + escapeHtml(task.run_id) + '">回测编号 ' + escapeHtml(shortTechnicalId(task.run_id)) + '</span>' : '') + '</div>' +
    '<div class="task-directory-actions"><button type="button" data-mode-task-open="' + index + '">进入工作区</button>' +
    '<button type="button" data-mode-task-run="' + index + '"' + (canRun ? "" : " disabled") + '>启动 / 恢复</button>' +
    '<button type="button" data-mode-task-result="' + index + '"' + (canResult ? "" : " disabled") + '>查看结果</button></div></article>';
}

function activeModeTask(mode) {
  const selected = mode === "independent-screening" ? currentScreeningTask : currentPortfolioTask;
  return selected || modeTaskCatalog.find((task) => task.mode === mode) || null;
}

function modeOverviewItem(mode, title, view) {
  const task = activeModeTask(mode);
  if (!task) {
    return '<article class="task-mode-item"><div><span class="task-mode-label">' + title + '</span><h4>尚无任务</h4><p>进入工作区配置并创建任务。</p></div><button type="button" data-overview-view="' + view + '">开始配置</button></article>';
  }
  const progress = taskProgressModel(task, mode);
  const info = backtestStatusInfo(task.status);
  const elapsed = taskElapsedSeconds(task);
  return '<article class="task-mode-item is-' + info.tone + '"><div><span class="task-mode-label">' + title + '</span><h4>' + escapeHtml(taskDisplayTitle(task)) + '</h4><p>' + escapeHtml(info.label) + ' · ' + Math.round(progress.percent) + '% · ' + progress.processed + '/' + progress.total + (elapsed > 0 ? ' · ' + escapeHtml(formatTaskSeconds(elapsed)) : '') + '</p><small>' + escapeHtml(taskExecutionLabel(task)) + '</small></div><button type="button" data-overview-view="' + view + '">查看任务</button></article>';
}

function renderActiveTaskOverview() {
  const target = $("#backtest-task-overview-active");
  if (!target) return;
  const singleInfo = backtestStatusInfo(singleRunState.status);
  const singleTitle = singleRunState.runId ? ((singleRunState.strategyName || "单股策略") + " · " + (singleRunState.symbol || "-")) : "尚未执行";
  const singleDetail = singleRunState.symbol
    ? singleInfo.label + " · " + singleRunState.symbol + (singleRunState.elapsedSeconds ? " · " + formatTaskSeconds(singleRunState.elapsedSeconds) : "")
    : "选择股票后开始快速验证";
  target.innerHTML =
    '<article class="task-mode-item is-' + singleInfo.tone + '"><div><span class="task-mode-label">单股测试</span><h4>' + escapeHtml(singleTitle) + '</h4><p>' + escapeHtml(singleDetail) + '</p></div><button type="button" data-overview-view="single">进入测试</button></article>' +
    modeOverviewItem("independent-screening", "独立选股", "independent") +
    modeOverviewItem("shared-portfolio", "共享资金池", "portfolio");
  target.querySelectorAll("[data-overview-view]").forEach((button) => button.addEventListener("click", () => activateBacktestView(button.dataset.overviewView)));
}

function selectedResultContext() {
  if (currentModeTask) return { kind: "mode", task: currentModeTask };
  if (singleRunState.runId) return { kind: "single", task: singleRunState };
  const completed = modeTaskCatalog.find((task) => ["completed", "partial_completed", "partial_failed"].includes(task.status));
  return completed ? { kind: "mode", task: completed } : null;
}

function renderBacktestResultsContext() {
  const target = $("#backtest-results-context");
  const reportButton = $("#backtest-results-report");
  if (!target || !reportButton) return;
  const context = selectedResultContext();
  if (!context) {
    target.innerHTML = '<div class="empty-cell">请先完成或选择一个回测任务</div>';
    reportButton.disabled = true;
    return;
  }
  if (context.kind === "single") {
    const task = context.task;
    target.innerHTML = '<div class="results-context-main"><span class="task-mode-label">单股测试</span><h4>' + escapeHtml((task.strategyName || "单股策略") + " · " + (task.symbol || "-")) + '</h4><p title="' + escapeHtml(task.runId) + '">回测编号 ' + escapeHtml(shortTechnicalId(task.runId)) + ' · 已完成</p></div><span class="task-status-badge is-success">结果可查看</span>';
    reportButton.disabled = false;
    return;
  }
  const task = context.task;
  const info = backtestStatusInfo(task.status);
  const binding = task.strategy_binding || {};
  target.innerHTML = '<div class="results-context-main"><span class="task-mode-label">' + escapeHtml(task.mode_label || task.mode) + '</span><h4>' + escapeHtml(taskDisplayTitle(task)) + '</h4><p title="' + escapeHtml(task.task_id) + '">' + escapeHtml(binding.strategy_version || "-") + ' · 任务编号 ' + escapeHtml(shortTechnicalId(task.task_id)) + ' · 耗时 ' + escapeHtml(taskElapsedSeconds(task) > 0 ? formatTaskSeconds(taskElapsedSeconds(task)) : "-") + '</p></div><span class="task-status-badge is-' + info.tone + '">' + escapeHtml(info.label) + '</span>';
  reportButton.disabled = !["completed", "partial_completed", "partial_failed"].includes(task.status);
}

function activateBacktestView(view) {
  currentBacktestView = view;
  document.querySelectorAll("[data-backtest-view]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.backtestView === view));
  document.querySelectorAll("[data-backtest-view-target]").forEach((button) => {
    const active = button.dataset.backtestViewTarget === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  renderBacktestWorkspace();
  if (view === "overview") renderActiveTaskOverview();
  if (view === "results") renderBacktestResultsContext();
}

function renderBacktestWorkspace() {
  const target = $("#backtest-context-summary");
  if (!target) return;
  const strategyName = selectedStrategy?.name || selectedStrategy?.strategy_id || "尚未选择";
  const strategyVersion = selectedStrategy?.latest_version || "-";
  const viewNames = { overview: "任务总览", single: "单股测试", strategy: "策略库", independent: "独立选股", portfolio: "共享资金池", results: "结果分析" };
  const runningTask = [currentScreeningTask, currentPortfolioTask].find((task) => ["running", "pending"].includes(task?.status));
  const resultContext = selectedResultContext();
  renderSummaryGrid(target, [
    { label: "当前策略", value: strategyName },
    { label: "策略版本", value: strategyVersion },
    { label: "当前工作区", value: viewNames[currentBacktestView] || currentBacktestView },
    { label: "当前任务", value: runningTask ? taskDisplayTitle(runningTask) : (currentModeTask ? taskDisplayTitle(currentModeTask) : (singleRunState.symbol ? (singleRunState.strategyName || "单股策略") + " · " + singleRunState.symbol : "尚未选择")) },
    { label: "执行状态", value: runningTask ? backtestStatusInfo(runningTask.status).label : backtestStatusInfo(singleRunState.status).label },
    { label: "结果状态", value: resultContext ? "已有可查看结果" : "等待任务完成" },
  ]);
  const hasTask = singleRunState.status !== "idle" || Boolean(currentScreeningTaskId || currentPortfolioTaskId);
  const isRunning = ["running", "loading_result"].includes(singleRunState.status) || Boolean(runningTask);
  const hasResult = Boolean(resultContext);
  const completed = {
    strategy: Boolean(selectedStrategy),
    mode: hasTask,
    configure: hasTask,
    run: isRunning || hasResult,
    results: hasResult,
  };
  const currentStep = currentBacktestView === "strategy" ? "strategy"
    : currentBacktestView === "overview" ? "mode"
    : ["single", "independent", "portfolio"].includes(currentBacktestView) ? (isRunning ? "run" : "configure")
    : "results";
  document.querySelectorAll("[data-workflow-step]").forEach((step) => {
    step.classList.toggle("is-complete", Boolean(completed[step.dataset.workflowStep]));
    step.classList.toggle("is-current", step.dataset.workflowStep === currentStep);
  });
  $("#backtest-workspace-status").textContent = selectedStrategy ? strategyName + " / " + strategyVersion : "请先选择策略";
}
function renderBacktestConfigPreview(form, target, mode) {
  if (!form || !target) return;
  const values = Object.fromEntries(new FormData(form).entries());
  const explicitSymbols = String(values.symbols || "").split(/[,，\s]+/).filter(Boolean);
  const limit = Number(values.symbol_limit || 0);
  const scope = explicitSymbols.length ? `指定 ${explicitSymbols.length} 只股票` : (values.market ? values.market : (limit > 0 ? `前 ${limit} 只 A 股` : "全部当前 A 股"));
  const items = [
    { label: "回测模式", value: mode === "independent" ? "独立资金逐股回测" : "单一共享资金池" },
    { label: "策略", value: selectedStrategy?.name || selectedStrategy?.strategy_id || "请选择策略" },
    { label: "股票范围", value: scope },
    { label: "回测期间", value: `${values.start_date || "-"} 至 ${values.end_date || "-"}` },
    { label: "复权", value: values.adjustment || "raw" },
  ];
  if (mode === "independent") items.push({ label: "执行资源", value: Number(values.max_workers || 0) ? `${values.max_workers} 并发` : "自动并发" });
  else items.push({ label: "组合约束", value: `最多 ${values.max_positions || 10} 只 / 资金使用 ${Math.round(Number(values.portfolio_exposure || 0.95) * 100)}%` });
  renderSummaryGrid(target, items);
}

function toggleAdvancedFields(form, button) {
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  button.textContent = expanded ? "高级参数" : "收起高级参数";
  form.querySelectorAll(".advanced-field").forEach((field) => field.classList.toggle("is-hidden", expanded));
}

function setupAdvancedFields(form, names) {
  names.forEach((name) => form.elements[name]?.closest("label")?.classList.add("advanced-field", "is-hidden"));
}

function updateScreeningActions(task = {}) {
  const status = task.status || "not_found";
  $("#screening-task-run").disabled = !["ready", "paused", "interrupted", "failed", "partial_failed"].includes(status);
  $("#screening-task-pause").disabled = status !== "running";
  $("#screening-task-cancel").disabled = !["ready", "running", "pause_requested", "paused", "interrupted"].includes(status);
  renderBacktestWorkspace();
}

function updatePortfolioActions(task = {}) {
  const status = task.status || "not_found";
  $("#portfolio-task-run").disabled = !["ready", "interrupted", "failed"].includes(status);
  renderBacktestWorkspace();
}

async function openBacktestWorkspaceView(view) {
  activateBacktestView(view);
  if (view === "overview") await loadBacktestModeTasks();
  else if (view === "independent") await loadIndependentScreeningTasks();
  else if (view === "portfolio") await loadSharedPortfolioTasks();
  else if (view === "results") await refreshBacktestResults();
}

function bindBacktestWorkspace() {
  document.querySelectorAll("[data-backtest-view-target]").forEach((button) => button.addEventListener("click", () => {
    openBacktestWorkspaceView(button.dataset.backtestViewTarget).catch((error) => setFeedback(error.message, "error"));
  }));
  document.querySelectorAll("[data-backtest-view-jump]").forEach((button) => button.addEventListener("click", () => {
    openBacktestWorkspaceView(button.dataset.backtestViewJump).catch((error) => setFeedback(error.message, "error"));
  }));
  const screeningForm = $("#screening-task-form");
  const portfolioForm = $("#portfolio-task-form");
  setupAdvancedFields(screeningForm, ["scheduler_batch_size", "retry_count", "initial_cash"]);
  setupAdvancedFields(portfolioForm, ["max_workers", "initial_cash"]);
  screeningForm.addEventListener("input", () => renderBacktestConfigPreview(screeningForm, $("#screening-config-preview"), "independent"));
  portfolioForm.addEventListener("input", () => renderBacktestConfigPreview(portfolioForm, $("#portfolio-config-preview"), "portfolio"));
  $("#screening-advanced-toggle").addEventListener("click", (event) => toggleAdvancedFields(screeningForm, event.currentTarget));
  $("#portfolio-advanced-toggle").addEventListener("click", (event) => toggleAdvancedFields(portfolioForm, event.currentTarget));
  renderBacktestConfigPreview(screeningForm, $("#screening-config-preview"), "independent");
  renderBacktestConfigPreview(portfolioForm, $("#portfolio-config-preview"), "portfolio");
  renderTaskProgress("#screening-live-progress", taskProgressModel({}, "independent-screening"));
  renderTaskProgress("#portfolio-live-progress", taskProgressModel({}, "shared-portfolio"));
  renderSingleRunProgress();
  updateScreeningActions();
  updatePortfolioActions();
  activateBacktestView("overview");
}
function renderScreeningTask(task = {}) {
  currentScreeningTask = task.task_id ? task : currentScreeningTask;
  const progress = task.progress || {};
  const execution = task.execution || {};
  renderTaskProgress("#screening-live-progress", taskProgressModel(task, "independent-screening"));
  renderSummaryGrid($("#screening-progress"), [
    { label: "状态", value: backtestStatusInfo(task.status).label },
    { label: "股票总数", value: progress.total ?? 0 },
    { label: "已处理", value: progress.processed ?? 0 },
    { label: "已建仓", value: progress.entered ?? 0 },
    { label: "未建仓", value: progress.no_entry ?? 0 },
    { label: "失败", value: progress.failed ?? 0 },
    { label: "有效并发", value: execution.effective_workers ?? "-" },
    { label: "调度批次", value: execution.batch_size ?? "-" },
    { label: "执行耗时", value: taskElapsedSeconds(task) > 0 ? formatTaskSeconds(taskElapsedSeconds(task)) : "尚未执行" },
    { label: "创建时间", value: formatTaskTimestamp(task.created_at) },
  ]);
  $("#screening-summary").textContent = JSON.stringify({ config: task.config || {}, execution, summary: task.summary || {} }, null, 2);
  if (currentModeTask?.mode === "independent-screening" && currentModeTask.task_id === task.task_id) {
    currentModeTask = {
      ...currentModeTask,
      status: task.status,
      progress,
      execution,
      updated_at: task.updated_at,
      started_at: task.started_at,
      finished_at: task.finished_at,
    };
  }
  updateScreeningActions(task);
  renderActiveTaskOverview();
  renderBacktestResultsContext();
}
function renderScreeningEnteredResults(items = []) {
  const target = $("#screening-entered-results");
  if (!items.length) {
    target.innerHTML = '<div class="empty-cell">暂无建仓标的</div>';
    return;
  }
  target.innerHTML = '<table><thead><tr><th>代码</th><th>名称</th><th>状态</th><th>总收益</th><th>年化收益</th><th>回测编号</th></tr></thead><tbody>' + items.map((item) => '<tr><td>' + escapeHtml(item.symbol) + '</td><td>' + escapeHtml(item.name) + '</td><td>' + escapeHtml(item.status) + '</td><td class="' + financialToneClass(item.metrics?.total_returns) + '">' + (item.metrics?.total_returns ?? "-") + '</td><td class="' + financialToneClass(item.metrics?.annualized_returns) + '">' + (item.metrics?.annualized_returns ?? "-") + '</td><td title="' + escapeHtml(item.run_id || "") + '">' + escapeHtml(shortTechnicalId(item.run_id)) + '</td></tr>').join("") + '</tbody></table>';
}
async function loadIndependentScreeningTask(taskId, { schedule = true } = {}) {
  if (!taskId) return null;
  currentScreeningTaskId = taskId;
  const [detail, entered] = await Promise.all([
    requestJson(`/api/backtest/independent-screening-tasks/${encodeURIComponent(taskId)}`),
    requestJson(`/api/backtest/independent-screening-tasks/${encodeURIComponent(taskId)}/items?entered_only=true&limit=100`),
  ]);
  const task = detail.task || {};
  renderScreeningTask(task);
  renderScreeningEnteredResults(entered.result?.items || []);
  if (screeningPollTimer) clearTimeout(screeningPollTimer);
  if (schedule && ["running", "ready", "interrupted", "pause_requested", "cancel_requested"].includes(task.status)) {
    screeningPollTimer = setTimeout(() => loadIndependentScreeningTask(taskId).catch((error) => setFeedback(error.message, "error")), 2000);
  }
  return task;
}
async function loadIndependentScreeningTasks() {
  const payload = await requestJson("/api/backtest/independent-screening-tasks?limit=20");
  const tasks = payload.tasks || [];
  $("#screening-task-list").innerHTML = tasks.map((task) => {
    const progress = taskProgressModel(task, "independent-screening");
    const info = backtestStatusInfo(task.status);
    return '<article class="compact-task-row is-' + info.tone + '" data-screening-task="' + escapeHtml(task.task_id) + '">' +
      '<div><span class="task-status-badge is-' + info.tone + '">' + escapeHtml(info.label) + '</span><h4>' + escapeHtml(strategyDisplayName(task.config?.strategy_id) + " · 独立选股") + '</h4><p>' + escapeHtml(taskExecutionLabel(task)) + ' · ' + progress.total + ' 只' + (taskElapsedSeconds(task) > 0 ? ' · 耗时 ' + escapeHtml(formatTaskSeconds(taskElapsedSeconds(task))) : '') + '</p></div>' +
      '<div class="task-card-progress"><div><i style="width:' + progress.percent + '%"></i></div><span>' + Math.round(progress.percent) + '% · ' + progress.processed + '/' + progress.total + '</span></div></article>';
  }).join("") || '<div class="empty-cell">暂无独立选股任务</div>';
  document.querySelectorAll("[data-screening-task]").forEach((card) => card.addEventListener("click", async () => {
    const task = tasks.find((item) => item.task_id === card.dataset.screeningTask);
    currentModeTask = task ? {
      task_id: task.task_id,
      mode: "independent-screening",
      mode_label: "独立选股",
      name: task.config?.name || task.task_id,
      status: task.status,
      strategy_binding: { strategy_id: task.config?.strategy_id, strategy_version: task.config?.strategy_version },
      date_window: task.config?.date_window || {},
      universe_count: task.progress?.total || 0,
      progress: task.progress || {},
      execution: task.execution || {},
      created_at: task.created_at,
      updated_at: task.updated_at,
      started_at: task.started_at,
      finished_at: task.finished_at,
      links: {
        report: "/api/reporting/backtest-modes/independent-screening/" + encodeURIComponent(task.task_id),
      },
    } : null;
    await loadIndependentScreeningTask(card.dataset.screeningTask);
    renderModeTaskSelection(currentModeTask);
  }));
  if (!currentScreeningTaskId && tasks.length) await loadIndependentScreeningTask(tasks[0].task_id, { schedule: false });
  return tasks;
}
async function createIndependentScreeningTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = event.submitter || form.querySelector('button[type="submit"]');
  const originalLabel = submit?.textContent || "创建任务";
  if (submit) { submit.disabled = true; submit.textContent = "正在创建..."; }
  setFeedback("正在创建独立选股任务，请稍候");
  try {
    const values = Object.fromEntries(new FormData(form).entries());
    const backtestForm = Object.fromEntries(new FormData($("#backtest-run-form")).entries());
    const body = {
      task_id: values.task_id || newTaskId("screening"),
      name: (selectedStrategy?.name || "策略") + " 独立选股",
      strategy_id: selectedStrategy?.strategy_id || backtestForm.strategy_id || "moving_average_strategy",
      strategy_version: selectedStrategy?.latest_version || backtestForm.strategy_version || "v1",
      symbols: String(values.symbols || "").split(/[,，\s]+/).filter(Boolean),
      market: values.market || "",
      start_date: values.start_date,
      end_date: values.end_date,
      adjustment: values.adjustment || "raw",
      benchmark: backtestForm.benchmark || "000300.XSHG",
      initial_cash: Number(values.initial_cash || 1000000),
      parameters: collectStrategyParameters(),
      max_workers: Number(values.max_workers || 4),
      retry_count: Number(values.retry_count || 1),
      symbol_limit: Number(values.symbol_limit || 0),
      scheduler_batch_size: Number(values.scheduler_batch_size || 0),
    };
    const payload = await requestJson("/api/backtest/independent-screening-tasks", { method: "POST", body: JSON.stringify(body) });
    currentScreeningTaskId = payload.task?.task_id;
    renderScreeningTask(payload.task || {});
    await loadIndependentScreeningTasks();
    await loadBacktestModeTasks();
    currentModeTask = modeTaskCatalog.find((task) => task.mode === "independent-screening" && task.task_id === currentScreeningTaskId) || currentModeTask;
    renderModeTaskSelection(currentModeTask);
    form.elements.task_id.value = "";
    setFeedback("独立选股任务已创建：" + taskDisplayTitle(currentModeTask || {}), "success");
  } catch (error) {
    setFeedback("独立选股创建失败：" + error.message, "error");
    throw error;
  } finally {
    if (submit) { submit.disabled = false; submit.textContent = originalLabel; }
  }
}
async function runIndependentScreeningTask() {
  if (!currentScreeningTaskId) throw new Error("请先创建或选择独立选股任务");
  await requestJson(`/api/backtest/independent-screening-tasks/${encodeURIComponent(currentScreeningTaskId)}/run`, { method: "POST", body: JSON.stringify({ wait: false }) });
  await loadIndependentScreeningTask(currentScreeningTaskId);
  await loadBacktestModeTasks();
  setFeedback(`独立选股任务已启动：${currentScreeningTaskId}`, "success");
}
async function controlIndependentScreeningTask(action) {
  if (!currentScreeningTaskId) throw new Error("请先创建或选择独立选股任务");
  const payload = await requestJson(
    `/api/backtest/independent-screening-tasks/${encodeURIComponent(currentScreeningTaskId)}/control`,
    { method: "POST", body: JSON.stringify({ action }) },
  );
  renderScreeningTask(payload.task || {});
  await loadBacktestModeTasks();
  setFeedback(`独立选股任务控制已提交：${action}`, "success");
}
function renderPortfolioTask(task = {}) {
  currentPortfolioTask = task.task_id ? task : currentPortfolioTask;
  const summary = task.summary || {};
  const metrics = summary.metrics || {};
  const progressTask = task;
  renderTaskProgress("#portfolio-live-progress", taskProgressModel(progressTask, "shared-portfolio"));
  renderSummaryGrid($("#portfolio-task-progress"), [
    { label: "状态", value: backtestStatusInfo(task.status).label },
    { label: "冻结股票", value: task.universe_count ?? 0 },
    { label: "已处理股票", value: (task.progress || {}).processed ?? 0 },
    { label: "可执行股票", value: (task.progress || {}).prepared ?? summary.executed_symbol_count ?? 0 },
    { label: "排除股票", value: (task.progress || {}).excluded ?? summary.excluded_symbol_count ?? 0 },
    { label: "执行耗时", value: taskElapsedSeconds(task) > 0 ? formatTaskSeconds(taskElapsedSeconds(task)) : "尚未执行" },
    { label: "组合收益", value: metrics.total_returns ?? "-", tone: financialToneClass(metrics.total_returns) },
    { label: "最大回撤", value: metrics.max_drawdown ?? "-", tone: financialToneClass(metrics.max_drawdown) },
    { label: "成交数", value: summary.trade_count ?? 0 },
  ]);
  $("#portfolio-task-summary").textContent = JSON.stringify({ config: task.config || {}, summary, run_id: task.run_id, error_message: task.error_message }, null, 2);
  if (currentModeTask?.mode === "shared-portfolio" && currentModeTask.task_id === task.task_id) {
    currentModeTask = {
      ...currentModeTask,
      status: task.status,
      run_id: task.run_id,
      progress: progressTask.progress,
      updated_at: task.updated_at,
      started_at: task.started_at,
      finished_at: task.finished_at,
    };
  }
  updatePortfolioActions(task);
  renderActiveTaskOverview();
  renderBacktestResultsContext();
}
async function loadSharedPortfolioTask(taskId, { schedule = true } = {}) {
  if (!taskId) return null;
  currentPortfolioTaskId = taskId;
  const payload = await requestJson(`/api/backtest/shared-portfolio-tasks/${encodeURIComponent(taskId)}`);
  const task = payload.task || {};
  renderPortfolioTask(task);
  if (portfolioPollTimer) clearTimeout(portfolioPollTimer);
  if (schedule && ["running", "ready", "interrupted"].includes(task.status)) {
    portfolioPollTimer = setTimeout(() => loadSharedPortfolioTask(taskId).catch((error) => setFeedback(error.message, "error")), 2000);
  }
  return task;
}
async function loadSharedPortfolioTasks() {
  const payload = await requestJson("/api/backtest/shared-portfolio-tasks?limit=20");
  const tasks = payload.tasks || [];
  $("#portfolio-task-list").innerHTML = tasks.map((task) => {
    const progress = taskProgressModel(task, "shared-portfolio");
    const info = backtestStatusInfo(task.status);
    return '<article class="compact-task-row is-' + info.tone + '" data-portfolio-task="' + escapeHtml(task.task_id) + '">' +
      '<div><span class="task-status-badge is-' + info.tone + '">' + escapeHtml(info.label) + '</span><h4>' + escapeHtml(strategyDisplayName(task.config?.strategy_id) + " · 共享资金池") + '</h4><p>' + escapeHtml(taskExecutionLabel(task)) + ' · ' + (task.universe_count || 0) + ' 只 · 最多持仓 ' + (task.config?.max_positions || "-") + (taskElapsedSeconds(task) > 0 ? ' · 耗时 ' + escapeHtml(formatTaskSeconds(taskElapsedSeconds(task))) : '') + '</p></div>' +
      '<div class="task-card-progress"><div><i style="width:' + progress.percent + '%"></i></div><span>' + Math.round(progress.percent) + '% · ' + progress.processed + '/' + progress.total + '</span></div></article>';
  }).join("") || '<div class="empty-cell">暂无共享资金池任务</div>';
  document.querySelectorAll("[data-portfolio-task]").forEach((card) => card.addEventListener("click", async () => {
    const task = tasks.find((item) => item.task_id === card.dataset.portfolioTask);
    currentModeTask = task ? {
      task_id: task.task_id,
      mode: "shared-portfolio",
      mode_label: "共享资金池",
      name: task.config?.name || task.task_id,
      status: task.status,
      strategy_binding: { strategy_id: task.config?.strategy_id, strategy_version: task.config?.strategy_version },
      date_window: task.config?.date_window || {},
      universe_count: task.universe_count || 0,
      run_id: task.run_id,
      progress: task.progress || {},
      created_at: task.created_at,
      updated_at: task.updated_at,
      started_at: task.started_at,
      finished_at: task.finished_at,
      links: {
        report: "/api/reporting/backtest-modes/shared-portfolio/" + encodeURIComponent(task.task_id),
      },
    } : null;
    await loadSharedPortfolioTask(card.dataset.portfolioTask);
    renderModeTaskSelection(currentModeTask);
  }));
  if (!currentPortfolioTaskId && tasks.length) await loadSharedPortfolioTask(tasks[0].task_id, { schedule: false });
  return tasks;
}
async function createSharedPortfolioTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = event.submitter || form.querySelector('button[type="submit"]');
  const originalLabel = submit?.textContent || "创建组合任务";
  if (submit) { submit.disabled = true; submit.textContent = "正在创建..."; }
  setFeedback("正在创建共享资金池任务，请稍候");
  try {
    const values = Object.fromEntries(new FormData(form).entries());
    const backtestForm = Object.fromEntries(new FormData($("#backtest-run-form")).entries());
    const body = {
      task_id: values.task_id || newTaskId("portfolio"),
      name: (selectedStrategy?.name || "策略") + " 共享资金池组合",
      strategy_id: selectedStrategy?.strategy_id || backtestForm.strategy_id || "moving_average_strategy",
      strategy_version: selectedStrategy?.latest_version || backtestForm.strategy_version || "v1",
      symbols: String(values.symbols || "").split(/[,，\s]+/).filter(Boolean),
      market: values.market || "",
      start_date: values.start_date,
      end_date: values.end_date,
      adjustment: values.adjustment || "raw",
      benchmark: backtestForm.benchmark || "000300.XSHG",
      initial_cash: Number(values.initial_cash || 1000000),
      parameters: collectStrategyParameters(),
      max_workers: Number(values.max_workers || 4),
      symbol_limit: Number(values.symbol_limit || 0),
      max_positions: Number(values.max_positions || 10),
      portfolio_exposure: Number(values.portfolio_exposure || 0.95),
      commission_rate: Number(backtestForm.commission_rate || 0.0003),
      min_commission: Number(backtestForm.min_commission || 5),
      tax_rate: Number(backtestForm.tax_rate || 0.001),
      slippage_rate: Number(backtestForm.slippage_rate || 0.0005),
    };
    const payload = await requestJson("/api/backtest/shared-portfolio-tasks", { method: "POST", body: JSON.stringify(body) });
    currentPortfolioTaskId = payload.task?.task_id;
    renderPortfolioTask(payload.task || {});
    await loadSharedPortfolioTasks();
    await loadBacktestModeTasks();
    currentModeTask = modeTaskCatalog.find((task) => task.mode === "shared-portfolio" && task.task_id === currentPortfolioTaskId) || currentModeTask;
    renderModeTaskSelection(currentModeTask);
    form.elements.task_id.value = "";
    setFeedback("共享资金池任务已创建：" + taskDisplayTitle(currentModeTask || {}), "success");
  } catch (error) {
    setFeedback("共享资金池创建失败：" + error.message, "error");
    throw error;
  } finally {
    if (submit) { submit.disabled = false; submit.textContent = originalLabel; }
  }
}
async function runSharedPortfolioTask() {
  if (!currentPortfolioTaskId) throw new Error("请先创建或选择共享资金池组合任务");
  await requestJson(`/api/backtest/shared-portfolio-tasks/${encodeURIComponent(currentPortfolioTaskId)}/run`, { method: "POST", body: JSON.stringify({ wait: false }) });
  await loadSharedPortfolioTask(currentPortfolioTaskId);
  await loadBacktestModeTasks();
  setFeedback(`共享资金池组合任务已启动：${currentPortfolioTaskId}`, "success");
}

function renderModeTaskSelection(task) {
  const target = $("#mode-task-directory-detail");
  if (!target) return;
  if (!task) {
    target.innerHTML = '<div class="empty-cell">选择任务查看执行详情</div>';
    return;
  }
  const progress = taskProgressModel(task, task.mode);
  const info = backtestStatusInfo(task.status);
  const binding = task.strategy_binding || {};
  const dates = task.date_window || {};
  const elapsed = taskElapsedSeconds(task);
  target.innerHTML =
    '<div class="task-selection-head"><div><span class="task-mode-label">' + escapeHtml(task.mode_label || task.mode) + '</span><h4>' + escapeHtml(taskDisplayTitle(task)) + '</h4><small>' + escapeHtml(taskExecutionLabel(task)) + '</small></div><span class="task-status-badge is-' + info.tone + '">' + escapeHtml(info.label) + '</span></div>' +
    '<div class="task-selection-grid"><div><span>策略版本</span><strong>' + escapeHtml(binding.strategy_version || "-") + '</strong></div><div><span>回测期间</span><strong>' + escapeHtml(dates.start_date || "-") + ' 至 ' + escapeHtml(dates.end_date || "-") + '</strong></div><div><span>股票范围</span><strong>' + (task.universe_count || progress.total || 0) + ' 只</strong></div><div><span>执行进度</span><strong>' + Math.round(progress.percent) + '% · ' + progress.processed + '/' + progress.total + '</strong></div><div><span>执行耗时</span><strong>' + (elapsed > 0 ? escapeHtml(formatTaskSeconds(elapsed)) : "尚未执行") + '</strong></div><div><span>创建时间</span><strong>' + escapeHtml(formatTaskTimestamp(task.created_at)) + '</strong></div><div><span>任务编号</span><strong title="' + escapeHtml(task.task_id) + '">' + escapeHtml(shortTechnicalId(task.task_id)) + '</strong></div><div><span>回测编号</span><strong title="' + escapeHtml(task.run_id || "") + '">' + escapeHtml(shortTechnicalId(task.run_id)) + '</strong></div></div>' +
    '<div class="task-card-progress is-large"><div><i style="width:' + progress.percent + '%"></i></div><span>' + escapeHtml(progress.phase) + '</span></div>';
}

async function selectBacktestModeTask(task, options = {}) {
  currentModeTask = task;
  renderModeTaskSelection(task);
  if (task.mode === "independent-screening") {
    currentScreeningTaskId = task.task_id;
    await loadIndependentScreeningTask(task.task_id, { schedule: options.schedule !== false });
  } else {
    currentPortfolioTaskId = task.task_id;
    await loadSharedPortfolioTask(task.task_id, { schedule: options.schedule !== false });
  }
  if (options.openWorkspace) activateBacktestView(task.mode === "independent-screening" ? "independent" : "portfolio");
  renderActiveTaskOverview();
  renderBacktestResultsContext();
}

async function runBacktestModeTask(task) {
  currentModeTask = task;
  await requestJson(task.links.run, { method: "POST", body: JSON.stringify({ wait: false }) });
  await selectBacktestModeTask({ ...task, status: "running" });
  await loadBacktestModeTasks();
  setFeedback("回测任务已启动 / 恢复：" + task.task_id, "success");
}

async function openBacktestModeReport(task) {
  const form = $("#mode-report-form");
  form.elements.mode.value = task.mode;
  form.elements.task_id.value = task.task_id;
  activatePage("reporting");
  await loadBacktestModeReport();
}

async function showBacktestTaskResults(task) {
  currentModeTask = task;
  renderModeTaskSelection(task);
  activateBacktestView("results");
  renderBacktestResultsContext();
  if (task.mode === "shared-portfolio" && task.run_id) {
    await loadBacktestResultPanel(task.run_id);
  }
}

async function refreshBacktestResults() {
  const context = selectedResultContext();
  renderBacktestResultsContext();
  if (!context) return;
  if (context.kind === "single" && context.task.runId) {
    await loadBacktestResultPanel(context.task.runId);
  } else if (context.kind === "mode") {
    await selectBacktestModeTask(context.task, { schedule: false });
    if (context.task.mode === "shared-portfolio" && context.task.run_id) {
      await loadBacktestResultPanel(context.task.run_id);
    }
  }
}

async function openSelectedBacktestReport() {
  const context = selectedResultContext();
  if (!context) return;
  if (context.kind === "mode") {
    await openBacktestModeReport(context.task);
    return;
  }
  activatePage("reporting");
  $('#reporting-query-form input[name="run_id"]').value = context.task.runId;
  await loadReports(context.task.runId, "phase1-batch-001");
}

async function loadBacktestModeTasks(values = null) {
  const form = $("#mode-task-directory-form");
  const query = values || Object.fromEntries(new FormData(form).entries());
  const payload = await requestJson("/api/backtest/mode-tasks?" + buildQuery(query));
  const tasks = payload.tasks || [];
  modeTaskCatalog = tasks;
  const summary = payload.summary || {};
  renderSummaryGrid($("#mode-task-directory-summary"), [
    { label: "任务总数", value: summary.task_count || 0 },
    { label: "独立选股", value: summary.mode_counts?.["independent-screening"] || 0 },
    { label: "共享资金池", value: summary.mode_counts?.["shared-portfolio"] || 0 },
    { label: "运行中", value: summary.status_counts?.running || 0 },
    { label: "已完成", value: (summary.status_counts?.completed || 0) + (summary.status_counts?.partial_completed || 0) },
    { label: "异常", value: (summary.status_counts?.failed || 0) + (summary.status_counts?.partial_failed || 0) },
  ]);
  $("#mode-task-directory-list").innerHTML = tasks.map(taskCardHtml).join("") || '<div class="empty-cell">暂无符合条件的回测任务</div>';
  document.querySelectorAll("[data-mode-task-select]").forEach((card) => card.addEventListener("click", () => {
    selectBacktestModeTask(tasks[Number(card.dataset.modeTaskSelect)], { schedule: false }).catch((error) => setFeedback(error.message, "error"));
  }));
  document.querySelectorAll("[data-mode-task-open]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    selectBacktestModeTask(tasks[Number(button.dataset.modeTaskOpen)], { openWorkspace: true }).catch((error) => setFeedback(error.message, "error"));
  }));
  document.querySelectorAll("[data-mode-task-run]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    runBacktestModeTask(tasks[Number(button.dataset.modeTaskRun)]).catch((error) => setFeedback(error.message, "error"));
  }));
  document.querySelectorAll("[data-mode-task-result]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    showBacktestTaskResults(tasks[Number(button.dataset.modeTaskResult)]).catch((error) => setFeedback(error.message, "error"));
  }));
  if (currentModeTask) {
    const refreshed = tasks.find((task) => task.task_id === currentModeTask.task_id && task.mode === currentModeTask.mode);
    if (refreshed) {
      currentModeTask = refreshed;
      renderModeTaskSelection(refreshed);
    }
  }
  renderActiveTaskOverview();
  renderBacktestResultsContext();
  return tasks;
}
function renderStrategyResearchTasks(tasks = []) {
  const target = $("#strategy-research-list");
  if (!target) return;
  target.innerHTML = tasks.map((task) => `<article class="definition-item"><h4>${task.task_id} / ${task.strategy_id}</h4><p>${(task.symbols || []).join(", ")}；${task.date_window?.start_date || "-"} 至 ${task.date_window?.end_date || "-"}</p><span>${task.status || "unknown"} / ${task.strategy_version || "v1"}</span><div class="button-row"><button type="button" data-research-run="${task.task_id}">执行回测</button></div></article>`).join("") || '<div class="empty-cell">暂无研究任务</div>';
}
async function loadStrategyResearchTasks() {
  const payload = await requestJson("/api/backtest/research-tasks");
  renderStrategyResearchTasks(payload.tasks || []);
  document.querySelectorAll("[data-research-run]").forEach((button) => button.addEventListener("click", () => runStrategyResearchTask(button.dataset.researchRun)));
  return payload.tasks || [];
}
async function runStrategyResearchTask(taskId) {
  const payload = await requestJson(`/api/backtest/research-tasks/${encodeURIComponent(taskId)}/run`, { method: "POST", body: JSON.stringify({ run_id_prefix: `${taskId}-web` }) });
  $("#strategy-research-output").textContent = JSON.stringify(payload.result || {}, null, 2);
  await loadStrategyResearchTasks();
  await loadExperimentIndex();
  const firstRunId = (payload.result?.run_ids || [])[0];
  if (firstRunId) await loadBacktestResultPanel(firstRunId);
  if ((payload.result?.run_ids || []).length > 1) {
    const prefix = payload.result?.run_id_prefix || firstRunId.replace(/-\d+$/, "");
    currentBacktestRunIdPrefix = prefix;
    await loadBacktestPortfolioPanel(prefix);
    await loadBacktestExperimentPanel(prefix);
    await loadExperimentIndex();
  }
  setFeedback(`研究任务回测完成：${payload.result?.status || "unknown"}`, payload.result?.status === "completed" ? "success" : "error");
}
async function createStrategyResearchTask() {
  const form = Object.fromEntries(new FormData($("#backtest-run-form")).entries());
  const body = {
    strategy_id: form.strategy_id || selectedStrategy?.strategy_id || "moving_average_strategy",
    strategy_version: form.strategy_version || selectedStrategy?.latest_version || "v1",
    name: `${selectedStrategy?.name || form.strategy_name || "策略"} 研究任务`,
    symbols: [form.symbol || "000001.XSHE"],
    start_date: form.start_date || "2020-01-01",
    end_date: form.end_date || "2020-12-31",
    benchmark: form.benchmark || "000300.XSHG",
    frequency: "1d",
    parameters: collectStrategyParameters(),
    notes: "Web MVP 阶段 34 创建的本地策略研究任务",
  };
  const payload = await requestJson("/api/backtest/research-tasks", { method: "POST", body: JSON.stringify(body) });
  $("#strategy-research-output").textContent = JSON.stringify(payload.task || {}, null, 2);
  await loadStrategyResearchTasks();
  await loadExperimentIndex();
  setFeedback(`研究任务已创建：${payload.task?.task_id || "unknown"}`, "success");
}
async function loadStrategies({ selectId = null } = {}) {
  const feedback = $("#strategy-library-feedback");
  feedback.textContent = "正在加载策略库...";
  feedback.className = "inline-status";
  try {
    const payload = await requestJson("/api/backtest/strategies");
    strategyCatalog = payload.strategies || [];
    const categories = [...new Set(strategyCatalog.map((item) => item.category).filter(Boolean))].sort();
    const categorySelect = $("#strategy-library-category");
    const currentCategory = categorySelect.value;
    categorySelect.innerHTML = '<option value="">全部分类</option>' + categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join("");
    categorySelect.value = categories.includes(currentCategory) ? currentCategory : "";
    renderStrategyLibrary();
    const targetId = selectId || selectedStrategy?.strategy_id || strategyCatalog[0]?.strategy_id;
    const target = strategyCatalog.find((item) => item.strategy_id === targetId);
    if (target) await selectStrategy(target);
    else if (!strategyCatalog.length) startNewStrategy();
    feedback.textContent = strategyCatalog.length ? "策略库已加载" : "策略库为空，请新建策略。";
    feedback.className = `inline-status ${strategyCatalog.length ? "is-success" : "is-warning"}`;
    Promise.allSettled([loadStrategyResearchTasks(), loadExperimentIndex()]);
    return strategyCatalog;
  } catch (error) {
    strategyCatalog = [];
    $("#strategy-library").innerHTML = `<div class="empty-cell">策略库加载失败：${escapeHtml(error.message)}</div>`;
    $("#strategy-library-count").textContent = "加载失败";
    feedback.textContent = `${error.message}，请点击刷新重试。`;
    feedback.className = "inline-status is-error";
    return [];
  }
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}
function renderStrategyLibrary() {
  const search = $("#strategy-library-search").value.trim().toLowerCase();
  const category = $("#strategy-library-category").value;
  const filtered = strategyCatalog.filter((strategy) => {
    const matchesSearch = !search || `${strategy.name} ${strategy.strategy_id} ${strategy.description}`.toLowerCase().includes(search);
    return matchesSearch && (!category || strategy.category === category);
  });
  $("#strategy-library-count").textContent = `${filtered.length} / ${strategyCatalog.length} 个策略`;
  $("#strategy-library").innerHTML = filtered.length ? filtered.map((strategy) => {
    const active = selectedStrategy?.strategy_id === strategy.strategy_id;
    return `<button type="button" class="strategy-library-item${active ? " is-selected" : ""}" data-strategy-id="${escapeHtml(strategy.strategy_id)}"><span class="strategy-library-item-main"><strong>${escapeHtml(strategy.name)}</strong><small>${escapeHtml(strategy.strategy_id)}</small></span><span class="strategy-library-item-meta"><em>${escapeHtml(strategy.category)}</em><span>${escapeHtml(strategy.latest_version || "v1")} · ${strategy.version_count || 1} 个版本</span></span><span class="strategy-library-item-description">${escapeHtml(strategy.description || "暂无说明")}</span></button>`;
  }).join("") : '<div class="empty-cell">没有符合条件的策略</div>';
}
function strategyParameterLabel(key) {
  const labels = { short_window: "短均线周期", long_window: "长均线周期", atr_window: "ATR 周期", atr_multiplier: "ATR 止损倍数", position_size: "目标仓位", commission: "手续费率", breakout_window: "突破周期", max_position: "最大仓位" };
  return labels[key] || key;
}
function coerceParameterValue(value, spec = {}) {
  if (spec.type === "integer") return Number.parseInt(value, 10);
  if (spec.type === "number") return Number.parseFloat(value);
  if (spec.type === "boolean") return value === true || value === "true" || value === "on";
  return value;
}
function collectStrategyParameters() {
  const parameters = {};
  document.querySelectorAll("[data-param-key]").forEach((input) => {
    const key = input.dataset.paramKey;
    const spec = selectedStrategy?.parameter_schema?.[key] || {};
    parameters[key] = coerceParameterValue(input.type === "checkbox" ? input.checked : input.value, spec);
  });
  return parameters;
}
function renderParameterForm(strategy) {
  const schema = strategy.parameter_schema || {};
  const parameters = strategy.parameters || {};
  const entries = Object.entries(schema);
  if (!entries.length) {
    $("#strategy-parameter-schema").innerHTML = '<div class="empty-cell">暂无可配置参数</div>';
    return;
  }
  $("#strategy-parameter-schema").innerHTML = entries.map(([key, spec]) => {
    const value = parameters[key] ?? "";
    const label = strategyParameterLabel(key);
    if (spec.type === "enum") {
      return `<label class="strategy-parameter-field"><span>${escapeHtml(label)}</span><select data-param-key="${escapeHtml(key)}">${(spec.options || []).map((option) => `<option value="${escapeHtml(option)}" ${option === value ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select></label>`;
    }
    if (spec.type === "boolean") {
      return `<label class="strategy-parameter-field strategy-toggle-field"><span>${escapeHtml(label)}</span><input data-param-key="${escapeHtml(key)}" type="checkbox" ${value ? "checked" : ""}></label>`;
    }
    const numeric = spec.type === "integer" || spec.type === "number";
    const type = numeric ? "number" : "text";
    const step = spec.type === "integer" ? "1" : "any";
    const min = spec.min == null ? "" : ` min="${spec.min}"`;
    const max = spec.max == null ? "" : ` max="${spec.max}"`;
    return `<label class="strategy-parameter-field"><span>${escapeHtml(label)}</span><input data-param-key="${escapeHtml(key)}" type="${type}" step="${step}"${min}${max} value="${escapeHtml(value)}"><small>${escapeHtml(key)}</small></label>`;
  }).join("");
}
function setStrategyCategory(category) {
  const select = $("#strategy-draft-category");
  if (![...select.options].some((option) => option.value === category)) select.add(new Option(category, category));
  select.value = category || "自定义策略";
}
async function selectStrategy(strategy) {
  if (!strategy) return;
  selectedStrategy = strategy;
  renderBacktestWorkspace();
  renderBacktestConfigPreview($("#screening-task-form"), $("#screening-config-preview"), "independent");
  renderBacktestConfigPreview($("#portfolio-task-form"), $("#portfolio-config-preview"), "portfolio");
  renderStrategyLibrary();
  $("#strategy-name-input").value = strategy.strategy_id;
  $("#strategy-id-input").value = strategy.strategy_id;
  $("#strategy-version-input").value = strategy.latest_version || "v1";
  $("#strategy-draft-id").value = strategy.strategy_id;
  $("#strategy-draft-id").readOnly = true;
  $("#strategy-draft-name").value = strategy.name;
  setStrategyCategory(strategy.category);
  $("#strategy-draft-description").value = strategy.description || "";
  $("#strategy-editor-meta").textContent = `${strategy.name} / ${strategy.latest_version || "v1"} / ${strategy.validation_status || "unknown"}`;
  $("#strategy-editor-state").textContent = "已选择";
  $("#strategy-delete").disabled = false;
  $("#strategy-editor").value = strategy.source_code || "";
  renderParameterForm(strategy);
  try {
    const history = await requestJson(`/api/backtest/strategies/${encodeURIComponent(strategy.strategy_id)}/versions`);
    const versions = history.versions || [];
    $("#strategy-version-history").innerHTML = versions.slice().reverse().map((version, index) => `<button type="button" class="strategy-version-item${version.latest_version === strategy.latest_version ? " is-current" : ""}" data-strategy-version-index="${versions.length - index - 1}"><strong>${escapeHtml(version.latest_version)}</strong><span>${escapeHtml(version.saved_at || "")}</span><small>${escapeHtml((version.source_sha256 || "").slice(0, 12))}</small></button>`).join("") || '<div class="empty-cell">暂无版本历史</div>';
    $("#strategy-version-history").querySelectorAll("[data-strategy-version-index]").forEach((button) => button.addEventListener("click", () => selectStrategy(versions[Number(button.dataset.strategyVersionIndex)])));
  } catch (error) {
    $("#strategy-version-history").innerHTML = `<div class="empty-cell">版本历史加载失败：${escapeHtml(error.message)}</div>`;
  }
}
function startNewStrategy() {
  selectedStrategy = { strategy_id: "custom_strategy", name: "自定义策略", category: "自定义策略", description: "", parameters: { position_size: 1.0 }, parameter_schema: { position_size: { type: "number", min: 0, max: 1 } }, source_code: newStrategyTemplate, latest_version: "未保存", version_count: 0, validation_status: "pending" };
  renderStrategyLibrary();
  renderBacktestWorkspace();
  $("#strategy-draft-id").value = "custom_strategy";
  $("#strategy-draft-id").readOnly = false;
  $("#strategy-draft-name").value = "自定义策略";
  setStrategyCategory("自定义策略");
  $("#strategy-draft-description").value = "";
  $("#strategy-editor").value = newStrategyTemplate;
  $("#strategy-editor-meta").textContent = "新策略 / 尚未保存";
  $("#strategy-editor-state").textContent = "新建中";
  $("#strategy-delete").disabled = true;
  $("#strategy-version-history").innerHTML = '<div class="empty-cell">保存后生成 v1</div>';
  $("#strategy-validation-output").textContent = "等待策略校验";
  $("#strategy-validation-output").className = "inline-status";
  renderParameterForm(selectedStrategy);
  $("#strategy-draft-name").focus();
}
async function validateStrategySource() {
  const payload = await requestJson("/api/backtest/strategies/validate", { method: "POST", body: JSON.stringify({ source_code: $("#strategy-editor").value }) });
  const validation = payload.validation || {};
  const issues = (validation.issues || []).map((item) => `${item.line ? `第 ${item.line} 行：` : ""}${item.message}`).join("；");
  $("#strategy-validation-output").textContent = validation.ok ? `校验通过 · ${validation.contract || "target-weights-v1"}` : `校验失败 · ${issues || "请检查策略源码"}`;
  $("#strategy-validation-output").className = `inline-status ${validation.ok ? "is-success" : "is-error"}`;
  setFeedback(validation.ok ? "策略代码校验通过" : "策略代码校验未通过", validation.ok ? "success" : "error");
  return validation;
}
async function saveStrategyDraft() {
  const strategyId = $("#strategy-draft-id").value.trim();
  const name = $("#strategy-draft-name").value.trim();
  if (!strategyId || !name) {
    setFeedback("策略 ID 和策略名称不能为空", "error");
    return;
  }
  const validation = await validateStrategySource();
  if (!validation.ok) return;
  const body = { strategy_id: strategyId, name, category: $("#strategy-draft-category").value, description: $("#strategy-draft-description").value.trim(), source_code: $("#strategy-editor").value, parameters: collectStrategyParameters(), parameter_schema: selectedStrategy?.parameter_schema || {} };
  const payload = await requestJson("/api/backtest/strategies/save-draft", { method: "POST", body: JSON.stringify(body) });
  selectedStrategy = payload.strategy;
  await loadStrategies({ selectId: payload.strategy.strategy_id });
  setFeedback(`策略版本已保存：${payload.strategy.name} ${payload.strategy.latest_version}`, "success");
}
async function archiveSelectedStrategy() {
  const strategyId = selectedStrategy?.strategy_id;
  if (!strategyId || selectedStrategy?.latest_version === "未保存") return;
  if (!window.confirm(`确认删除策略“${selectedStrategy.name}”？历史版本和既有回测引用会保留。`)) return;
  await requestJson(`/api/backtest/strategies/${encodeURIComponent(strategyId)}`, { method: "DELETE" });
  selectedStrategy = null;
  await loadStrategies();
  setFeedback(`策略已从策略库删除：${strategyId}`, "success");
}
function bindStrategyManager() {
  $("#strategy-library").addEventListener("click", (event) => {
    const item = event.target.closest("[data-strategy-id]");
    if (item) selectStrategy(strategyCatalog.find((strategy) => strategy.strategy_id === item.dataset.strategyId));
  });
  $("#strategy-library-search").addEventListener("input", renderStrategyLibrary);
  $("#strategy-library-category").addEventListener("change", renderStrategyLibrary);
  $("#strategy-library-refresh").addEventListener("click", () => loadStrategies().then(() => setFeedback("策略库已刷新", "success")));
  $("#strategy-new").addEventListener("click", startNewStrategy);
  $("#strategy-validate").addEventListener("click", () => validateStrategySource().catch((error) => setFeedback(error.message, "error")));
  $("#strategy-save-draft").addEventListener("click", () => saveStrategyDraft().catch((error) => setFeedback(error.message, "error")));
  $("#strategy-delete").addEventListener("click", () => archiveSelectedStrategy().catch((error) => setFeedback(error.message, "error")));
}function buildRqalphaLocalConfig(formValues = {}) {
  return {
    strategy_template: formValues.rqalpha_strategy_template || "handle_bar_ma_cross",
    commission_rate: Number(formValues.commission_rate ?? 0.0003),
    tax_rate: Number(formValues.tax_rate ?? 0.001),
    min_commission: Number(formValues.min_commission ?? 5),
    slippage_rate: Number(formValues.slippage_rate ?? 0.0005),
    benchmark_alignment: formValues.benchmark_alignment || "same_symbol_buy_hold",
  };
}
async function loadBacktestResultPanel(runId) {
  if (!runId) return null;
  currentBacktestResultRunId = runId;
  currentBacktestRunIdPrefix = runId.replace(/-\d+$/, "");
  const payload = await requestJson(`/api/backtest/results/${encodeURIComponent(runId)}/panel`);
  const result = payload.result || {};
  const summary = result.summary || {};
  renderSummaryGrid($("#backtest-result-panel-summary"), [
    { label: "回测编号", value: shortTechnicalId(summary.run_id || result.run_id || runId) },
    { label: "状态", value: summary.status || result.status || "unknown" },
    { label: "策略", value: summary.strategy_name || "-" },
    { label: "标的", value: summary.universe || "-" },
    { label: "交易数", value: summary.trade_count ?? 0 },
    { label: "账户点", value: summary.account_points ?? 0 },
  ]);
  renderBacktestDataVersion(result);
  renderSummaryGrid($("#backtest-result-panel-metrics"), Object.entries(result.metrics || {}).map(([label, value]) => ({ label, value })));
  renderSeriesChart($("#backtest-result-equity-chart"), result.equity_curve || []);
  renderSeriesChart($("#backtest-result-drawdown-chart"), result.drawdown_curve || []);
  const tradeAttr = result.trade_attribution || {};
  const risk = result.risk_metrics || {};
  const exposure = result.exposure_summary || {};
  renderSummaryGrid($("#backtest-trade-attribution"), [
    { label: "交易数", value: tradeAttr.trade_count ?? 0 },
    { label: "买/卖", value: `${tradeAttr.buy_count ?? 0} / ${tradeAttr.sell_count ?? 0}` },
    { label: "成交额", value: tradeAttr.traded_amount ?? 0 },
    { label: "估算胜率", value: tradeAttr.estimated_win_rate ?? "-" },
    { label: "估算成本", value: tradeAttr.estimated_cost ?? 0 },
  ]);
  renderSummaryGrid($("#backtest-risk-metrics"), [
    { label: "最大回撤", value: risk.max_drawdown ?? "-" },
    { label: "当前回撤", value: risk.current_drawdown ?? "-" },
    { label: "波动", value: risk.period_volatility ?? "-" },
    { label: "最好/最差", value: `${risk.best_period_return ?? "-"} / ${risk.worst_period_return ?? "-"}` },
    { label: "已修复", value: risk.recovered === true ? "是" : (risk.recovered === false ? "否" : "-") },
  ]);
  renderSummaryGrid($("#backtest-exposure-summary"), [
    { label: "持仓数", value: exposure.holding_count ?? 0 },
    { label: "总市值", value: exposure.gross_market_value ?? 0 },
    { label: "单票最大权重", value: exposure.max_single_weight ?? "-" },
    { label: "快照", value: exposure.latest_snapshot_time || "-" },
  ]);
  $("#backtest-result-panel-tables").innerHTML = `<h4>交易明细</h4>${renderTable(result.trades || [], [{key:"trade_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"side",label:"方向"},{key:"price",label:"价格"},{key:"quantity",label:"数量"},{key:"amount",label:"成交额"}])}<h4>持仓快照</h4>${renderTable(result.positions || [], [{key:"snapshot_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"quantity",label:"数量"},{key:"market_value",label:"市值"}])}<h4>账户快照</h4>${renderTable(result.accounts || [], [{key:"snapshot_time",label:"时间"},{key:"total_value",label:"总资产"},{key:"cash",label:"现金"},{key:"unit_net_value",label:"单位净值"}])}<h4>年度收益</h4>${renderTable(result.yearly_returns || [], [{key:"year",label:"年度"},{key:"portfolio_return",label:"组合收益"},{key:"benchmark_return",label:"基准收益"},{key:"excess_return",label:"超额收益"}])}`;
  $("#backtest-result-panel-output").textContent = JSON.stringify({ summary, metrics: result.metrics || {}, trade_attribution: result.trade_attribution || {}, risk_metrics: result.risk_metrics || {}, exposure_summary: result.exposure_summary || {}, parameter_snapshot: result.parameter_snapshot || {}, input_snapshot: result.input_snapshot || {}, data_asset_trace: result.data_asset_trace || {}, logs: result.logs || [] }, null, 2);
  await loadBacktestResultTable(0);
  return result;
}
async function loadBacktestResultTable(offset = 0, exportFormat = "json") {
  if (!currentBacktestResultRunId) return null;
  currentBacktestTableOffset = Math.max(0, offset);
  const query = buildQuery({ table: "trades", offset: currentBacktestTableOffset, limit: currentBacktestTableLimit, export_format: exportFormat });
  const payload = await requestJson(`/api/backtest/results/${encodeURIComponent(currentBacktestResultRunId)}/table?${query}`);
  const result = payload.result || {};
  $("#backtest-result-page-table").innerHTML = `<h4>分页交易明细 ${result.offset || 0} / ${result.total || 0}</h4>${renderTable(result.rows || [], [{key:"trade_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"side",label:"方向"},{key:"price",label:"价格"},{key:"quantity",label:"数量"},{key:"amount",label:"成交额"}])}`;
  if (exportFormat !== "json") $("#backtest-result-export-output").textContent = result.content || "";
  return result;
}
async function exportBacktestResultTable(format) {
  const result = await loadBacktestResultTable(currentBacktestTableOffset, format);
  $("#backtest-result-export-output").textContent = format === "csv" ? (result?.content || "") : JSON.stringify(result?.content || result?.rows || [], null, 2);
}
async function loadBacktestExperimentPanel(runIdPrefix) {
  if (!runIdPrefix) return null;
  const payload = await requestJson(`/api/backtest/experiments/${encodeURIComponent(runIdPrefix)}/panel`);
  const result = payload.result || {};
  renderAssetConsistency(result.asset_consistency || {});
  $("#backtest-experiment-panel-output").textContent = JSON.stringify(result, null, 2);
  return payload.result;
}
async function loadBacktestPortfolioPanel(runIdPrefix) {
  if (!runIdPrefix) return null;
  const payload = await requestJson(`/api/backtest/results/${encodeURIComponent(runIdPrefix)}/portfolio-panel`);
  const result = payload.result || {};
  const summary = result.summary || {};
  renderSummaryGrid($("#backtest-portfolio-panel-summary"), [
    { label: "组合前缀", value: result.run_id_prefix || runIdPrefix },
    { label: "状态", value: result.status || "unknown" },
    { label: "Run 数", value: summary.run_count ?? 0 },
    { label: "标的数", value: (summary.symbols || []).length },
    { label: "交易数", value: summary.trade_count ?? 0 },
    { label: "平均收益", value: result.metrics?.avg_total_returns ?? "-" },
  ]);
  renderAssetConsistency(result.asset_consistency || {});
  renderSeriesChart($("#backtest-portfolio-equity-chart"), result.equity_curve || []);
  $("#backtest-portfolio-panel-output").textContent = JSON.stringify({ summary, metrics: result.metrics || {}, asset_consistency: result.asset_consistency || {}, trade_attribution: result.trade_attribution || {}, risk_metrics: result.risk_metrics || {}, rows: result.rows || [], drawdown_curve: result.drawdown_curve || [] }, null, 2);
  return result;
}
async function runBacktest(payload) {
  payload.strategy_id = payload.strategy_id || selectedStrategy?.strategy_id || payload.strategy_name;
  payload.strategy_version = payload.strategy_version || selectedStrategy?.latest_version || "v1";
  payload.parameters = collectStrategyParameters();
  payload.extra_config = { ...(payload.extra_config || {}), rqalpha_local: buildRqalphaLocalConfig(payload) };
  delete payload.rqalpha_strategy_template;
  delete payload.commission_rate;
  delete payload.tax_rate;
  delete payload.min_commission;
  delete payload.slippage_rate;
  delete payload.benchmark_alignment;
  currentModeTask = null;
  setSingleRunState({
    status: "running",
    phase: "正在读取行情并执行策略",
    runId: payload.run_id,
    strategyName: selectedStrategy?.name || payload.strategy_name || payload.strategy_id,
    symbol: payload.symbol,
    startedAt: Date.now(),
    elapsedSeconds: 0,
    result: null,
    error: "",
  });
  try {
    const resultPayload = await requestJson("/api/backtest/run-once", { method: "POST", body: JSON.stringify(payload) });
    const result = resultPayload.result || {};
    setSingleRunState({
      status: "loading_result",
      phase: "回测计算完成，正在载入指标和交易明细",
      runId: result.run_id || payload.run_id,
      result,
    });
    renderSummaryGrid($("#backtest-run-summary"), [
      { label: "回测编号", value: shortTechnicalId(result.run_id || payload.run_id) },
      { label: "策略", value: result.strategy_name || payload.strategy_name },
      { label: "策略版本", value: payload.strategy_id + " / " + payload.strategy_version },
      { label: "状态", value: backtestStatusInfo(result.status || "completed").label },
      { label: "基准", value: result.benchmark || payload.benchmark },
    ]);
    $("#backtest-run-output").textContent = JSON.stringify({
      result,
      strategy_binding: { strategy_id: payload.strategy_id, strategy_version: payload.strategy_version },
      parameters: payload.parameters,
      rqalpha_local: payload.extra_config?.rqalpha_local,
    }, null, 2);
    const jump = $("#backtest-jump-reporting");
    jump.disabled = false;
    jump.dataset.runId = result.run_id || payload.run_id;
    await loadBacktestResultPanel(result.run_id || payload.run_id);
    const elapsed = singleRunState.startedAt ? (Date.now() - singleRunState.startedAt) / 1000 : 0;
    setSingleRunState({
      status: result.status === "failed" ? "failed" : "completed",
      phase: result.status === "failed" ? "单股回测执行失败" : "单股回测完成，结果已载入",
      elapsedSeconds: elapsed,
      startedAt: null,
      result,
      error: result.error_message || "",
    });
    activateBacktestView("results");
    return result;
  } catch (error) {
    const elapsed = singleRunState.startedAt ? (Date.now() - singleRunState.startedAt) / 1000 : 0;
    setSingleRunState({
      status: "failed",
      phase: "单股回测失败：" + error.message,
      elapsedSeconds: elapsed,
      startedAt: null,
      error: error.message,
    });
    throw error;
  }
}
function buildParameterGrid(parameters) {
  const grid = {};
  for (const [key, value] of Object.entries(parameters)) {
    if (typeof value === "number" && Number.isFinite(value)) grid[key] = [value, value + (Number.isInteger(value) ? 1 : 0.1)];
    else grid[key] = [value];
  }
  return grid;
}
function renderScanComparison(report) {
  if (!report) return;
  const rows = report.rows || [];
  const table = renderTable(rows, [
    { key: "rank", label: "Rank" },
    { key: "run_id", label: "Run" },
    { key: "score", label: "Score" },
    { key: "annualized_returns", label: "年化" },
    { key: "max_drawdown", label: "回撤" },
    { key: "sharpe", label: "Sharpe" },
    { key: "status", label: "状态" },
  ]);
  $("#strategy-scan-output").textContent = JSON.stringify({ best_run_id: report.best_run_id, best_parameters: report.best_parameters, recommendation: report.recommendation }, null, 2);
  $("#strategy-version-history").innerHTML = `<strong>${report.title}</strong><p>${report.recommendation}</p>${table}`;
}
async function loadScanComparison(runIdPrefix) {
  const payload = await requestJson(`/api/reporting/parameter-scan/${encodeURIComponent(runIdPrefix)}/comparison`);
  renderScanComparison(payload.report);
  return payload.report;
}
async function saveCurrentScanComparisonSnapshot() {
  if (!currentScanRunIdPrefix) {
    setFeedback("请先执行参数扫描", "error");
    return;
  }
  const payload = await requestJson(`/api/reporting/parameter-scan/${encodeURIComponent(currentScanRunIdPrefix)}/comparison/snapshots`, {
    method: "POST",
    body: JSON.stringify({ report_type: "parameter_scan_comparison", report_version: "parameter-scan-v1" }),
  });
  $("#strategy-scan-output").textContent = JSON.stringify(payload.snapshot, null, 2);
  setFeedback(`扫描对比快照已保存：${payload.snapshot.snapshot_id}`, "success");
  return payload.snapshot;
}
let currentParameterMatrixTaskId = "";
async function createParameterMatrixTask() {
  const form = Object.fromEntries(new FormData($("#backtest-run-form")).entries());
  const parameters = collectStrategyParameters();
  const shortWindow = Number(parameters.short_window || 3);
  const longWindow = Number(parameters.long_window || 5);
  const body = {
    task_id: `${form.run_id || "matrix"}-matrix`,
    run_id_prefix: `${form.run_id || "matrix"}-matrix`,
    strategy_name: form.strategy_name || selectedStrategy?.name || "moving_average_strategy",
    strategy_id: form.strategy_id || selectedStrategy?.strategy_id || "moving_average_strategy",
    strategy_version: form.strategy_version || selectedStrategy?.latest_version || "v1",
    symbol: form.symbol || "000001.XSHE",
    benchmark: form.benchmark || "000300.XSHG",
    start_date: form.start_date || "2020-01-01",
    end_date: form.end_date || "2020-12-31",
    base_parameters: parameters,
    parameter_grid: { short_window: [Math.max(2, shortWindow - 1), shortWindow], long_window: [Math.max(shortWindow + 1, longWindow), Math.max(shortWindow + 2, longWindow + 2)] },
    extra_config: { rqalpha_local: collectRqalphaLocalSettings(form) },
    max_runs: 4,
  };
  const payload = await requestJson("/api/backtest/parameter-matrix-tasks", { method: "POST", body: JSON.stringify(body) });
  currentParameterMatrixTaskId = payload.task?.task_id || body.task_id;
  $("#strategy-matrix-output").textContent = JSON.stringify(payload.task || {}, null, 2);
  await loadExperimentIndex();
  setFeedback(`参数矩阵已创建：${currentParameterMatrixTaskId}`, "success");
  return payload.task;
}
async function runCurrentParameterMatrixTask() {
  if (!currentParameterMatrixTaskId) await createParameterMatrixTask();
  const payload = await requestJson(`/api/backtest/parameter-matrix-tasks/${encodeURIComponent(currentParameterMatrixTaskId)}/run`, { method: "POST", body: JSON.stringify({}) });
  const result = payload.result || {};
  $("#strategy-matrix-output").textContent = JSON.stringify(result, null, 2);
  if (result.best_run_id) await loadBacktestResultPanel(result.best_run_id);
  if (result.run_id_prefix) {
    currentBacktestRunIdPrefix = result.run_id_prefix;
    await loadBacktestPortfolioPanel(result.run_id_prefix);
    await loadBacktestExperimentPanel(result.run_id_prefix);
  }
  await loadExperimentIndex();
  setFeedback(`参数矩阵执行完成：${result.completed_count || 0}/${result.run_count || 0}`, result.status === "completed" ? "success" : "error");
  return result;
}async function runParameterScan() {
  const form = Object.fromEntries(new FormData($("#backtest-run-form")).entries());
  const parameters = collectStrategyParameters();
  const body = {
    run_id_prefix: `${form.run_id || "scan"}-scan`,
    strategy_name: form.strategy_name,
    strategy_id: form.strategy_id || selectedStrategy?.strategy_id,
    strategy_version: form.strategy_version || selectedStrategy?.latest_version || "v1",
    symbol: form.symbol,
    benchmark: form.benchmark,
    start_date: form.start_date,
    end_date: form.end_date,
    base_parameters: parameters,
    parameter_grid: buildParameterGrid(parameters),
    extra_config: { rqalpha_local: buildRqalphaLocalConfig(form) },
    max_runs: 6,
  };
  currentScanRunIdPrefix = body.run_id_prefix;
  const payload = await requestJson("/api/backtest/parameter-scan", { method: "POST", body: JSON.stringify(body) });
  $("#strategy-scan-output").textContent = JSON.stringify(payload, null, 2);
  await loadScanComparison(body.run_id_prefix);
  setFeedback(`参数扫描完成：${(payload.results || []).length} 组，已生成对比报告`, "success");
  return payload;
}
function formatPercent(value) { const n = Number(value); if (!Number.isFinite(n)) return "--"; return `${(Math.abs(n) <= 2 ? n * 100 : n).toFixed(2)}%`; }
function metricValue(metrics, keys, fallback) { for (const key of keys) { if (metrics[key] != null) return metrics[key]; } return fallback; }
function scoreLevel(score) { if (score >= 85) return { text: "优秀", cls: "excellent" }; if (score >= 75) return { text: "良好", cls: "good" }; if (score >= 60) return { text: "合格", cls: "normal" }; return { text: "待优化", cls: "bad" }; }
function renderMiniBars(rows) { const max = Math.max(...rows.map((row) => Math.abs(Number(row.value) || 0)), 1); return `<svg viewBox="0 0 420 170" role="img"><line x1="38" x2="400" y1="130" y2="130" stroke="#d9e1e8"/>${rows.map((row, index) => { const value = Number(row.value) || 0; const h = Math.max(4, Math.abs(value) / max * 92); const x = 54 + index * (320 / Math.max(rows.length, 1)); const y = value >= 0 ? 130 - h : 130; const color = value >= 0 ? "#c43d3d" : "#16845b"; return `<rect x="${x}" y="${y}" width="34" height="${h}" fill="${color}"/><text x="${x + 17}" y="152" text-anchor="middle" font-size="11" fill="#5d6b78">${row.label}</text><text x="${x + 17}" y="${Math.max(14, y - 6)}" text-anchor="middle" font-size="11" fill="#17202a">${row.display || value}</text>`; }).join("")}</svg>`; }
function renderMiniLine(rows, danger = false) { const values = rows.map((row) => Number(row.value) || 0); const max = Math.max(...values, 1); const min = Math.min(...values, 0); const span = max - min || 1; const points = rows.map((row, index) => { const x = 38 + index * (350 / Math.max(rows.length - 1, 1)); const y = 130 - ((Number(row.value) || 0) - min) / span * 100; return `${x},${y}`; }).join(" "); return `<svg viewBox="0 0 420 170" role="img"><line x1="38" x2="400" y1="130" y2="130" stroke="#d9e1e8"/><polyline points="${points}" fill="none" stroke="${danger ? "#16845b" : "#315f9f"}" stroke-width="3"/>${rows.map((row, index) => { const x = 38 + index * (350 / Math.max(rows.length - 1, 1)); const y = 130 - ((Number(row.value) || 0) - min) / span * 100; return `<circle cx="${x}" cy="${y}" r="4" fill="${danger ? "#16845b" : "#315f9f"}"/><text x="${x}" y="152" text-anchor="middle" font-size="11" fill="#5d6b78">${row.label}</text>`; }).join("")}</svg>`; }
function renderRadar(target, dimensions) { const cx = 360, cy = 160, radius = 108; const pointsFor = (scale) => dimensions.map((item, index) => { const angle = -Math.PI / 2 + index * Math.PI * 2 / dimensions.length; return `${cx + Math.cos(angle) * radius * scale},${cy + Math.sin(angle) * radius * scale}`; }).join(" "); const dataPoints = dimensions.map((item, index) => { const angle = -Math.PI / 2 + index * Math.PI * 2 / dimensions.length; const scale = item.score / 100; return { x: cx + Math.cos(angle) * radius * scale, y: cy + Math.sin(angle) * radius * scale, lx: cx + Math.cos(angle) * (radius + 42), ly: cy + Math.sin(angle) * (radius + 28), label: item.short, score: item.score }; }); target.innerHTML = `<svg viewBox="0 0 720 320" role="img" aria-label="策略7维评分雷达图">${[0.2,0.4,0.6,0.8,1].map((s) => `<polygon class="radar-grid" points="${pointsFor(s)}"/>`).join("")}${dimensions.map((_, index) => { const angle = -Math.PI / 2 + index * Math.PI * 2 / dimensions.length; return `<line class="radar-axis" x1="${cx}" y1="${cy}" x2="${cx + Math.cos(angle) * radius}" y2="${cy + Math.sin(angle) * radius}"/>`; }).join("")}<polygon class="radar-shape" points="${dataPoints.map((p) => `${p.x},${p.y}`).join(" ")}"/>${dataPoints.map((p) => `<circle class="radar-point" cx="${p.x}" cy="${p.y}" r="4"/><text class="radar-label" x="${p.lx}" y="${p.ly}" text-anchor="middle">${p.label} ${p.score}</text>`).join("")}</svg>`; }
function buildSevenDimensionReport(run) { const metrics = run.metrics || {}; const yearly = run.yearly_returns || []; const trades = run.trades || []; const positions = run.positions || []; const totalReturn = Number(metricValue(metrics, ["total_returns", "total_return"], 0.128)); const sharpe = Number(metricValue(metrics, ["sharpe", "sharpe_ratio"], 1.12)); const maxDrawdown = Math.abs(Number(metricValue(metrics, ["max_drawdown", "drawdown"], 0.086))); const annualReturn = Number(metricValue(metrics, ["annual_return", "annual_returns"], totalReturn)); const winYears = yearly.filter((row) => Number(row.portfolio_return) > Number(row.benchmark_return || 0)).length; const yearWinRate = yearly.length ? winYears / yearly.length : 0.8; const avgPositionCount = Math.max(positions.length, 3); const dimensions = [{ key:"return", short:"收益真实", title:"维度1：收益真实性", score: Math.min(95, Math.round(70 + Math.max(0, annualReturn) * 120)), level:null, metrics:[["总收益率", formatPercent(totalReturn)],["年化收益率", formatPercent(annualReturn)],["年度胜率", formatPercent(yearWinRate)],["样本内外偏差", "演示 3.98%"]], chart: renderMiniBars((yearly.length ? yearly : [{year:"2020", portfolio_return:0.12, benchmark_return:0.08},{year:"2021", portfolio_return:0.08, benchmark_return:0.04},{year:"2022", portfolio_return:-0.03, benchmark_return:-0.06}]).map((row) => ({ label: String(row.year), value: Number(row.portfolio_return || 0) * 100, display: formatPercent(row.portfolio_return || 0) }))) }, { key:"risk", short:"风险可控", title:"维度2：风险可控性", score: Math.max(55, Math.round(92 - maxDrawdown * 160)), metrics:[["最大回撤", formatPercent(maxDrawdown)],["年化波动率", formatPercent(metricValue(metrics,["volatility","annual_volatility"],0.116))],["最大连续亏损月", "演示 4个月"],["回撤修复时间", "演示 2.1个月"]], chart: renderMiniLine([{label:"起始",value:0},{label:"低点",value:maxDrawdown*100},{label:"修复",value:maxDrawdown*55},{label:"当前",value:maxDrawdown*30}], true) }, { key:"riskReturn", short:"性价比", title:"维度3：风险调整收益", score: Math.min(92, Math.round(60 + sharpe * 18)), metrics:[["Sharpe", sharpe.toFixed(2)],["Calmar", (annualReturn / Math.max(maxDrawdown, 0.01)).toFixed(2)],["Sortino", (sharpe * 1.22).toFixed(2)],["基准 Sharpe", "演示 0.78"]], chart: renderMiniBars([{label:"Sharpe",value:sharpe,display:sharpe.toFixed(2)},{label:"Calmar",value:annualReturn / Math.max(maxDrawdown,0.01),display:(annualReturn / Math.max(maxDrawdown,0.01)).toFixed(2)},{label:"Sortino",value:sharpe*1.22,display:(sharpe*1.22).toFixed(2)}]) }, { key:"stable", short:"收益稳定", title:"维度4：收益稳定性", score: Math.round(65 + yearWinRate * 25), metrics:[["年度胜率", formatPercent(yearWinRate)],["月度胜率", "演示 61.67%"],["平均盈亏比", "演示 1.86"],["最大连续盈利月", "演示 5个月"]], chart: renderMiniBars([{label:"2020",value:3.2},{label:"2021",value:1.8},{label:"2022",value:-1.4},{label:"2023",value:2.1},{label:"2024",value:2.7}]) }, { key:"attr", short:"归因合理", title:"维度5：业绩归因合理性", score: 84, metrics:[["牛市年化", "演示 32.56%"],["熊市年化", "演示 -4.23%"],["震荡市年化", "演示 11.89%"],["主因子贡献", "演示 82%"]], chart: renderMiniBars([{label:"牛市",value:32.56},{label:"熊市",value:-4.23},{label:"震荡",value:11.89}]) }, { key:"cost", short:"成本容量", title:"维度6：成本与容量适配性", score: Math.max(62, 82 - Math.round(trades.length / 3)), metrics:[["交易笔数", trades.length || "演示 2"],["成本侵蚀率", "演示 1.57%"],["容量上限", "演示 5亿"],["滑点冲击", "演示 0.32%"]], chart: renderMiniLine([{label:"0%",value:15.9},{label:"0.03%",value:14.3},{label:"0.06%",value:13.1},{label:"0.1%",value:11.6},{label:"0.2%",value:8.8}]) }, { key:"diverse", short:"持仓分散", title:"维度7：持仓分散度", score: Math.min(92, 72 + avgPositionCount * 4), metrics:[["单票最大权重", "演示 3.33%"],["行业最大占比", "演示 28%"],["平均持仓数", avgPositionCount],["跌停冲击", "演示 0.33%"]], chart: renderMiniBars([{label:"换手",value:360},{label:"单票",value:3.33},{label:"行业",value:28},{label:"冲击",value:0.33}]) }]; dimensions.forEach((item) => { item.level = scoreLevel(item.score); }); return dimensions; }
function renderEvaluationChart(chart) { const rows = chart?.rows || []; if (!rows.length) return '<div class="empty-cell">暂无图表数据</div>'; if ((chart.kind || "").startsWith("line")) return renderMiniLine(rows, chart.kind === "line-danger"); return renderMiniBars(rows); }
function normalizeEvaluationDimension(item) { const levelMap = { excellent: "优秀", good: "良好", normal: "合格", bad: "待优化" }; return { key: item.key, short: item.short_label || item.short || item.title, title: item.title, score: item.score, level: { cls: item.level || scoreLevel(item.score).cls, text: levelMap[item.level] || scoreLevel(item.score).text }, metrics: (item.metrics || []).map((metric) => [metric.label, metric.value]), chart: renderEvaluationChart(item.chart) }; }
function normalizeEvaluationReport(report) { if (!report?.dimensions) return null; return { average: report.average_score, dimensions: report.dimensions.map(normalizeEvaluationDimension), conclusions: report.conclusions || [], notes: report.data_quality_notes || [], diagnostics: report.diagnostics || {}, scoreBreakdown: report.score_breakdown || {}, decisionFlags: report.decision_flags || [] }; }
function renderReportAnalysisSummary(report = {}) {
  const summary = report.analysis_summary || {};
  const asset = summary.data_asset || {};
  const headline = $("#report-analysis-headline");
  if (headline) headline.textContent = summary.headline || "暂无分析摘要";
  const cardsTarget = $("#report-analysis-cards");
  if (cardsTarget) {
    cardsTarget.innerHTML = (summary.cards || []).map((card) => `<article class="analysis-card analysis-card-${card.key || "item"}"><strong>${card.label || card.key || "指标"}</strong><span>${card.value ?? "-"}</span><small>${card.detail || "-"}</small></article>`).join("") || '<div class="empty-cell">暂无分析卡片</div>';
  }
  const sourceText = Object.entries(asset.source_counts || {}).map(([key, value]) => `${key}:${value}`).join(", ") || "-";
  const assetTarget = $("#report-data-asset-summary");
  if (assetTarget) {
    assetTarget.innerHTML = [
      ["分析结论", summary.verdict || "unknown"],
      ["数据绑定", asset.status || "not_bound"],
      ["标的", asset.symbol || "-"],
      ["数据版本", asset.data_version || "-"],
      ["质量", asset.quality_status || "-"],
      ["覆盖", asset.coverage_status || "-"],
      ["行数", asset.row_count ?? "-"],
      ["来源", sourceText],
    ].map(([label, value]) => `<div class="asset-chip"><strong>${label}</strong><span>${value}</span></div>`).join("");
  }
  const actionTarget = $("#report-action-items");
  if (actionTarget) actionTarget.innerHTML = (summary.action_items || []).map((item, index) => `<article class="report-action-item"><strong>${index + 1}</strong><p>${item}</p><span>${summary.version || "stage50"}</span></article>`).join("") || '<div class="empty-cell">暂无行动项</div>';
}
function renderStrategyDiagnostics(normalized) {
  const diagnostics = normalized?.diagnostics || {};
  const risk = diagnostics.risk || {};
  const trade = diagnostics.trade_quality || {};
  const cost = diagnostics.capacity_cost || {};
  const exposure = diagnostics.exposure || {};
  const dataQuality = diagnostics.data_quality || {};
  renderSummaryGrid($("#report-diagnostics-grid"), [
    { label: "最大回撤", value: formatPercent(risk.max_drawdown || 0) },
    { label: "当前回撤", value: formatPercent(risk.current_drawdown || 0) },
    { label: "区间波动", value: formatPercent(risk.volatility || 0) },
    { label: "交易活跃点", value: trade.trade_count ?? 0 },
    { label: "估算胜率", value: formatPercent(trade.estimated_win_rate || 0) },
    { label: "估算成本", value: cost.estimated_cost ?? 0 },
    { label: "最新持仓数", value: exposure.latest_holding_count ?? 0 },
    { label: "数据覆盖", value: formatPercent(dataQuality.coverage_score || 0) },
  ]);
  renderSummaryGrid($("#report-decision-flags"), (normalized?.decisionFlags || []).map((flag) => ({ label: flag.label || flag.key, value: `${flag.value ?? ""} / ${flag.level || "watch"}` })));
  const scoreTarget = $("#report-score-breakdown");
  if (scoreTarget) scoreTarget.textContent = JSON.stringify({ score_breakdown: normalized?.scoreBreakdown || {}, diagnostics }, null, 2);
}function renderSevenDimensionReport(run, evaluationReport = null) {
  const normalized = normalizeEvaluationReport(evaluationReport);
  const dimensions = normalized?.dimensions || buildSevenDimensionReport(run);
  const average = normalized?.average || Math.round(dimensions.reduce((sum, item) => sum + item.score, 0) / dimensions.length);
  renderRadar($("#report-radar"), dimensions);
  $("#report-score-summary").textContent = `综合评分 ${average}/100；核心逻辑：能不能做、做得好不好、能做多久。`;
  $("#report-dimension-grid").innerHTML = dimensions.map((item) => `<article class="dimension-card ${item.key === "diverse" ? "is-wide" : ""}"><div class="dimension-title"><h4>${item.title}</h4><span class="score-tag ${item.level.cls}">${item.level.text} ${item.score}</span></div><div class="dimension-metrics">${item.metrics.map(([label, value]) => `<div class="dimension-metric"><span>${label}</span><strong>${value}</strong></div>`).join("")}</div><div class="mini-chart">${item.chart}</div></article>`).join("");
  const conclusions = normalized?.conclusions?.length ? normalized.conclusions : [
    `核心结论：当前策略综合评分 ${average}/100，基于本地 MVP 数据可进入继续观察与参数优化阶段，暂不等同于真实实盘承诺。`,
    "核心优势：收益、风险调整收益和持仓分散维度表现较好，报告已将 SleeperCloudQuant-old 的 seven-dimension 模板转化为可刷新 Web 视图。",
    "待优化点：真实数据源、完整交易成本、行业归因和样本外检验仍需在后续接入正式数据后复核。",
    "实盘建议：当前仅建议用于本地研究和验收；进入实盘前必须补齐数据授权、风控阈值、容量评估和人工审批。",
  ];
  $("#report-conclusion").innerHTML = conclusions.map((text, index) => `<p><strong>${index + 1}. </strong>${text}</p>`).join("") + ((normalized?.notes || []).length ? `<p><strong>数据质量：</strong>${normalized.notes.join("；")}</p>` : "");
}
function renderTable(rows, columns) { return '<div class="table-wrap"><table><thead><tr>' + columns.map((c) => '<th>' + c.label + '</th>').join("") + '</tr></thead><tbody>' + ((rows || []).map((row) => '<tr>' + columns.map((c) => '<td class="' + financialToneForLabel(c.label, row[c.key]) + '">' + (row[c.key] ?? "") + '</td>').join("") + '</tr>').join("") || '<tr><td colspan="' + columns.length + '" class="empty-cell">暂无数据</td></tr>') + '</tbody></table></div>'; }function renderReportAIWorkflow(replay) {
  if (!replay?.linked) {
    renderSummaryGrid($("#report-ai-workflow-summary"), [{ label: "关联状态", value: "未关联" }, { label: "原因", value: replay?.reason || "暂无 AI workflow" }]);
    $("#report-ai-workflow-timeline").innerHTML = '<div class="empty-cell">暂无 AI workflow 阶段留痕</div>';
    $("#report-ai-workflow-risk").innerHTML = '<div class="empty-cell">暂无风险委员会意见</div>';
    $("#report-ai-workflow-detail").textContent = JSON.stringify(replay || {}, null, 2);
    return;
  }
  renderSummaryGrid($("#report-ai-workflow-summary"), [
    { label: "Workflow", value: replay.workflow_id },
    { label: "标的", value: replay.symbol },
    { label: "Provider", value: replay.provider_mode },
    { label: "组合经理动作", value: replay.portfolio_decision?.action || "unknown" },
  ]);
  $("#report-ai-workflow-timeline").innerHTML = (replay.timeline || []).map((item) => `<article class="definition-item"><h4>${item.stage} / ${item.status}</h4><p>${item.summary}</p><span>${item.artifact}</span></article>`).join("") || '<div class="empty-cell">暂无阶段留痕</div>';
  const riskRows = [
    ...(replay.risk_votes || []).map((item) => ({ title: item.agent, body: item.content, meta: item.vote })),
    { title: "Portfolio Manager", body: replay.portfolio_decision?.rationale || "", meta: replay.portfolio_decision?.action || "" },
  ];
  $("#report-ai-workflow-risk").innerHTML = riskRows.map((item) => `<article class="definition-item"><h4>${item.title}</h4><p>${item.body}</p><span>${item.meta}</span></article>`).join("") || '<div class="empty-cell">暂无风险意见</div>';
  $("#report-ai-workflow-detail").textContent = JSON.stringify({ config: replay.workflow_config, summary_notes: replay.summary_notes, data_quality_notes: replay.data_quality_notes, llm_provider_trace: replay.llm_provider_trace }, null, 2);
}

function downloadTextFile(filename, content, contentType) {
  const blob = new Blob([content], { type: contentType || "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "report-package.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function exportSelectedReportPackage(format = "html") {
  if (!selectedReportPackageId) {
    setFeedback("请先创建或选择研究报告包", "error");
    return;
  }
  const payload = await requestJson(`/api/reporting/report-packages/${encodeURIComponent(selectedReportPackageId)}/export?format=${encodeURIComponent(format)}`);
  const exported = payload.export || {};
  downloadTextFile(exported.filename, exported.content || "", exported.content_type);
  setFeedback(`研究报告包已导出：${exported.filename}`, "success");
}
async function loadReportPackages(runId) {
  const payload = await requestJson(`/api/reporting/run-detail/${encodeURIComponent(runId)}/report-packages`);
  const packages = payload.packages || [];
  const target = $("#report-package-list");
  if (!target) return packages;
  target.innerHTML = packages.map((item) => `<article class="definition-item strategy-card" data-report-package="${item.package_id}"><h4>${item.title}</h4><p>${item.created_at} / ${item.binding_mode}</p><span>Manifest: ${item.manifest_version || "未记录"} / ${item.workflow_id || "无 workflow"} / ${item.snapshot_id || "无 snapshot"}</span></article>`).join("") || '<div class="empty-cell">暂无研究报告包</div>';
  document.querySelectorAll("[data-report-package]").forEach((card) => card.addEventListener("click", async () => {
    selectedReportPackageId = card.dataset.reportPackage;
    const detail = await requestJson(`/api/reporting/report-packages/${encodeURIComponent(card.dataset.reportPackage)}`);
    $("#report-package-detail").textContent = JSON.stringify(detail.package, null, 2);
    setFeedback("研究报告包已读取", "success");
  }));
  return packages;
}


async function loadReportPackageDirectory(options = {}) {
  const runId = options.run_id ?? $("#report-package-directory-run-id")?.value ?? currentReportRunId;
  const packageType = options.package_type ?? $("#report-package-directory-type")?.value ?? "";
  const limit = options.limit ?? $("#report-package-directory-limit")?.value ?? 20;
  const query = buildQuery({ run_id: runId, package_type: packageType, limit });
  const payload = await requestJson(`/api/reporting/report-packages${query ? `?${query}` : ""}`);
  const directory = payload.directory || {};
  const packages = directory.packages || [];
  const summary = directory.summary || {};
  const summaryTarget = $("#report-package-directory-summary");
  if (summaryTarget) {
    renderSummaryGrid(summaryTarget, [
      { label: "包数量", value: summary.package_count ?? 0 },
      { label: "筛选 Run", value: summary.filters?.run_id || "全部" },
      { label: "筛选类型", value: summary.filters?.package_type || "全部" },
      { label: "类型分布", value: JSON.stringify(summary.type_counts || {}) },
    ]);
  }
  const list = $("#report-package-directory-list");
  if (list) {
    list.innerHTML = packages.map((item) => `<article class="definition-item strategy-card" data-report-package-directory="${item.package_id}"><h4>${item.title || item.package_id}</h4><p>${item.package_type || "unknown"} / ${item.lifecycle_status || "active"} / ${item.created_at || ""}</p><span>${item.run_id || ""} / ${item.binding_mode || ""} / ${item.manifest_version || "未记录"} / ${item.retention_policy || "standard"}</span></article>`).join("") || '<div class="empty-cell">暂无报告包归档</div>';
    document.querySelectorAll("[data-report-package-directory]").forEach((card) => card.addEventListener("click", async () => {
      selectedReportPackageId = card.dataset.reportPackageDirectory;
      const detail = await requestJson(`/api/reporting/report-packages/${encodeURIComponent(selectedReportPackageId)}`);
      $("#report-package-detail").textContent = JSON.stringify(detail.package, null, 2);
      $("#report-package-directory-output").textContent = JSON.stringify(detail.package, null, 2);
      setFeedback("报告包归档已读取", "success");
    }));
  }
  const output = $("#report-package-directory-output");
  if (output) output.textContent = JSON.stringify(directory, null, 2);
  return directory;
}


async function createReportPackageExportManifest() {
  const runId = $("#report-package-directory-run-id")?.value ?? currentReportRunId;
  const packageType = $("#report-package-directory-type")?.value ?? "";
  const lifecycleStatus = $("#report-package-directory-lifecycle")?.value ?? "";
  const limit = $("#report-package-directory-limit")?.value ?? 20;
  const formats = $("#report-package-export-manifest-formats")?.value ?? "html,json";
  const query = buildQuery({ run_id: runId, package_type: packageType, lifecycle_status: lifecycleStatus, formats, limit });
  const payload = await requestJson(`/api/reporting/report-packages/export-manifest${query ? `?${query}` : ""}`);
  const manifest = payload.manifest || {};
  const output = $("#report-package-export-manifest-output");
  if (output) output.textContent = JSON.stringify(manifest, null, 2);
  setFeedback(`报告包导出清单已生成：${manifest.package_count || 0} 个包`, "success");
  return manifest;
}
async function updateSelectedReportPackageLifecycle(status, options = {}) {
  if (!selectedReportPackageId) {
    setFeedback("请先在报告包目录中选择一个报告包", "error");
    return null;
  }
  const payload = await requestJson(`/api/reporting/report-packages/${encodeURIComponent(selectedReportPackageId)}/lifecycle`, {
    method: "POST",
    body: JSON.stringify({
      status,
      retention_policy: options.retention_policy || (status === "archived" ? "retain-local-audit" : "standard"),
      protected: Boolean(options.protected),
      reason: options.reason || `stage56 ${status}`,
      updated_by: "web-reporting-center",
    }),
  });
  $("#report-package-detail").textContent = JSON.stringify(payload.package, null, 2);
  $("#report-package-directory-output").textContent = JSON.stringify(payload.package, null, 2);
  await loadReportPackageDirectory();
  setFeedback(`报告包生命周期已更新：${status}`, "success");
  return payload.package;
}
async function createExperimentComparisonPackage() {
  const prefix = currentReportExperimentId || currentReportRunId.replace(/-\d+$/, "");
  const payload = await requestJson(`/api/reporting/experiments/${encodeURIComponent(prefix)}/comparison-package`, {
    method: "POST",
    body: JSON.stringify({ title: `${prefix} 实验对比报告包` }),
  });
  selectedReportPackageId = payload.package.package_id;
  $("#report-package-detail").textContent = JSON.stringify(payload.package, null, 2);
  await loadReportPackages(prefix);
  setFeedback(`实验对比报告包已创建：${payload.package.package_id}`, "success");
  return payload.package;
}
async function createCurrentReportPackage() {
  const payload = await requestJson(`/api/reporting/run-detail/${encodeURIComponent(currentReportRunId)}/report-package`, {
    method: "POST",
    body: JSON.stringify({ symbol: "000001.XSHE", title: `${currentReportRunId} 研究报告包` }),
  });
  selectedReportPackageId = payload.package.package_id;
  $("#report-package-detail").textContent = JSON.stringify(payload.package, null, 2);
  await loadReportPackages(currentReportRunId);
  setFeedback(`研究报告包已创建：${payload.package.package_id}`, "success");
  return payload.package;
}
function shortRunLabel(runId = "") {
  const parts = String(runId || "").split("-");
  return parts.slice(-2).join("-") || runId || "run";
}
function renderComparisonBarSvg(rows, key, { title, danger = false, percent = false } = {}) {
  const values = rows.map((row) => Number(row[key]) || 0);
  const max = Math.max(...values.map((value) => Math.abs(value)), 1);
  const width = 520, height = 210, pad = 34;
  const barW = Math.max(18, Math.min(46, (width - pad * 2) / Math.max(rows.length, 1) - 12));
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${title || key}"><text x="${pad}" y="20" class="axis-label">${title || key}</text><line x1="${pad}" x2="${width - pad}" y1="150" y2="150" class="grid-line"/>${rows.map((row, index) => { const value = Number(row[key]) || 0; const h = Math.max(4, Math.abs(value) / max * 104); const x = pad + index * ((width - pad * 2) / Math.max(rows.length, 1)) + 8; const y = value >= 0 ? 150 - h : 150; const color = danger ? "#16845b" : (value >= 0 ? "#c43d3d" : "#16845b"); const display = percent ? formatPercent(value) : String(Math.round(value * 100) / 100); return `<rect x="${x}" y="${y}" width="${barW}" height="${h}" fill="${color}"/><text x="${x + barW / 2}" y="${Math.max(34, y - 6)}" text-anchor="middle" font-size="11" fill="#17202a">${display}</text><text x="${x + barW / 2}" y="174" text-anchor="middle" font-size="10" fill="#5d6b78">${shortRunLabel(row.run_id)}</text>`; }).join("")}</svg>`;
}
function renderExperimentComparisonCharts(comparison = {}) {
  const rows = comparison.rows || [];
  const summary = comparison.summary || {};
  const target = $("#report-experiment-comparison-charts");
  if (!target) return;
  if (!rows.length) { target.innerHTML = '<div class="empty-cell">暂无实验对比图表</div>'; return; }
  const versionText = (summary.data_versions || []).join(", ") || "-";
  target.innerHTML = `
    <article class="comparison-chart"><h4>评分排名</h4>${renderComparisonBarSvg(rows, "score", { title: "Score" })}</article>
    <article class="comparison-chart"><h4>年化收益</h4>${renderComparisonBarSvg(rows, "annualized_return", { title: "Annualized", percent: true })}</article>
    <article class="comparison-chart"><h4>最大回撤</h4>${renderComparisonBarSvg(rows, "max_drawdown", { title: "Drawdown", danger: true, percent: true })}</article>
    <article class="comparison-chart comparison-version"><h4>数据版本一致性</h4><div class="version-strip"><strong>${summary.asset_consistency_status || "empty"}</strong><span>${summary.data_version_count ?? 0} 个版本 / 缺失 ${summary.missing_data_version_count ?? 0}</span><small>${versionText}</small></div></article>`;
}
function renderExperimentReportComparison(comparison = {}) {
  const summary = comparison.summary || {};
  renderSummaryGrid($("#report-experiment-comparison-summary"), [
    { label: "状态", value: comparison.status || "unknown" },
    { label: "Run 数", value: summary.run_count ?? 0 },
    { label: "最佳 Run", value: summary.best_run_id || "-" },
    { label: "最佳评分", value: summary.best_score ?? "-" },
    { label: "最差 Run", value: summary.worst_run_id || "-" },
    { label: "资产一致性", value: summary.asset_consistency_status || "empty" },
    { label: "数据版本数", value: summary.data_version_count ?? 0 },
    { label: "缺失版本", value: summary.missing_data_version_count ?? 0 },
  ]);
  const rows = comparison.rows || [];
  const tableTarget = $("#report-experiment-comparison-table");
  if (tableTarget) tableTarget.innerHTML = renderTable(rows, [
    { key: "rank", label: "Rank" },
    { key: "run_id", label: "Run" },
    { key: "score", label: "评分" },
    { key: "verdict", label: "结论" },
    { key: "annualized_return", label: "年化" },
    { key: "max_drawdown", label: "回撤" },
    { key: "data_version", label: "数据版本" },
    { key: "quality_status", label: "质量" },
  ]);
  const output = $("#report-experiment-comparison-output");
  if (output) output.textContent = JSON.stringify(comparison, null, 2);
}
async function loadExperimentReportComparison(runIdPrefix) {
  if (!runIdPrefix) return null;
  const payload = await requestJson(`/api/reporting/experiments/${encodeURIComponent(runIdPrefix)}/comparison`);
  renderExperimentReportComparison(payload.comparison || {});
  return payload.comparison;
}
function renderIndependentModeReport(report = {}) {
  const scope = report.sample_scope || {};
  const distribution = report.distribution || {};
  const coverage = report.classification_coverage || {};
  renderSummaryGrid($("#mode-report-summary"), [
    { label: "任务状态", value: report.status || "unknown" },
    { label: "股票池", value: scope.universe_count ?? 0 },
    { label: "实际建仓", value: scope.entered_count ?? 0 },
    { label: "平均收益", value: distribution.mean == null ? "-" : formatPercent(distribution.mean) },
    { label: "收益中位数", value: distribution.median == null ? "-" : formatPercent(distribution.median) },
    { label: "亏损概率", value: distribution.loss_probability == null ? "-" : formatPercent(distribution.loss_probability) },
    { label: "VaR 95%", value: distribution.var_95 == null ? "-" : formatPercent(distribution.var_95) },
    { label: "正态性", value: distribution.normality?.reject_normality == null ? "样本不足" : (distribution.normality.reject_normality ? "拒绝正态" : "未拒绝正态") },
  ]);
  const histogram = distribution.histogram || [];
  const maxCount = Math.max(...histogram.map((row) => Number(row.count) || 0), 1);
  const histogramHtml = histogram.length ? `<div class="bar-chart">${histogram.map((row) => `<div class="bar-row"><span>${formatPercent(row.lower)} 至 ${formatPercent(row.upper)}</span><div class="bar-track"><i style="width:${(Number(row.count) || 0) / maxCount * 100}%"></i></div><strong>${row.count}</strong></div>`).join("")}</div>` : '<div class="empty-cell">样本不足，无法生成分布图</div>';
  const groupSections = Object.entries(report.group_comparisons || {}).map(([dimension, rows]) => `<h4>${{market:"市场比较",entry_period:"建仓时段比较",industry:"历史行业比较",concept:"历史概念比较"}[dimension] || dimension}</h4>${renderTable(rows || [], [{key:"category",label:"分类"},{key:"sample_size",label:"样本"},{key:"mean",label:"平均收益"},{key:"median",label:"中位数"},{key:"stddev",label:"标准差"},{key:"positive_probability",label:"正收益概率"}])}`).join("");
  $("#mode-report-content").innerHTML = `<h4>建仓股票收益分布</h4>${histogramHtml}<h4>正态性与置信区间</h4>${renderTable([{test:distribution.normality?.test,status:distribution.normality?.status,statistic:distribution.normality?.statistic,p_value:distribution.normality?.p_value,interpretation:distribution.normality?.interpretation,ci:(distribution.mean_confidence_interval_95 || []).join(" ~ "),bootstrap_ci:(distribution.bootstrap_mean_confidence_interval_95 || []).join(" ~ ")}],[{key:"test",label:"检验"},{key:"status",label:"状态"},{key:"statistic",label:"统计量"},{key:"p_value",label:"p 值"},{key:"ci",label:"均值 95% CI"},{key:"bootstrap_ci",label:"Bootstrap 95% CI"},{key:"interpretation",label:"解释"}])}${groupSections}<h4>历史分类覆盖率</h4>${renderTable(Object.entries(coverage).map(([dimension, value]) => ({dimension,...value})),[{key:"dimension",label:"维度"},{key:"covered_count",label:"已覆盖"},{key:"missing_count",label:"缺失"},{key:"coverage_ratio",label:"覆盖率"}])}`;
  $("#mode-report-output").textContent = JSON.stringify({ methodology: report.methodology, data_quality_notes: report.data_quality_notes, professional_sections: report.professional_sections }, null, 2);
}
async function loadBacktestModeReport(event) {
  if (event) event.preventDefault();
  const form = $("#mode-report-form");
  const values = Object.fromEntries(new FormData(form).entries());
  if (!values.task_id) throw new Error("请输入回测任务 ID");
  const payload = await requestJson(`/api/reporting/backtest-modes/${encodeURIComponent(values.mode)}/${encodeURIComponent(values.task_id)}`);
  const report = payload.report || {};
  if (values.mode === "shared-portfolio") {
    const professional = report.professional_report || {};
    renderSummaryGrid($("#mode-report-summary"), [
      { label: "任务状态", value: report.status || "unknown" },
      { label: "Run ID", value: report.run_id || "-" },
      { label: "专业模板", value: report.template || "-" },
      { label: "综合评分", value: professional.average_score ?? "-" },
    ]);
    $("#mode-report-content").innerHTML = professional.dimensions ? renderTable(professional.dimensions.map((item) => ({dimension:item.title,score:item.score,level:item.level})), [{key:"dimension",label:"维度"},{key:"score",label:"评分"},{key:"level",label:"等级"}]) : '<div class="empty-cell">组合任务尚未产生可用 run</div>';
    $("#mode-report-output").textContent = JSON.stringify(report, null, 2);
    if (report.run_id && report.status === "completed") await loadReports(report.run_id, report.run_id.replace(/-shared-portfolio$/, ""));
  } else {
    renderIndependentModeReport(report);
  }
  setFeedback(`双模式报告已生成：${values.task_id}`, "success");
  return report;
}async function loadReports(runId = "phase1-demo-run-001", experimentId = "phase1-batch-001") {
  currentReportRunId = runId;
  currentReportExperimentId = experimentId || runId.replace(/-\d+$/, "");
  const directoryRunInput = $("#report-package-directory-run-id");
  if (directoryRunInput) directoryRunInput.value = currentReportRunId;
  const [detail, batch, evaluation, aiReplay] = await Promise.all([requestJson(`/api/reporting/run-detail/${encodeURIComponent(runId)}`), requestJson(`/api/reporting/batch-summary/${encodeURIComponent(experimentId)}`), requestJson(`/api/reporting/strategy-evaluation/${encodeURIComponent(runId)}`), requestJson(`/api/reporting/run-detail/${encodeURIComponent(runId)}/ai-workflow?symbol=000001.XSHE`)]);
  const run = detail.detail || {}; renderSummaryGrid($("#run-detail-summary"), [{ label: "Run ID", value: run.run_id || runId }, { label: "状态", value: run.status || "unknown" }, { label: "策略", value: run.strategy_name || "" }, { label: "指标数", value: Object.keys(run.metrics || {}).length }]);
  renderSummaryGrid($("#report-metrics"), Object.entries(run.metrics || {}).map(([label, value]) => ({ label, value })));
  $("#report-logs").textContent = JSON.stringify(run.logs || [], null, 2);
  $("#report-rich-sections").innerHTML = `<h4>交易明细</h4>${renderTable(run.trades || [], [{key:"trade_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"side",label:"方向"},{key:"price",label:"价格"},{key:"quantity",label:"数量"}])}<h4>持仓快照</h4>${renderTable(run.positions || [], [{key:"snapshot_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"quantity",label:"数量"},{key:"market_value",label:"市值"}])}<h4>账户快照</h4>${renderTable(run.accounts || [], [{key:"snapshot_time",label:"时间"},{key:"total_value",label:"总资产"},{key:"cash",label:"现金"},{key:"unit_net_value",label:"单位净值"}])}<h4>年度收益</h4>${renderTable(run.yearly_returns || [], [{key:"year",label:"年度"},{key:"portfolio_return",label:"组合收益"},{key:"benchmark_return",label:"基准收益"},{key:"excess_return",label:"超额收益"}])}`;
  renderSevenDimensionReport(run, evaluation.report);
  renderReportAIWorkflow(aiReplay.replay);
  const rows = batch.summary?.rows || []; renderSummaryGrid($("#batch-summary-summary"), [{ label: "Experiment", value: batch.summary?.experiment_id || experimentId }, { label: "状态", value: batch.summary?.status || "unknown" }, { label: "成功", value: batch.summary?.success_count ?? 0 }, { label: "失败", value: batch.summary?.failure_count ?? 0 }]); $("#batch-summary-body").innerHTML = rows.map((row) => `<tr><td>${row.rank ?? ""}</td><td>${row.run_id ?? ""}</td><td>${row.status ?? ""}</td><td>${row.total_returns ?? ""}</td><td>${row.sharpe ?? ""}</td></tr>`).join("") || '<tr><td colspan="5" class="empty-cell">暂无批量记录</td></tr>';
  await loadReportSnapshots(runId);
  await loadReportPackages(runId);
  await loadReportPackageDirectory({ run_id: runId });
  return { detail, batch, evaluation, aiReplay };
}

async function loadReportSnapshots(runId) {
  const payload = await requestJson(`/api/reporting/run-detail/${encodeURIComponent(runId)}/snapshots`);
  const snapshots = payload.snapshots || [];
  const target = $("#report-snapshot-list");
  if (!target) return snapshots;
  target.innerHTML = snapshots.map((snapshot) => `<article class="definition-item strategy-card" data-snapshot="${snapshot.snapshot_id}"><h4>${snapshot.title}</h4><p>${snapshot.created_at} / ${snapshot.report_version}</p><span>${snapshot.snapshot_id}</span></article>`).join("") || '<div class="empty-cell">暂无报告快照</div>';
  document.querySelectorAll("[data-snapshot]").forEach((card) => card.addEventListener("click", async () => {
    const detail = await requestJson(`/api/reporting/snapshots/${encodeURIComponent(card.dataset.snapshot)}`);
    $("#report-snapshot-detail").textContent = JSON.stringify(detail.snapshot, null, 2);
    setFeedback("报告快照已读取", "success");
  }));
  return snapshots;
}
async function saveCurrentReportSnapshot() {
  const payload = await requestJson(`/api/reporting/strategy-evaluation/${encodeURIComponent(currentReportRunId)}/snapshots`, { method: "POST", body: JSON.stringify({ report_type: "strategy_evaluation", report_version: "three2-v1" }) });
  $("#report-snapshot-detail").textContent = JSON.stringify(payload.snapshot, null, 2);
  await loadReportSnapshots(currentReportRunId);
  setFeedback(`报告快照已保存：${payload.snapshot.snapshot_id}`, "success");
}
function renderWorkflow(workflow) {
  if (!workflow) return;
  $("#ai-workflow-timeline").innerHTML = (workflow.timeline || []).map((item) => `<article class="definition-item"><h4>${item.stage} / ${item.status}</h4><p>${item.summary}</p><span>${item.artifact}</span></article>`).join("") || '<div class="empty-cell">暂无工作流状态</div>';
  const artifactRows = [
    ...(workflow.agent_messages || []).map((item) => ({ title: item.agent, body: item.content, meta: `${item.stage} / ${item.status} / ${item.artifact_key}` })),
    ...(workflow.debate_rounds || []).flatMap((round) => (round.messages || []).map((item) => ({ title: `${item.agent} R${round.round}`, body: item.content, meta: item.stance }))),
    ...(workflow.risk_votes || []).map((item) => ({ title: item.agent, body: item.content, meta: item.vote })),
  ];
  $("#ai-workflow-artifacts").innerHTML = artifactRows.map((item) => `<article class="definition-item"><h4>${item.title}</h4><p>${item.body}</p><span>${item.meta}</span></article>`).join("") || '<div class="empty-cell">暂无中间产物</div>';
}
function buildAIWorkflowRequestConfig(configStatus) {
  const settings = configStatus?.status?.runtime_settings || {};
  const agent = configStatus?.status?.agent_settings || {};
  const workflow = settings.ai_workflow || {};
  return {
    max_debate_rounds: Number(workflow.max_debate_rounds ?? agent.max_debate_rounds ?? 1),
    enabled_analysts: workflow.enabled_analysts || agent.analysts || [],
    enabled_researchers: workflow.enabled_researchers || agent.researchers || [],
    risk_team: workflow.risk_team || agent.risk_team || [],
    provider_profile: workflow.provider_profile || agent.provider_profile || settings.llm_provider_mode || "local-demo-tradingagents-style",
    decision_policy: workflow.decision_policy || agent.decision_policy || "watchlist_only_until_real_data",
  };
}
async function loadAIWorkflowHistory(symbol = "000001.XSHE") {
  const query = buildQuery({ symbol, limit: 20 });
  const payload = await requestJson(`/api/ai/workflows?${query}`);
  const workflows = payload.workflows || [];
  const target = $("#ai-workflow-history");
  if (!target) return workflows;
  target.innerHTML = workflows.map((item) => `<article class="definition-item strategy-card" data-ai-workflow="${item.workflow_id}"><h4>${item.symbol} / ${item.status}</h4><p>${item.generated_at} / ${item.provider_mode}</p><span>${item.workflow_id} / ${item.debate_round_count} 轮 / ${item.decision_action}</span></article>`).join("") || '<div class="empty-cell">暂无 AI workflow 历史</div>';
  document.querySelectorAll("[data-ai-workflow]").forEach((card) => card.addEventListener("click", async () => {
    const detail = await requestJson(`/api/ai/workflow/${encodeURIComponent(card.dataset.aiWorkflow)}`);
    $("#ai-workflow-detail").textContent = JSON.stringify(detail.workflow, null, 2);
    renderWorkflow(detail.workflow);
    setFeedback("AI 工作流历史已读取", "success");
  }));
  return workflows;
}
async function runAI(symbol = "000001.XSHE", analysisDate = "2020-01-02") {
  const configStatus = await requestJson("/api/config/status");
  const workflowConfig = buildAIWorkflowRequestConfig(configStatus);
  const [payload, workflowPayload] = await Promise.all([
    requestJson("/api/ai/analyze", { method: "POST", body: JSON.stringify({ symbol, analysis_date: analysisDate }) }),
    requestJson("/api/ai/workflow/run", { method: "POST", body: JSON.stringify({ symbol, analysis_date: analysisDate, ...workflowConfig }) }),
  ]);
  const report = payload.report || {};
  const workflow = workflowPayload.workflow || {};
  $("#ai-report-title").textContent = report.title || "结构化报告";
  $("#ai-report").innerHTML = [["状态", report.status], ["Provider", `${workflow.provider_mode || report.provider_mode} / ${workflow.llm_provider_trace?.status || "local"}`], ["Workflow", workflow.workflow_id || report.workflow_state?.workflow_id], ["运行配置", `${(workflow.enabled_analysts || []).join(",")} / ${(workflow.enabled_researchers || []).join(",")} / ${(workflow.risk_team || []).join(",")} / ${workflow.max_debate_rounds || 1}轮`], ["数据依据", (report.data_basis || []).join(" / ")], ["核心摘要", (report.highlights || []).join("\n")], ["免责声明", report.disclaimer]].map(([label, value]) => `<article><strong>${label}</strong><p>${String(value || "")}</p></article>`).join("");
  renderCards($("#ai-analysts"), report.analyst_team || [], "role", "summary", "status");
  renderCards($("#ai-debate"), report.research_debate || [], "speaker", "argument", "stance");
  renderCards($("#ai-risk"), report.risk_committee || [], "role", "view", "vote");
  renderSummaryGrid($("#ai-decision"), Object.entries(report.portfolio_decision || {}).map(([label, value]) => ({ label, value: typeof value === "object" ? JSON.stringify(value) : value })));
  renderWorkflow(workflow);
  if ($("#ai-workflow-detail")) $("#ai-workflow-detail").textContent = JSON.stringify(workflow, null, 2);
  await loadAIWorkflowHistory(symbol);
  return report;
}
async function loadConfig() {
  const [status, profiles] = await Promise.all([requestJson("/api/config/status"), requestJson("/api/config/backtest-profiles")]);
  const cfg = status.status || {};
  renderCards($("#config-data-sources"), cfg.data_sources || [], "name", "status", "mode");
  renderCards($("#config-llm"), cfg.llm_providers || [], "name", "status", "model");
  renderSummaryGrid($("#config-agents"), Object.entries(cfg.agent_settings || {}).map(([label, value]) => ({ label, value: Array.isArray(value) ? value.join(", ") : value })));
  renderMarketProviderConfig(cfg);
  renderRqalphaRuntimeConfig(cfg);
  await loadMarketProviderSyncTasks();
  $("#config-output").textContent = JSON.stringify({ ai_workflow: cfg.runtime_settings?.ai_workflow, market_provider: cfg.runtime_settings?.market_provider, rqalpha_runtime: cfg.runtime_settings?.rqalpha_runtime, cache_policy: cfg.cache_policy, report_templates: cfg.report_templates, profiles: profiles.profiles, llm_provider_status: cfg.llm_provider_status, market_provider_status: cfg.market_provider_status, rqalpha_runtime_status: cfg.rqalpha_runtime_status, security_notes: cfg.security_notes }, null, 2);
  const draftEditor = $("#config-draft-editor");
  if (draftEditor && !draftEditor.matches(":focus")) draftEditor.value = JSON.stringify(cfg.runtime_settings || {}, null, 2);
  return { status, profiles };
}
function renderMarketProviderConfig(cfg) {
  const provider = cfg.runtime_settings?.market_provider || {};
  const status = cfg.market_provider_status || {};
  const spec = provider.endpoint_spec || status.endpoint_spec || {};
  const pagination = spec.pagination || {};
  const retry = spec.retry || {};
  renderSummaryGrid($("#config-market-provider-status"), [
    { label: "Provider", value: status.provider || provider.provider_name || "open-http-market-provider" },
    { label: "状态", value: status.status || "unknown" },
    { label: "Base URL", value: status.base_url_configured ? "已配置" : "未配置" },
    { label: "API Key", value: status.api_key_configured ? "已配置（环境变量）" : "未配置（环境变量）" },
    { label: "启用意图", value: status.enabled_intent ? "启用" : "关闭" },
    { label: "Timeout", value: `${status.timeout_seconds ?? provider.timeout_seconds ?? 8}s` },
    { label: "价格 Path", value: spec.price_history_path || "/price-history" },
    { label: "Rows 路径", value: spec.price_history_rows_path || "rows" },
    { label: "分页策略", value: pagination.enabled ? `${pagination.page_size || 200} x ${pagination.max_pages || 1}` : "关闭" },
    { label: "重试", value: `${retry.max_attempts || 1} 次` },
  ]);
  const form = $("#config-market-provider-form");
  if (form && !form.matches(":focus-within")) {
    form.elements.enabled.value = String(Boolean(provider.enabled));
    form.elements.provider_name.value = provider.provider_name || "open-http-market-provider";
    form.elements.base_url.value = provider.base_url || "";
    form.elements.timeout_seconds.value = provider.timeout_seconds ?? 8;
    form.elements.price_history_path.value = spec.price_history_path || "/price-history";
    form.elements.price_history_rows_path.value = spec.price_history_rows_path || "rows";
    form.elements.trading_calendar_path.value = spec.trading_calendar_path || "/trading-calendar";
    form.elements.trading_calendar_days_path.value = spec.trading_calendar_days_path || "days";
    form.elements.pagination_enabled.value = String(Boolean(pagination.enabled));
    form.elements.page_size.value = pagination.page_size ?? 200;
    form.elements.max_pages.value = pagination.max_pages ?? 1;
    form.elements.retry_max_attempts.value = retry.max_attempts ?? 1;
    form.elements.field_mapping.value = JSON.stringify(spec.field_mapping || defaultMarketFieldMapping(), null, 2);
  }
}
function defaultMarketFieldMapping() { return { date: ["date", "trade_date"], open: ["open", "open_price"], high: ["high", "high_price"], low: ["low", "low_price"], close: ["close", "close_price"], volume: ["volume", "vol"] }; }
function readFieldMapping(value) { try { const parsed = JSON.parse(value || "{}"); return parsed && typeof parsed === "object" ? parsed : defaultMarketFieldMapping(); } catch (_) { return defaultMarketFieldMapping(); } }
function renderRqalphaRuntimeConfig(cfg) {
  const runtime = cfg.runtime_settings?.rqalpha_runtime || {};
  const status = cfg.rqalpha_runtime_status || {};
  renderSummaryGrid($("#config-rqalpha-status"), [
    { label: "包状态", value: status.status || "unknown" },
    { label: "可用", value: status.available ? "是" : "否" },
    { label: "版本", value: status.version || "未检测到" },
    { label: "执行模式", value: runtime.execution_mode || "probe_then_local_fallback" },
    { label: "本地优先", value: runtime.prefer_real_package ? "否，偏真实包" : "是，先本地" },
    { label: "Fallback", value: "local_sqlite_backtest_runtime" },
  ]);
  const local = runtime.local_capabilities || [];
  const pending = runtime.pending_real_capabilities || [];
  $("#config-rqalpha-capabilities").innerHTML = [
    `<article class="definition-item"><h4>可先本地完成</h4><p>${local.join(" / ") || "package_probe / local_sqlite_backtest"}</p><span>不需要真实 rqalpha 包即可验证</span></article>`,
    `<article class="definition-item"><h4>待真实 rqalpha 环境</h4><p>${pending.join(" / ") || "rqalpha_data_bundle / strategy_file_execution"}</p><span>需要安装包、数据 bundle 或真实 provider</span></article>`,
  ].join("");
}
function readDraftSettings() { try { return JSON.parse($("#config-draft-editor").value || "{}"); } catch (_) { return null; } }
function writeDraftSettings(settings) { $("#config-draft-editor").value = JSON.stringify(settings, null, 2); }
function applyMarketProviderFormToDraft() {
  const form = $("#config-market-provider-form");
  const settings = readDraftSettings();
  if (!settings) { setFeedback("配置草稿必须是有效 JSON", "error"); return; }
  settings.market_provider = {
    enabled: form.elements.enabled.value === "true",
    provider_name: form.elements.provider_name.value.trim() || "open-http-market-provider",
    base_url: form.elements.base_url.value.trim(),
    timeout_seconds: Number(form.elements.timeout_seconds.value || 8),
    api_key_policy: "env_only_SCQ_MARKET_PROVIDER_API_KEY",
    endpoint_spec: {
      price_history_path: form.elements.price_history_path.value.trim() || "/price-history",
      price_history_rows_path: form.elements.price_history_rows_path.value.trim() || "rows",
      trading_calendar_path: form.elements.trading_calendar_path.value.trim() || "/trading-calendar",
      trading_calendar_days_path: form.elements.trading_calendar_days_path.value.trim() || "days",
      field_mapping: readFieldMapping(form.elements.field_mapping.value),
      pagination: { enabled: form.elements.pagination_enabled.value === "true", page_param: "page", page_size_param: "page_size", page_size: Number(form.elements.page_size.value || 200), next_cursor_path: "next_cursor", next_cursor_param: "cursor", max_pages: Number(form.elements.max_pages.value || 1) },
      retry: { max_attempts: Number(form.elements.retry_max_attempts.value || 1) },
    },
  };
  settings.rqalpha_runtime = settings.rqalpha_runtime || { execution_mode: "probe_then_local_fallback", prefer_real_package: false };
  writeDraftSettings(settings);
  setFeedback("外部行情 Provider endpoint、字段映射与分页策略已写入草稿，保存后生效", "success");
}
async function preflightMarketProvider() {
  applyMarketProviderFormToDraft();
  await saveConfigDraft();
  const form = $("#market-query-form");
  const marketValues = form ? Object.fromEntries(new FormData(form).entries()) : {};
  const payload = await requestJson("/api/config/market-provider/preflight", { method: "POST", body: JSON.stringify({ symbol: marketValues.symbol || "000001.XSHE", start_date: marketValues.start_date || "2020-01-01", end_date: marketValues.end_date || marketValues.start_date || "2020-01-01" }) });
  const target = $("#config-market-provider-preflight-output");
  if (target) target.textContent = JSON.stringify(payload.result || {}, null, 2);
  setFeedback(`Provider 预检完成：${payload.result?.status || "unknown"}`, payload.result?.status === "passed" ? "success" : "error");
  await loadConfig();
  return payload.result;
}
function renderMarketProviderSyncTasks(tasks = []) {
  const target = $("#config-sync-task-list");
  if (!target) return;
  target.innerHTML = tasks.map((task) => `<article class="definition-item"><h4>${task.task_id} / ${task.status}</h4><p>${(task.symbols || []).join(", ")}；窗口 ${task.date_window?.start_date || "-"} 至 ${task.date_window?.end_date || "-"}；行数 ${task.row_count || 0}；游标 ${JSON.stringify(task.cursor_by_symbol || {})}</p><span>运行 ${task.run_count || 0} 次 / 重试 ${task.retry_count || 0} 次 / 最近 ${task.last_run_at || "未运行"}</span><div class="button-row"><button type="button" data-sync-run="${task.task_id}">运行</button><button type="button" data-sync-retry="${task.task_id}">重试</button></div></article>`).join("") || '<div class="empty-cell">暂无同步任务</div>';
  target.querySelectorAll("[data-sync-run]").forEach((button) => button.addEventListener("click", () => runMarketProviderSyncTask(button.dataset.syncRun)));
  target.querySelectorAll("[data-sync-retry]").forEach((button) => button.addEventListener("click", () => retryMarketProviderSyncTask(button.dataset.syncRetry)));
}
async function loadMarketProviderSyncTasks() {
  const payload = await requestJson("/api/config/market-provider/sync-tasks");
  renderMarketProviderSyncTasks(payload.tasks || []);
  return payload.tasks || [];
}
function readSyncTaskFormValues(form) {
  const values = Object.fromEntries(new FormData(form).entries());
  return {
    symbols: String(values.symbols || "000001.XSHE").split(",").map((item) => item.trim()).filter(Boolean),
    start_date: values.start_date || "2020-06-01",
    end_date: values.end_date || values.start_date || "2020-06-01",
    interval_seconds: values.interval_seconds ? Number(values.interval_seconds) : null,
  };
}
async function createMarketProviderSyncTask(event) {
  event.preventDefault();
  const taskPayload = readSyncTaskFormValues(event.currentTarget);
  const payload = await requestJson("/api/config/market-provider/sync-tasks", { method: "POST", body: JSON.stringify(taskPayload) });
  $("#config-sync-task-output").textContent = JSON.stringify(payload.task || {}, null, 2);
  await loadMarketProviderSyncTasks();
  setFeedback(`同步任务已创建：${payload.task?.task_id || "unknown"}`, "success");
}
async function runMarketProviderSyncTask(taskId) {
  const payload = await requestJson(`/api/config/market-provider/sync-tasks/${encodeURIComponent(taskId)}/run`, { method: "POST", body: JSON.stringify({}) });
  $("#config-sync-task-output").textContent = JSON.stringify(payload.task || {}, null, 2);
  await loadMarketProviderSyncTasks();
  setFeedback(`同步任务运行完成：${payload.task?.status || "unknown"}`, payload.task?.status === "completed" ? "success" : "error");
}
async function retryMarketProviderSyncTask(taskId) {
  const payload = await requestJson(`/api/config/market-provider/sync-tasks/${encodeURIComponent(taskId)}/retry`, { method: "POST", body: JSON.stringify({}) });
  $("#config-sync-task-output").textContent = JSON.stringify(payload.task || {}, null, 2);
  await loadMarketProviderSyncTasks();
  setFeedback(`同步任务重试完成：${payload.task?.status || "unknown"}`, payload.task?.status === "completed" ? "success" : "error");
}
async function saveConfigDraft() { let settings; try { settings = JSON.parse($("#config-draft-editor").value || "{}"); } catch (error) { setFeedback("配置草稿必须是有效 JSON", "error"); return; } const payload = await requestJson("/api/config/runtime-draft", { method: "POST", body: JSON.stringify({ settings }) }); await loadConfig(); setFeedback(`配置草稿已保存：${payload.draft.saved_at || "local"}`, "success"); }
async function loadDashboard() {
  const strategies = await loadStrategies();
  const [market, factors, reports, ai, config] = await Promise.all([
    loadMarket(),
    loadFactors(),
    loadReports(),
    runAI(),
    loadConfig(),
  ]);
  renderSummaryGrid($("#dashboard-metrics"), [
    { label: "行情记录", value: market.rows.length },
    { label: "交易日", value: market.calendar.days.length },
    { label: "因子定义", value: factors.definitions.definitions.length },
    { label: "策略库", value: strategies.length },
    { label: "回测状态", value: reports.detail.detail.status || "completed" },
    { label: "AI 报告", value: ai.status || "generated" },
    { label: "配置源", value: config.status.status.data_sources.length },
    { label: "仓库映射", value: sourceMatrix.length },
  ]);
  renderSummaryGrid($("#dashboard-backtest"), [
    { label: "Run", value: reports.detail.detail.run_id || "phase1-demo-run-001" },
    { label: "Strategy", value: reports.detail.detail.strategy_name || "moving_average_strategy" },
    { label: "Metrics", value: Object.keys(reports.detail.detail.metrics || {}).join(", ") },
  ]);
}
function bindEvents() { bindBacktestWorkspace(); bindStrategyManager(); document.querySelectorAll(".nav-tab").forEach((button) => button.addEventListener("click", () => { activatePage(button.dataset.page); if (button.dataset.page === "market" && !aShareWorkspaceLoaded) { loadAShareWorkspace().then(() => setFeedback("A 股真实数据库已加载", "success")).catch((error) => setFeedback(error.message, "error")); } })); document.querySelectorAll("[data-jump]").forEach((button) => button.addEventListener("click", () => activatePage(button.dataset.jump))); $("#market-query-form").addEventListener("submit", async (event) => { event.preventDefault(); await loadMarket(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("数据中心已刷新", "success"); }); const aShareSymbolForm = $("#a-share-symbol-form"); if (aShareSymbolForm) aShareSymbolForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadAShareSymbols(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("A 股股票目录已刷新", "success"); }); const aShareDailyForm = $("#a-share-daily-form"); if (aShareDailyForm) aShareDailyForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadAShareDaily(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("A 股真实日线已刷新", "success"); }); const aShareSymbolBody = $("#a-share-symbol-body"); if (aShareSymbolBody) aShareSymbolBody.addEventListener("click", async (event) => { const button = event.target.closest("[data-a-share-symbol]"); if (!button) return; aShareDailyForm.elements.symbol.value = button.dataset.aShareSymbol; await loadAShareDaily(Object.fromEntries(new FormData(aShareDailyForm).entries())); setFeedback("已加载 " + button.dataset.aShareSymbol + " 真实日线", "success"); }); const repairGapsButton = $("#market-repair-gaps"); if (repairGapsButton) repairGapsButton.addEventListener("click", repairMarketGaps); const assetDirectoryForm = $("#backtest-asset-directory-form"); if (assetDirectoryForm) assetDirectoryForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadBacktestAssetDirectory(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("回测资产目录已刷新", "success"); }); const migrationDryRun = $("#backtest-asset-migration-dry-run"); if (migrationDryRun) migrationDryRun.addEventListener("click", async () => { await migrateBacktestInputSnapshots(true); setFeedback("历史输入快照迁移预检完成", "success"); }); const migrationRun = $("#backtest-asset-migration-run"); if (migrationRun) migrationRun.addEventListener("click", async () => { await migrateBacktestInputSnapshots(false); setFeedback("历史输入快照迁移完成", "success"); }); $("#factor-query-form").addEventListener("submit", async (event) => { event.preventDefault(); await loadFactors(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("因子分析已刷新", "success"); }); $("#backtest-run-form").addEventListener("submit", async (event) => { event.preventDefault(); try { await runBacktest(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("单股回测已完成，已进入结果分析", "success"); } catch (error) { setFeedback(error.message, "error"); } }); const resultsRefresh = $("#backtest-results-refresh"); if (resultsRefresh) resultsRefresh.addEventListener("click", () => refreshBacktestResults().then(() => setFeedback("回测结果已刷新", "success")).catch((error) => setFeedback(error.message, "error"))); const resultsReport = $("#backtest-results-report"); if (resultsReport) resultsReport.addEventListener("click", () => openSelectedBacktestReport().catch((error) => setFeedback(error.message, "error"))); const modeTaskForm = $("#mode-task-directory-form"); if (modeTaskForm) modeTaskForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadBacktestModeTasks(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("双模式回测任务已筛选", "success"); }); const modeTaskRefresh = $("#mode-task-directory-refresh"); if (modeTaskRefresh) modeTaskRefresh.addEventListener("click", () => loadBacktestModeTasks().then(() => setFeedback("双模式回测任务已刷新", "success")).catch((error) => setFeedback(error.message, "error"))); const screeningForm = $("#screening-task-form"); if (screeningForm) screeningForm.addEventListener("submit", (event) => createIndependentScreeningTask(event).catch(() => {})); const screeningRun = $("#screening-task-run"); if (screeningRun) screeningRun.addEventListener("click", () => runIndependentScreeningTask().catch((error) => setFeedback(error.message, "error"))); const screeningPause = $("#screening-task-pause"); if (screeningPause) screeningPause.addEventListener("click", () => controlIndependentScreeningTask("pause").catch((error) => setFeedback(error.message, "error"))); const screeningCancel = $("#screening-task-cancel"); if (screeningCancel) screeningCancel.addEventListener("click", () => controlIndependentScreeningTask("cancel").catch((error) => setFeedback(error.message, "error"))); const screeningRefresh = $("#screening-task-refresh"); if (screeningRefresh) screeningRefresh.addEventListener("click", () => loadIndependentScreeningTasks().then(() => setFeedback("独立选股任务已刷新", "success")).catch((error) => setFeedback(error.message, "error")));  const portfolioForm = $("#portfolio-task-form"); if (portfolioForm) portfolioForm.addEventListener("submit", (event) => createSharedPortfolioTask(event).catch(() => {})); const portfolioRun = $("#portfolio-task-run"); if (portfolioRun) portfolioRun.addEventListener("click", () => runSharedPortfolioTask().catch((error) => setFeedback(error.message, "error"))); const portfolioRefresh = $("#portfolio-task-refresh"); if (portfolioRefresh) portfolioRefresh.addEventListener("click", () => loadSharedPortfolioTasks().then(() => setFeedback("共享资金池组合任务已刷新", "success")).catch((error) => setFeedback(error.message, "error"))); const researchCreate = $("#strategy-research-create"); if (researchCreate) researchCreate.addEventListener("click", createStrategyResearchTask); const experimentCreate = $("#backtest-experiment-index-create"); if (experimentCreate) experimentCreate.addEventListener("click", createCurrentExperimentIndex); const experimentRefresh = $("#backtest-experiment-index-refresh"); if (experimentRefresh) experimentRefresh.addEventListener("click", loadExperimentIndex); const experimentCompare = $("#backtest-experiment-compare"); if (experimentCompare && typeof compareSelectedExperiments === "function") experimentCompare.addEventListener("click", compareSelectedExperiments); $("#strategy-parameter-scan").addEventListener("click", runParameterScan); const matrixCreate = $("#strategy-matrix-create"); if (matrixCreate) matrixCreate.addEventListener("click", createParameterMatrixTask); const matrixRun = $("#strategy-matrix-run"); if (matrixRun) matrixRun.addEventListener("click", runCurrentParameterMatrixTask); $("#strategy-scan-save-snapshot").addEventListener("click", saveCurrentScanComparisonSnapshot); $("#backtest-jump-reporting").addEventListener("click", async (event) => { const runId = event.currentTarget.dataset.runId; activatePage("reporting"); $('#reporting-query-form input[name="run_id"]').value = runId; try { await loadReports(runId, "phase1-batch-001"); } catch (_) { setFeedback("已跳转报告中心，请刷新 seeded run 或检查 run_id", "error"); } }); $("#ai-analysis-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); await runAI(form.get("symbol"), form.get("analysis_date")); setFeedback("AI 摘要已生成", "success"); }); const modeReportForm = $("#mode-report-form"); if (modeReportForm) modeReportForm.addEventListener("submit", (event) => loadBacktestModeReport(event).catch((error) => setFeedback(error.message, "error"))); $("#reporting-query-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); await loadReports(form.get("run_id"), form.get("experiment_id")); setFeedback("报告中心已刷新", "success"); }); $("#config-refresh").addEventListener("click", async () => { await loadConfig(); setFeedback("配置状态已刷新", "success"); }); $("#config-save-draft").addEventListener("click", saveConfigDraft); const preflightButton = $("#config-market-provider-preflight"); if (preflightButton) preflightButton.addEventListener("click", preflightMarketProvider); const syncTaskForm = $("#config-sync-task-form"); if (syncTaskForm) syncTaskForm.addEventListener("submit", createMarketProviderSyncTask); const marketApply = $("#config-market-provider-apply"); if (marketApply) marketApply.addEventListener("click", applyMarketProviderFormToDraft); $("#report-save-snapshot").addEventListener("click", saveCurrentReportSnapshot); $("#report-package-create").addEventListener("click", createCurrentReportPackage); const comparisonPackageCreate = $("#report-comparison-package-create"); if (comparisonPackageCreate) comparisonPackageCreate.addEventListener("click", createExperimentComparisonPackage); const packageDirectoryRefresh = $("#report-package-directory-refresh"); if (packageDirectoryRefresh) packageDirectoryRefresh.addEventListener("click", async () => { await loadReportPackageDirectory(); setFeedback("报告包归档目录已刷新", "success"); }); const exportManifestCreate = $("#report-package-export-manifest-create"); if (exportManifestCreate) exportManifestCreate.addEventListener("click", createReportPackageExportManifest); const lifecycleActive = $("#report-package-lifecycle-active"); if (lifecycleActive) lifecycleActive.addEventListener("click", () => updateSelectedReportPackageLifecycle("active", { protected: false, reason: "恢复为活跃报告包" })); const lifecycleArchive = $("#report-package-lifecycle-archive"); if (lifecycleArchive) lifecycleArchive.addEventListener("click", () => updateSelectedReportPackageLifecycle("archived", { protected: false, reason: "阶段56 归档保留" })); const lifecycleProtect = $("#report-package-lifecycle-protect"); if (lifecycleProtect) lifecycleProtect.addEventListener("click", () => updateSelectedReportPackageLifecycle("protected", { protected: true, retention_policy: "retain-protected", reason: "阶段56 保护保留" })); $("#report-package-export-html").addEventListener("click", () => exportSelectedReportPackage("html")); $("#report-package-export-json").addEventListener("click", () => exportSelectedReportPackage("json")); $("#report-package-export-pdf").addEventListener("click", () => exportSelectedReportPackage("pdf")); $("#report-package-export-word").addEventListener("click", () => exportSelectedReportPackage("word")); }
function bindBacktestResultControls() {
  const prev = $("#backtest-table-prev");
  const next = $("#backtest-table-next");
  const exportJson = $("#backtest-table-export-json");
  const exportCsv = $("#backtest-table-export-csv");
  if (prev) prev.addEventListener("click", () => loadBacktestResultTable(Math.max(0, currentBacktestTableOffset - currentBacktestTableLimit)));
  if (next) next.addEventListener("click", () => loadBacktestResultTable(currentBacktestTableOffset + currentBacktestTableLimit));
  if (exportJson) exportJson.addEventListener("click", () => exportBacktestResultTable("json"));
  if (exportCsv) exportCsv.addEventListener("click", () => exportBacktestResultTable("csv"));
}
async function main() { bindEvents(); bindBacktestResultControls(); renderTraceability(); renderAcceptanceMatrix(); const requestedPage = new URLSearchParams(window.location.search).get("page"); if (requestedPage && pageTitles[requestedPage]) activatePage(requestedPage); try { await loadDashboard(); await loadBacktestModeTasks(); setFeedback("MVP 数据加载完成", "success"); } catch (error) { setFeedback(error.message, "error"); } }
main();




























































