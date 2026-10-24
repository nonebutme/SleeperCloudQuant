const pageTitles = {
  dashboard: "工作台",
  market: "数据中心",
  factor: "因子分析",
  "strategy-datasets": "策略数据集与指标",
  backtest: "策略回测",
  ai: "AI 研究",
  reporting: "回测分析与复盘",
  "report-management": "报告资产",
  config: "系统设置",
  traceability: "系统信息与工程审计",
};
const pageNavigationGroups = {
  "strategy-datasets": "datasets",
  ai: "reporting",
  reporting: "backtest",
  "report-management": "reporting",
  traceability: "config",
};
let currentConfigAnchor = "config-ai-agent";
let currentNavigationGroup = "dashboard";
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
let currentSingleTask = null;
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
let currentReportWorkflowId = "";
let currentBacktestResultRunId = "";
let currentBacktestRunIdPrefix = "";
let currentBacktestTableOffset = 0;
let currentIndustrySortMode = "default";
let currentIndependentModeReport = null;
let currentModeReportTaskId = "";
let currentModeReportRunIndex = [];
let currentModeReportSelectedIndex = 0;
let currentModeReportTab = "task_statistics";
let aShareWorkspaceLoaded = false;let stage75ComparisonRuns = [];
let stage75RunCatalog = [];
let stage75ResultDockOpen = false;
const stage75ComparisonColors = ["#285f8f", "#bd4b55", "#2f7d65", "#8a63a8"];
const currentBacktestTableLimit = 5;
const $ = (selector) => document.querySelector(selector);
const globalFeedback = $("#global-feedback");

function setFeedback(message, kind = "") { globalFeedback.textContent = message; globalFeedback.className = kind ? `feedback is-${kind}` : "feedback"; }
function buildQuery(params) { const search = new URLSearchParams(); Object.entries(params).forEach(([key, value]) => { if (value !== "" && value != null) search.set(key, value); }); return search.toString(); }
function friendlyApiError(message) {
  const detail = String(message || "");
  if (detail.includes("published_version_does_not_cover_requested_window")) {
    return "回测日期超出当前已发布数据范围。请使用页面给出的最大可用日期，或先在数据中心补齐并发布数据。";
  }
  return detail;
}
async function requestJson(path, options = {}) { const response = await fetch(path, { method: options.method || "GET", headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) }, body: options.body }); const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(friendlyApiError(payload.detail || `请求失败 (${response.status})`)); return payload; }
function navigationGroupFor(pageId) {
  return pageNavigationGroups[pageId] || pageId;
}
function syncNavigationState(pageId, preferredGroup = "") {
  const group = preferredGroup || navigationGroupFor(pageId);
  currentNavigationGroup = group;
  document.querySelectorAll(".nav-tab").forEach((button) => {
    const active = (button.dataset.navGroup || button.dataset.page) === group;
    button.classList.toggle("is-active", active);
    if (button.hasAttribute("aria-expanded")) button.setAttribute("aria-expanded", active ? "true" : "false");
  });
  document.querySelectorAll("[data-nav-submenu]").forEach((submenu) => {
    submenu.hidden = submenu.dataset.navSubmenu !== group;
  });
  document.querySelectorAll("[data-route-page]").forEach((button) => {
    const samePage = button.dataset.routePage === pageId;
    const sameAnchor = !button.dataset.configAnchor || button.dataset.configAnchor === currentConfigAnchor;
    button.classList.toggle("is-active", samePage && sameAnchor);
  });
}
function activatePage(pageId, replace = true, syncUrl = true, preferredGroup = "") {
  document.querySelectorAll(".page-section").forEach((section) => {
    section.classList.toggle("is-active", section.id === "page-" + pageId);
  });
  const focusedNavigation = document.activeElement?.matches?.(".nav-tab") && document.activeElement.dataset.page === pageId
    ? document.activeElement.dataset.navGroup
    : "";
  syncNavigationState(pageId, preferredGroup || focusedNavigation);
  $("#page-title").textContent = currentNavigationGroup === "market-data" ? "市场数据" : (pageTitles[pageId] || "SleeperCloudQuant");
  if (pageId === "factor") window.syncFactorPageTitle?.();
  if (syncUrl) updateStage75Url({ page: pageId }, replace);
}
function focusConfigAnchor(anchorId) {
  const target = document.getElementById(anchorId);
  if (!target) return;
  requestAnimationFrame(() => target.scrollIntoView({ block: "start", behavior: "smooth" }));
}
function configureUnifiedNavigation() {
  const dataSourceSummary = $("#config-data-sources-panel");
  if (dataSourceSummary) dataSourceSummary.hidden = true;
  document.querySelectorAll("[data-route-page]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.configAnchor) currentConfigAnchor = button.dataset.configAnchor;
      const navigationGroup = button.dataset.navContext || button.closest("[data-nav-submenu]")?.dataset.navSubmenu || "";
      activatePage(button.dataset.routePage, false, true, navigationGroup);
      if (button.dataset.configAnchor) focusConfigAnchor(button.dataset.configAnchor);
    });
  });
  document.querySelectorAll("[data-market-category]").forEach((button) => {
    button.addEventListener("click", () => {
      const category = button.dataset.marketCategory;
      activatePage("market", false, true, "market-data");
      document.querySelectorAll("[data-market-category]").forEach((item) => item.classList.toggle("is-active", item === button));
      const url = new URL(window.location.href);
      url.searchParams.set("page", "market");
      url.searchParams.set("dc_view", "assets");
      url.searchParams.set("market_tab", category);
      window.history.replaceState({}, "", url);
      window.openMarketDataCategory?.(category);
      window.requestAnimationFrame(() => {
        activatePage("market", false, true, "market-data");
        document.querySelectorAll("[data-market-category]").forEach((item) => item.classList.toggle("is-active", item === button));
        window.openMarketDataCategory?.(category);
      });
    });
  });
  document.querySelector('.nav-tab[data-nav-group="market-data"]')?.addEventListener("click", () => {
    const target = document.querySelector("[data-market-category].is-active") || document.querySelector("[data-market-category]");
    target?.click();
  });
  window.addEventListener("popstate", () => {
    const params = new URLSearchParams(window.location.search);
    const pageId = params.get("page") || "dashboard";
    const navigationGroup = pageId === "market" && params.get("dc_view") === "assets" ? "market-data" : "";
    if (pageTitles[pageId]) activatePage(pageId, true, false, navigationGroup);
    const factorView = params.get("factor_view");
    if (pageId === "factor" && factorView && typeof window.activateFactorView === "function") {
      window.activateFactorView(factorView, false);
    }
  });
  const initialParams = new URLSearchParams(window.location.search);
  const initialPage = initialParams.get("page") || "dashboard";
  const initialGroup = initialPage === "market" && initialParams.get("dc_view") === "assets" ? "market-data" : "";
  syncNavigationState(initialPage, initialGroup);
}
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
  if (!rows.length) { target.innerHTML = '<div class="empty-cell">No candlestick data</div>'; return; }
  const width = 960, height = 380, padX = 42, priceTop = 22, priceBottom = 264, volumeTop = 292, volumeBottom = 352;
  const numericRows = rows.map((row) => ({ ...row, open: Number(row.open), high: Number(row.high), low: Number(row.low), close: Number(row.close), volume: Number(row.volume || 0) }));
  const highs = numericRows.map((row) => row.high); const lows = numericRows.map((row) => row.low);
  const max = Math.max(...highs); const min = Math.min(...lows); const span = max - min || 1;
  const maxVolume = Math.max(...numericRows.map((row) => row.volume), 1);
  const y = (value) => priceTop + (max - Number(value)) / span * (priceBottom - priceTop);
  const step = (width - padX * 2) / numericRows.length;
  const xAt = (index) => padX + index * step + step / 2;
  const labelStride = Math.max(1, Math.ceil(numericRows.length / 8));
  const candles = numericRows.map((row, index) => {
    const x = xAt(index); const openY = y(row.open); const closeY = y(row.close); const highY = y(row.high); const lowY = y(row.low);
    const up = row.close >= row.open; const color = up ? "#c43d3d" : "#16845b"; const bodyY = Math.min(openY, closeY); const bodyH = Math.max(2, Math.abs(openY - closeY));
    const barHeight = Math.max(1, row.volume / maxVolume * (volumeBottom - volumeTop));
    const dateLabel = index % labelStride === 0 ? `<text x="${x}" y="${height - 8}" text-anchor="middle" class="kline-label">${String(row.date).slice(5)}</text>` : '';
    return `<g class="kline-candle" data-kline-date="${row.date}" tabindex="0" role="button" aria-label="${row.date} OHLC ${row.open} ${row.high} ${row.low} ${row.close}"><line x1="${x}" x2="${x}" y1="${highY}" y2="${lowY}" stroke="${color}" stroke-width="1.4"/><rect x="${x - Math.min(6, step * 0.3)}" y="${bodyY}" width="${Math.max(1.5, Math.min(12, step * 0.6))}" height="${bodyH}" fill="${color}"/><rect x="${x - Math.min(6, step * 0.3)}" y="${volumeBottom - barHeight}" width="${Math.max(1.5, Math.min(12, step * 0.6))}" height="${barHeight}" fill="${color}" opacity="0.45"/>${dateLabel}</g>`;
  }).join('');
  const maColors = { 5: '#f7ba1e', 10: '#722ed1', 20: '#0fc6c2', 60: '#165dff' };
  const averages = Object.entries(maColors).map(([periodText, color]) => {
    const period = Number(periodText); const points = [];
    numericRows.forEach((row, index) => {
      if (index + 1 < period) return;
      const values = numericRows.slice(index - period + 1, index + 1).map((item) => item.close);
      const average = values.reduce((sum, value) => sum + value, 0) / period;
      points.push(`${xAt(index)},${y(average)}`);
    });
    return points.length > 1 ? `<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="1.5" opacity="0.9"/>` : '';
  }).join('');
  target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Candlestick chart with moving averages and volume"><line x1="${padX}" x2="${width - padX}" y1="${priceTop}" y2="${priceTop}" class="grid-line"/><line x1="${padX}" x2="${width - padX}" y1="${priceBottom}" y2="${priceBottom}" class="grid-line"/><line x1="${padX}" x2="${width - padX}" y1="${volumeBottom}" y2="${volumeBottom}" class="grid-line"/><text x="4" y="${priceTop + 4}" class="axis-label">${max.toFixed(2)}</text><text x="4" y="${priceBottom}" class="axis-label">${min.toFixed(2)}</text><text x="4" y="${volumeTop + 8}" class="axis-label">VOL</text>${candles}${averages}</svg>`;
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
  const quality = daily.quality || {};
  renderSummaryGrid($("#a-share-daily-summary"), [
    { label: "股票", value: (daily.symbol || "-") + " / " + (daily.market || "-") },
    { label: "复权口径", value: daily.adjustment || "-" },
    { label: "区间总行数", value: formatMarketNumber(daily.total) },
    { label: "本页", value: formatMarketNumber(rows.length) },
    { label: "去除重复", value: formatMarketNumber(daily.duplicate_rows_removed) },
    { label: "完整性", value: quality.missing_count == null ? "未检查" : (quality.missing_count === 0 ? "完整" : `缺失 ${quality.missing_count} 日`) },
    { label: "正确性", value: quality.invalid_count == null ? "未检查" : (quality.invalid_count === 0 ? "通过" : `异常 ${quality.invalid_count} 行`) },
    { label: "缺失范围", value: quality.missing_count ? `${quality.first_missing_date} → ${quality.last_missing_date}` : "-" },
    { label: "来源", value: daily.provider || daily.source || "-" },
  ]);
  renderCandlestick($("#a-share-daily-chart"), [...rows].reverse());
  $("#a-share-daily-body").innerHTML = rows.map((row) => { const tone = financialToneClass(row.change_pct); return "<tr><td>" + row.date + "</td><td>" + row.open + "</td><td>" + row.high + "</td><td>" + row.low + "</td><td>" + row.close + "</td><td>" + formatMarketNumber(row.volume) + "</td><td>" + formatMarketNumber(row.amount) + "</td><td class='" + tone + "'>" + (row.change_pct ?? "-") + "</td><td>" + (row.turnover_rate ?? "-") + "</td></tr>"; }).join("") || '<tr><td colspan="9" class="empty-cell">该区间没有行情</td></tr>';
  $("#a-share-daily-output").textContent = JSON.stringify({ status: daily.status, read_only: daily.read_only, symbol: daily.symbol, adjustment: daily.adjustment, total: daily.total, quality, duplicate_rows_removed: daily.duplicate_rows_removed, limit: daily.limit, offset: daily.offset }, null, 2);
  window.dispatchEvent(new CustomEvent("scq:market-bars-loaded", { detail: { kind: "stock", rows: [...rows].reverse(), payload: daily } }));
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
  if (!$("#price-history-body")) return { rows, calendar, status: syncStatus.status || {} };
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
async function loadLegacyFactors(params = { index_code: "000300.XSHG", trade_date: "2020-01-02", factor_id: "close_to_ma2_bias" }) {
  const [definitions, pool, ranking, summary] = await Promise.all([requestJson("/api/factors/definitions"), requestJson(`/api/factors/pool-members?${buildQuery({ index_code: params.index_code, date: params.trade_date })}`), requestJson(`/api/factors/top-n?${buildQuery({ factor_id: params.factor_id, trade_date: params.trade_date, start_date: "2020-01-01", end_date: params.trade_date, limit: 5, descending: true })}`), requestJson(`/api/factors/cross-section-summary?${buildQuery({ index_code: params.index_code, date: params.trade_date, trade_date: params.trade_date, start_date: "2020-01-01", end_date: params.trade_date })}`)]);
  renderCards($("#factor-definitions-list"), definitions.definitions || [], "factor_id", "name", "version"); renderList($("#factor-pool-list"), pool.symbols || []);
  const rankingRows = ranking.ranking?.rows || []; renderBarChart($("#factor-ranking-chart"), rankingRows, "symbol", "value"); $("#factor-summary-output").textContent = JSON.stringify({ ranking: ranking.ranking, cross_section: summary.summaries }, null, 2);
  return { definitions, pool, ranking, summary };
}

function renderExperimentIndex(experiments = []) {
  const target = $("#backtest-experiment-index-list");
  if (!target) return;
  target.innerHTML = experiments.map((item) => `<article class="definition-item"><h4>${item.name || item.experiment_id}</h4><p>${item.run_id_prefix || "-"}\uff1b${(item.tags || []).join(", ")}</p><span>${item.status || "unknown"} / ${item.primary_run_id || "\u65e0\u4e3b run"}</span><button type="button" data-experiment-review="${item.experiment_id || item.run_id_prefix}">\u751f\u6210\u5b9e\u9a8c\u590d\u76d8\u62a5\u544a</button></article>`).join("") || '<div class="empty-cell">\u6682\u65e0\u5b9e\u9a8c\u7d22\u5f15</div>';
  target.querySelectorAll(".definition-item").forEach((card, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "danger-button";
    button.dataset.experimentDelete = experiments[index]?.experiment_id || "";
    button.textContent = "\u5220\u9664";
    card.append(button);
  });
  document.querySelectorAll("[data-experiment-review]").forEach((button) => button.addEventListener("click", () => createExperimentReviewPackage(button.dataset.experimentReview)));
  document.querySelectorAll("[data-experiment-delete]").forEach((button) => button.addEventListener("click", () => deleteExperimentIndex(button.dataset.experimentDelete).catch((error) => setFeedback(error.message, "error"))));
}
async function deleteExperimentIndex(experimentId) {
  if (!experimentId || !window.confirm(`\u786e\u8ba4\u5220\u9664\u5b9e\u9a8c\u7d22\u5f15 ${experimentId}\uff1f\u5220\u9664\u540e\u4ecd\u4fdd\u7559\u5ba1\u8ba1\u8bb0\u5f55\u3002`)) return;
  await requestJson(`/api/backtest/experiments/index/${encodeURIComponent(experimentId)}`, { method: "DELETE" });
  await loadExperimentIndex();
  setFeedback(`\u5b9e\u9a8c\u7d22\u5f15\u5df2\u5220\u9664\uff1a${experimentId}`, "success");
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
  const mode = task.mode_label || (task.mode === "shared-portfolio" ? "投资组合回测" : "独立账户批量回测");
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
  else if (status === "running" && mode === "shared-portfolio") phase = "正在执行投资组合回测";
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
  if (singleRunState.status !== "idle") setStage76ModeTaskState("single",true,{run_id:singleRunState.runId,status:singleRunState.status,symbol:singleRunState.symbol});
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
    '<button type="button" data-mode-task-result="' + index + '"' + (canResult ? "" : " disabled") + '>分析报告</button></div></article>';
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
    '<article class="task-mode-item is-' + singleInfo.tone + '"><div><span class="task-mode-label">单品种测试</span><h4>' + escapeHtml(singleTitle) + '</h4><p>' + escapeHtml(singleDetail) + '</p></div><button type="button" data-overview-view="single">进入测试</button></article>' +
    modeOverviewItem("independent-screening", "独立账户批量回测", "independent") +
    modeOverviewItem("shared-portfolio", "投资组合回测", "portfolio");
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
  const deleteButton = $("#backtest-results-delete");
  if (!target || !reportButton) return;
  const context = selectedResultContext();
  if (!context) {
    target.innerHTML = '<div class="empty-cell">请先完成或选择一个回测任务</div>';
    reportButton.disabled = true;
    if (deleteButton) deleteButton.disabled = true;
    return;
  }
  if (context.kind === "single") {
    const task = context.task;
    target.innerHTML = '<div class="results-context-main"><span class="task-mode-label">单品种测试</span><h4>' + escapeHtml((task.strategyName || "单股策略") + " · " + (task.symbol || "-")) + '</h4><p title="' + escapeHtml(task.runId) + '">回测编号 ' + escapeHtml(shortTechnicalId(task.runId)) + ' · 已完成</p></div><span class="task-status-badge is-success">结果可查看</span>';
    reportButton.disabled = false;
    if (deleteButton) deleteButton.disabled = !["completed", "failed"].includes(task.status);
    return;
  }
  const task = context.task;
  const info = backtestStatusInfo(task.status);
  const binding = task.strategy_binding || {};
  target.innerHTML = '<div class="results-context-main"><span class="task-mode-label">' + escapeHtml(task.mode_label || task.mode) + '</span><h4>' + escapeHtml(taskDisplayTitle(task)) + '</h4><p title="' + escapeHtml(task.task_id) + '">' + escapeHtml(binding.strategy_version || "-") + ' · 任务编号 ' + escapeHtml(shortTechnicalId(task.task_id)) + ' · 耗时 ' + escapeHtml(taskElapsedSeconds(task) > 0 ? formatTaskSeconds(taskElapsedSeconds(task)) : "-") + '</p></div><span class="task-status-badge is-' + info.tone + '">' + escapeHtml(info.label) + '</span>';
  reportButton.disabled = !["completed", "partial_completed", "partial_failed"].includes(task.status);
  if (deleteButton) deleteButton.disabled = !taskCanDelete(task);
}

function activateBacktestView(view) {
  if (view === "results") {
    renderBacktestResultsContext();
    openStage75ResultDock(currentBacktestResultRunId);
    return;
  }
  currentBacktestView = view === "overview" ? "single" : view;
  document.querySelectorAll("[data-backtest-view]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.backtestView === currentBacktestView));
  document.querySelectorAll("[data-backtest-view-target]").forEach((button) => {
    const active = button.dataset.backtestViewTarget === currentBacktestView;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  restoreStage75Draft(currentBacktestView);
  updateStage75Url({ page: "backtest", view: currentBacktestView });
  renderBacktestWorkspace();
}

function renderBacktestWorkspace() {
  const target = $("#backtest-context-summary");
  if (!target) return;
  const strategyName = selectedStrategy?.name || selectedStrategy?.strategy_id || "尚未选择";
  const strategyVersion = selectedStrategy?.latest_version || "-";
  const viewNames = { single: "单品种测试", strategy: "策略库", independent: "独立账户批量回测", portfolio: "投资组合回测", research: "研究实验", results: "结果详情" };
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
    { label: "回测模式", value: mode === "independent" ? "独立资金逐股回测" : "单一共享资金账户" },
    { label: "策略", value: selectedStrategy?.name || selectedStrategy?.strategy_id || "请选择策略" },
    { label: "股票范围", value: scope },
    { label: "回测期间", value: `${values.start_date || "-"} 至 ${values.end_date || "-"}` },
    { label: "复权", value: values.adjustment || "raw" },
  ];
  if (mode === "independent") items.push({ label: "执行资源", value: Number(values.max_workers || 0) ? `${values.max_workers} 并发` : "自动并发" });
  else {
    items.push({ label: "组合约束", value: `最多 ${values.max_positions || 10} 只 / 资金使用 ${Math.round(Number(values.portfolio_exposure || 0.95) * 100)}%` });
    items.push({ label: "调仓语义", value: values.rebalance_policy ? `${values.rebalance_policy === "event_driven" ? "仅成员事件" : "每日等权"} / ${values.capacity_replacement_policy === "incumbent_priority" ? "存量优先" : "强制 Top-N"}` : "按策略源码声明；未声明则兼容旧默认" });
    items.push({ label: "单票上限", value: values.max_single_position_weight ? `${Math.round(Number(values.max_single_position_weight) * 100)}%` : "按策略源码声明；未声明则无上限" });
  }
  renderSummaryGrid(target, items);
}

function setupPortfolioExecutionPolicyFields(form) {
  if (!form || form.elements.rebalance_policy) return;
  const workerLabel = form.elements.max_workers?.closest("label");
  if (!workerLabel) return;
  const rebalanceLabel = document.createElement("label");
  rebalanceLabel.innerHTML = '<span>再平衡方式</span><select name="rebalance_policy"><option value="">按策略声明（推荐）</option><option value="daily_equal_weight">每日恢复等权</option><option value="event_driven">仅成员事件时交易</option></select>';
  const capacityLabel = document.createElement("label");
  capacityLabel.innerHTML = '<span>持仓替换方式</span><select name="capacity_replacement_policy"><option value="">按策略声明（推荐）</option><option value="force_top_n">强制保持当日 Top-N</option><option value="incumbent_priority">存量持仓优先</option></select>';
  const positionCapLabel = document.createElement("label");
  positionCapLabel.innerHTML = '<span>单票最大权重</span><input name="max_single_position_weight" type="number" min="0.01" max="1" step="0.01" placeholder="按策略声明">';
  workerLabel.before(rebalanceLabel, capacityLabel, positionCapLabel);
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
  else if (view === "research") await Promise.all([loadStrategyResearchTasks(), loadExperimentIndex()]);
  else if (view === "results") await refreshBacktestResults();
}

function backtestQueryDateDefaults() {
  const now = new Date();
  const fallbackEnd = new Date(now);
  fallbackEnd.setDate(fallbackEnd.getDate() - 30);
  const formatDate = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  const start = `${now.getFullYear()}-01-01`;
  const end = formatDate(fallbackEnd);
  document.querySelectorAll("input[name=\"start_date\"]").forEach((input) => { input.value = start; });
  document.querySelectorAll("input[name=\"end_date\"]").forEach((input) => { input.value = end; });
  document.querySelectorAll("select[name=\"adjustment\"]").forEach((select) => { select.value = "qfq"; });
}
async function applyBacktestPublishedCoverageDefaults() {
  const payload = await requestJson("/api/strategy-datasets");
  const coverageDates = (payload.items || [])
    .filter((item) => item.strategy_access === "executable")
    .map((item) => item.published_version?.coverage_end || item.published_version?.as_of_trade_date)
    .filter(Boolean)
    .sort();
  const commonCoverageEnd = coverageDates[0];
  if (!commonCoverageEnd) return;
  document.querySelectorAll("input[name=\"end_date\"]").forEach((input) => {
    input.max = commonCoverageEnd;
    input.title = `当前策略数据集共同可用截止日：${commonCoverageEnd}`;
    if (!input.value || input.value > commonCoverageEnd) input.value = commonCoverageEnd;
  });
}
function renderSingleRunHistory(runs = []) {
  const target = $("#single-run-history");
  if (!target) return;
  target.innerHTML = runs.length ? runs.map((run) => `<article class="compact-task-row ${run.run_id === currentBacktestResultRunId ? "is-selected" : ""}" data-single-history-run="${escapeHtml(run.run_id)}"><div><span class="task-status-badge is-${backtestStatusInfo(run.status).tone}">${escapeHtml(backtestStatusInfo(run.status).label)}</span><h4>${escapeHtml(run.strategy_name || run.run_id)}</h4><p>${escapeHtml(run.run_id)} · ${escapeHtml(run.universe || "-")} · ${formatTaskTimestamp(run.created_at)}</p></div><div class="task-row-actions"><button type="button" data-single-result="${escapeHtml(run.run_id)}">分析报告</button><button type="button" class="danger-button" data-single-delete="${escapeHtml(run.run_id)}">删除</button></div></article>`).join("") : '<div class="empty-cell">暂无单品种测试历史任务</div>';
  target.querySelectorAll("[data-single-result]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); currentModeTask = null; hideIndependentResultSelector(); target.querySelectorAll("[data-single-history-run]").forEach((card) => card.classList.toggle("is-selected", card.dataset.singleHistoryRun === button.dataset.singleResult)); loadBacktestResultPanel(button.dataset.singleResult).then(() => openBacktestWorkspaceView("results")).catch((error) => setFeedback(error.message, "error")); }));
  target.querySelectorAll("[data-single-delete]").forEach((button) => button.addEventListener("click", async (event) => { event.stopPropagation(); if (!window.confirm("确认删除该单品种测试历史任务？删除后仅从工作台隐藏。")) return; await requestJson(`/api/backtest/results/${encodeURIComponent(button.dataset.singleDelete)}`, { method: "DELETE" }); if (currentBacktestResultRunId === button.dataset.singleDelete) { currentBacktestResultRunId = ""; } await loadSingleRunHistory(); setFeedback("单品种测试历史任务已删除", "success"); }));
}
async function loadSingleRunHistory() { const payload = await requestJson("/api/backtest/runs"); const runs = (payload.runs || []).filter((run) => !run.extra_config?.screening_task_id && run.extra_config?.mode !== "shared_cash_portfolio" && run.extra_config?.portfolio_mode !== "shared_cash"); renderSingleRunHistory(runs); return runs; }
function configurePcBacktestWorkspace() {
  backtestQueryDateDefaults();
  applyBacktestPublishedCoverageDefaults().catch((error) => setFeedback("未能读取回测数据截止日：" + friendlyApiError(error.message), "error"));
  document.querySelector(".backtest-workflow")?.remove();
  document.querySelector('[data-backtest-view="overview"]')?.setAttribute("hidden", "hidden");
  document.querySelector('[data-backtest-view-target="overview"]')?.remove();

  const researchTab = document.querySelector('[data-backtest-view-target="results"]');
  if (researchTab) {
    researchTab.dataset.backtestViewTarget = "research";
    researchTab.textContent = "研究实验";
  }
  const tabContainer = document.querySelector(".backtest-view-tabs");
  ["strategy", "single", "independent", "portfolio", "research"].forEach((view) => {
    const tab = document.querySelector(`[data-backtest-view-target="${view}"]`);
    if (tabContainer && tab) tabContainer.append(tab);
  });
  const researchList = $("#strategy-research-list")?.closest("[data-backtest-view]");
  const experimentList = $("#backtest-experiment-index-list")?.closest("[data-backtest-view]");
  if (researchList) {
    researchList.dataset.backtestView = "research";
    const title = researchList.querySelector("h3");
    if (title) title.textContent = "\u53ef\u590d\u7528\u7814\u7a76\u65b9\u6848";
  }
  if (experimentList) {
    experimentList.dataset.backtestView = "research";
    const title = experimentList.querySelector("h3");
    if (title) title.textContent = "\u7814\u7a76\u5b9e\u9a8c\u76ee\u5f55";
  }

  const strategyActions = $("#strategy-parameter-scan")?.closest(".secondary-actions");
  const scanOutput = $("#strategy-scan-output");
  const matrixOutput = $("#strategy-matrix-output");
  if (strategyActions && researchList) {
    const panel = document.createElement("section");
    panel.className = "panel panel-wide backtest-view-panel research-tools-panel";
    panel.dataset.backtestView = "research";
    panel.innerHTML = '<div class="panel-header"><div><h3>高级参数研究</h3><p>高级研究能力集中在此，不影响日常策略编辑与三类回测任务。</p></div></div>' +
      '<div class="research-experiment-grid"><article><h4>快速参数敏感性测试</h4><p>围绕当前数值参数生成少量组合，观察参数变化对单股结果的影响。</p></article>' +
      '<article><h4>参数组合批量测试</h4><p>创建可保存、可重复执行的参数组合任务，并按收益风险指标排序。</p></article>' +
      '<article><h4>固化本次参数对比</h4><p>保存参数、指标、排名与最佳组合，不会再次运行回测。</p></article></div>';
    researchList.parentElement.insertBefore(panel, researchList);
    panel.append(strategyActions, scanOutput, matrixOutput);
    $("#strategy-parameter-scan").textContent = "开始敏感性测试";
    $("#strategy-matrix-create").textContent = "创建组合任务";
    $("#strategy-matrix-run").textContent = "执行组合任务";
    $("#strategy-scan-save-snapshot").textContent = "固化参数对比";
    const matrixDelete = document.createElement("button");
    matrixDelete.id = "strategy-matrix-delete";
    matrixDelete.type = "button";
    matrixDelete.className = "danger-button";
    matrixDelete.textContent = "删除当前组合任务";
    strategyActions.append(matrixDelete);
  }

  const resultActions = $("#backtest-results-refresh")?.closest(".button-row");
  if (resultActions && !$("#backtest-results-back")) {
    resultActions.insertAdjacentHTML("afterbegin", '<button id="backtest-results-back" type="button">返回任务</button>');
    resultActions.insertAdjacentHTML("beforeend", '<button id="backtest-results-delete" class="danger-button" type="button" disabled>删除任务</button>');
  }
  $("#backtest-results-back")?.addEventListener("click", returnFromBacktestResults);
  $("#backtest-results-delete")?.addEventListener("click", () => deleteSelectedBacktestTask().catch((error) => setFeedback(error.message, "error")));
  $("#strategy-matrix-delete")?.addEventListener("click", () => deleteCurrentParameterMatrixTask().catch((error) => setFeedback(error.message, "error")));
}
function bindBacktestWorkspace() {
  configurePcBacktestWorkspace();
  document.querySelectorAll("[data-backtest-view-target]").forEach((button) => button.addEventListener("click", () => {
    openBacktestWorkspaceView(button.dataset.backtestViewTarget).catch((error) => setFeedback(error.message, "error"));
  }));
  document.querySelectorAll("[data-backtest-view-jump]").forEach((button) => button.addEventListener("click", () => {
    openBacktestWorkspaceView(button.dataset.backtestViewJump).catch((error) => setFeedback(error.message, "error"));
  }));
  const screeningForm = $("#screening-task-form");
  const portfolioForm = $("#portfolio-task-form");
  setupAdvancedFields(screeningForm, ["scheduler_batch_size", "retry_count", "initial_cash"]);
  setupPortfolioExecutionPolicyFields(portfolioForm);
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
  activateBacktestView("single");
  loadSingleRunHistory().catch((error) => setFeedback(error.message, "error"));
  $("#single-run-history-refresh")?.addEventListener("click", () => loadSingleRunHistory().catch((error) => setFeedback(error.message, "error")));
}
function renderScreeningTask(task = {}) {
  if (task.task_id) setStage76ModeTaskState("independent",true,task);
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
  target.innerHTML = '<table><thead><tr><th>代码</th><th>名称</th><th>状态</th><th>总收益</th><th>年化收益</th><th>回测编号</th></tr></thead><tbody>' + items.map((item) => '<tr><td>' + escapeHtml(item.symbol) + '</td><td>' + escapeHtml(item.name) + '</td><td>' + escapeHtml(item.status) + '</td><td class="' + financialToneClass(item.metrics?.total_returns) + '">' + (item.metrics?.total_returns ?? "-") + '</td><td class="' + financialToneClass(item.metrics?.annualized_returns) + '">' + (item.metrics?.annualized_returns ?? "-") + '</td><td title="' + escapeHtml(item.run_id || "") + '">' + escapeHtml(shortTechnicalId(item.run_id)) + '</td><td>' + (item.run_id ? '<button type="button" data-screening-item-run="' + escapeHtml(item.run_id) + '">\u67e5\u770b\u660e\u7ec6</button>' : "-") + '</td></tr>').join("") + '</tbody></table>';
  target.querySelectorAll("[data-screening-item-run]").forEach((button) => button.addEventListener("click", () => { const task = currentScreeningTask?.task_id ? nativeModeTask(currentScreeningTask, "independent-screening") : currentModeTask; if (!task) return; currentModeTask = task; activateBacktestView("results"); loadIndependentScreeningResultWorkspace(task, button.dataset.screeningItemRun).catch((error) => setFeedback(error.message, "error")); }));
}

function renderScreeningResults(items = [], task = {}) {
  const target = $("#screening-entered-results");
  if (!items.length) { target.innerHTML = '<div class="empty-cell">暂无逐股处理结果</div>'; return; }
  const failed = items.filter((item) => item.status === "failed");
  const primaryFailure = failed[0] || null;
  const suggestedAction = primaryFailure?.error_details?.suggested_action || "";
  const failureSummary = primaryFailure
    ? `<div class="strategy-validation is-error"><strong>主要失败原因：${escapeHtml(primaryFailure.error_code || "未分类错误")}</strong><p>${escapeHtml(primaryFailure.error_message || "-")}</p><p><strong>解决方法：</strong>${escapeHtml(suggestedAction || "复制错误信息并检查策略数据和配置。")}</p><p>失败 ${escapeHtml(task.progress?.failed ?? failed.length)} 只；当前显示 ${failed.length} 条失败记录。</p></div>`
    : "";
  target.innerHTML = '<div class="panel-header"><div><h4>逐股处理结果</h4><p>失败股票不按零收益计入分析；可恢复错误可在修复数据后单独重试。</p></div>' + (failed.some((item) => item.retryable) ? '<button type="button" data-screening-retry-all>重试全部可恢复错误</button>' : '') + '</div>' + failureSummary + '<table data-vtable-mode="detail"><thead><tr><th>代码</th><th>名称</th><th>状态</th><th>总收益</th><th>错误码</th><th>错误阶段</th><th>错误信息</th><th>解决方法</th><th>操作</th></tr></thead><tbody>' + items.map((item) => {
    const statusLabel = item.status === "completed" ? (item.entered ? "成功 / 已建仓" : "成功 / 未建仓") : item.status;
    const actions = item.status === "failed"
      ? `${item.retryable ? `<button type="button" data-screening-item-retry="${escapeHtml(item.symbol)}">重试</button>` : ""}<button type="button" data-screening-data-repair="${escapeHtml(item.symbol)}">去数据中心</button>`
      : (item.run_id && item.entered ? `<button type="button" data-screening-item-run="${escapeHtml(item.run_id)}">查看明细</button>` : "-");
    return `<tr><td>${escapeHtml(item.symbol)}</td><td>${escapeHtml(item.name)}</td><td>${escapeHtml(statusLabel)}</td><td class="${financialToneClass(item.metrics?.total_returns)}">${item.metrics?.total_returns ?? "-"}</td><td>${escapeHtml(item.error_code || "-")}</td><td>${escapeHtml(item.error_stage || "-")}</td><td title="${escapeHtml(item.error_message || "")}">${escapeHtml(item.error_message || "-")}</td><td>${escapeHtml(item.error_details?.suggested_action || "-")}</td><td>${actions}</td></tr>`;
  }).join("") + '</tbody></table>';
  target.querySelectorAll("[data-screening-item-run]").forEach((button) => button.addEventListener("click", () => { const task = currentScreeningTask?.task_id ? nativeModeTask(currentScreeningTask, "independent-screening") : currentModeTask; if (!task) return; currentModeTask = task; activateBacktestView("results"); loadIndependentScreeningResultWorkspace(task, button.dataset.screeningItemRun).catch((error) => setFeedback(error.message, "error")); }));
  target.querySelectorAll("[data-screening-item-retry]").forEach((button) => button.addEventListener("click", () => retryIndependentScreeningFailures([button.dataset.screeningItemRetry]).catch((error) => setFeedback(error.message, "error"))));
  target.querySelector("[data-screening-retry-all]")?.addEventListener("click", () => retryIndependentScreeningFailures([]).catch((error) => setFeedback(error.message, "error")));
  target.querySelectorAll("[data-screening-data-repair]").forEach((button) => button.addEventListener("click", () => {
    if (typeof activatePage === "function") activatePage("market");
    setFeedback(`请在数据中心检查 ${button.dataset.screeningDataRepair} 的日线及策略依赖数据，修复后返回任务重试`, "error");
  }));
  window.AppVTable?.enhanceAll(target);
}

async function retryIndependentScreeningFailures(symbols = []) {
  if (!currentScreeningTaskId) throw new Error("请先选择独立账户批量回测任务");
  await requestJson(`/api/backtest/independent-screening-tasks/${encodeURIComponent(currentScreeningTaskId)}/retry-failures`, { method: "POST", body: JSON.stringify({ symbols, wait: false }) });
  await loadIndependentScreeningTask(currentScreeningTaskId);
  setFeedback(symbols.length ? `已重试 ${symbols.join(", ")}` : "已重试全部可恢复错误", "success");
}

async function loadIndependentScreeningTask(taskId, { schedule = true } = {}) {
  if (!taskId) return null;
  currentScreeningTaskId = taskId;
  const detail = await requestJson(`/api/backtest/independent-screening-tasks/${encodeURIComponent(taskId)}`);
  const task = detail.task || {};
  const itemPayload = await requestJson(`/api/backtest/independent-screening-tasks/${encodeURIComponent(taskId)}/items?limit=500`);
  const itemResult = itemPayload.result || {};
  renderScreeningTask(task);
  renderScreeningResults(itemResult.items || [], task);
  if (["completed", "partial_completed", "partial_failed", "failed", "canceled"].includes(task.status)) { loadIndependentScreeningTasks().catch(() => {}); loadBacktestModeTasks().catch(() => {}); }
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
    return '<article class="compact-task-row is-' + info.tone + (task.task_id === currentScreeningTaskId ? " is-selected" : "") + '" data-screening-task="' + escapeHtml(task.task_id) + '">' +
      '<div><span class="task-status-badge is-' + info.tone + '">' + escapeHtml(info.label) + '</span><h4>' + escapeHtml(strategyDisplayName(task.config?.strategy_id) + " · 独立账户批量回测") + '</h4><p>' + escapeHtml(taskExecutionLabel(task)) + ' · ' + progress.total + ' 只' + (taskElapsedSeconds(task) > 0 ? ' · 耗时 ' + escapeHtml(formatTaskSeconds(taskElapsedSeconds(task))) : '') + '</p></div>' +
      '<div class="task-card-progress"><div><i style="width:' + progress.percent + '%"></i></div><span>' + Math.round(progress.percent) + '% · ' + progress.processed + '/' + progress.total + '</span></div></article>';
  }).join("") || '<div class="empty-cell">暂无独立账户批量回测任务</div>';
  document.querySelectorAll("[data-screening-task]").forEach((card) => card.addEventListener("click", async () => {
    const task = tasks.find((item) => item.task_id === card.dataset.screeningTask);
    document.querySelectorAll("[data-screening-task]").forEach((item) => item.classList.toggle("is-selected", item === card));
    currentModeTask = task ? {
      task_id: task.task_id,
      mode: "independent-screening",
      mode_label: "独立账户批量回测",
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
  document.querySelectorAll("[data-screening-task]").forEach((card) => {
    const task = tasks.find((item) => item.task_id === card.dataset.screeningTask);
    if (!task) return;
    const actions = document.createElement("div");
    actions.className = "task-row-actions";
    actions.innerHTML = '<button type="button" data-screening-result="' + escapeHtml(task.task_id) + '">\u67e5\u770b\u7ed3\u679c</button>' +
      '<button type="button" class="danger-button" data-screening-delete="' + escapeHtml(task.task_id) + '"' +
      (taskCanDelete(task) ? "" : ' disabled title="\u8fd0\u884c\u4e2d\u4efb\u52a1\u8bf7\u5148\u53d6\u6d88"') + '>\u5220\u9664</button>';
    card.append(actions);
  });
  document.querySelectorAll("[data-screening-result]").forEach((button) => button.addEventListener("click", async (event) => {
    event.stopPropagation();
    const task = tasks.find((item) => item.task_id === button.dataset.screeningResult);
    if (task) await showBacktestTaskResults(nativeModeTask(task, "independent-screening"));
  }));
  document.querySelectorAll("[data-screening-delete]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteNativeModeTask(tasks.find((item) => item.task_id === button.dataset.screeningDelete), "independent-screening").catch((error) => setFeedback(error.message, "error"));
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
  setFeedback("正在创建独立账户批量回测任务，请稍候");
  try {
    const values = Object.fromEntries(new FormData(form).entries());
    const backtestForm = Object.fromEntries(new FormData($("#backtest-run-form")).entries());
    const body = {
      task_id: values.task_id || newTaskId("screening"),
      name: (selectedStrategy?.name || "策略") + " 独立账户批量回测",
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
    setFeedback("独立账户批量回测任务已创建：" + taskDisplayTitle(currentModeTask || {}), "success");
  } catch (error) {
    setFeedback("独立账户批量回测创建失败：" + error.message, "error");
    throw error;
  } finally {
    if (submit) { submit.disabled = false; submit.textContent = originalLabel; }
  }
}
async function runIndependentScreeningTask() {
  if (!currentScreeningTaskId) throw new Error("请先创建或选择独立账户批量回测任务");
  await requestJson(`/api/backtest/independent-screening-tasks/${encodeURIComponent(currentScreeningTaskId)}/run`, { method: "POST", body: JSON.stringify({ wait: false }) });
  await loadIndependentScreeningTask(currentScreeningTaskId);
  await loadBacktestModeTasks();
  setFeedback(`独立账户批量回测任务已启动：${currentScreeningTaskId}`, "success");
}
async function controlIndependentScreeningTask(action) {
  if (!currentScreeningTaskId) throw new Error("请先创建或选择独立账户批量回测任务");
  const payload = await requestJson(
    `/api/backtest/independent-screening-tasks/${encodeURIComponent(currentScreeningTaskId)}/control`,
    { method: "POST", body: JSON.stringify({ action }) },
  );
  renderScreeningTask(payload.task || {});
  await loadBacktestModeTasks();
  setFeedback(`独立账户批量回测任务控制已提交：${action}`, "success");
}
function renderPortfolioTask(task = {}) {
  if (task.task_id) setStage76ModeTaskState("portfolio",true,task);
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
  if (["completed", "partial_completed", "partial_failed", "failed", "canceled"].includes(task.status)) { loadSharedPortfolioTasks().catch(() => {}); loadBacktestModeTasks().catch(() => {}); }
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
    return '<article class="compact-task-row is-' + info.tone + (task.task_id === currentPortfolioTaskId ? " is-selected" : "") + '" data-portfolio-task="' + escapeHtml(task.task_id) + '">' +
      '<div><span class="task-status-badge is-' + info.tone + '">' + escapeHtml(info.label) + '</span><h4>' + escapeHtml(strategyDisplayName(task.config?.strategy_id) + " · 投资组合回测") + '</h4><p>' + escapeHtml(taskExecutionLabel(task)) + ' · ' + (task.universe_count || 0) + ' 只 · 最多持仓 ' + (task.config?.max_positions || "-") + (taskElapsedSeconds(task) > 0 ? ' · 耗时 ' + escapeHtml(formatTaskSeconds(taskElapsedSeconds(task))) : '') + '</p></div>' +
      '<div class="task-card-progress"><div><i style="width:' + progress.percent + '%"></i></div><span>' + Math.round(progress.percent) + '% · ' + progress.processed + '/' + progress.total + '</span></div></article>';
  }).join("") || '<div class="empty-cell">暂无投资组合回测任务</div>';
  document.querySelectorAll("[data-portfolio-task]").forEach((card) => card.addEventListener("click", async () => {
    const task = tasks.find((item) => item.task_id === card.dataset.portfolioTask);
    document.querySelectorAll("[data-portfolio-task]").forEach((item) => item.classList.toggle("is-selected", item === card));
    currentModeTask = task ? {
      task_id: task.task_id,
      mode: "shared-portfolio",
      mode_label: "投资组合回测",
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
  document.querySelectorAll("[data-portfolio-task]").forEach((card) => {
    const task = tasks.find((item) => item.task_id === card.dataset.portfolioTask);
    if (!task) return;
    const actions = document.createElement("div");
    actions.className = "task-row-actions";
    actions.innerHTML = '<button type="button" data-portfolio-result="' + escapeHtml(task.task_id) + '">\u67e5\u770b\u7ed3\u679c</button>' +
      '<button type="button" class="danger-button" data-portfolio-delete="' + escapeHtml(task.task_id) + '"' +
      (taskCanDelete(task) ? "" : ' disabled title="\u8fd0\u884c\u4e2d\u4efb\u52a1\u8bf7\u5148\u53d6\u6d88"') + '>\u5220\u9664</button>';
    card.append(actions);
  });
  document.querySelectorAll("[data-portfolio-result]").forEach((button) => button.addEventListener("click", async (event) => {
    event.stopPropagation();
    const task = tasks.find((item) => item.task_id === button.dataset.portfolioResult);
    if (task) await showBacktestTaskResults(nativeModeTask(task, "shared-portfolio"));
  }));
  document.querySelectorAll("[data-portfolio-delete]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteNativeModeTask(tasks.find((item) => item.task_id === button.dataset.portfolioDelete), "shared-portfolio").catch((error) => setFeedback(error.message, "error"));
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
  setFeedback("正在创建投资组合回测任务，请稍候");
  try {
    const values = Object.fromEntries(new FormData(form).entries());
    const backtestForm = Object.fromEntries(new FormData($("#backtest-run-form")).entries());
    const body = {
      task_id: values.task_id || newTaskId("portfolio"),
      name: (selectedStrategy?.name || "策略") + " 投资组合",
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
      rebalance_policy: values.rebalance_policy || null,
      capacity_replacement_policy: values.capacity_replacement_policy || null,
      max_single_position_weight: values.max_single_position_weight ? Number(values.max_single_position_weight) : null,
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
    setFeedback("投资组合回测任务已创建：" + taskDisplayTitle(currentModeTask || {}), "success");
  } catch (error) {
    setFeedback("投资组合回测创建失败：" + error.message, "error");
    throw error;
  } finally {
    if (submit) { submit.disabled = false; submit.textContent = originalLabel; }
  }
}
async function runSharedPortfolioTask() {
  if (!currentPortfolioTaskId) throw new Error("请先创建或选择投资组合回测任务");
  await requestJson(`/api/backtest/shared-portfolio-tasks/${encodeURIComponent(currentPortfolioTaskId)}/run`, { method: "POST", body: JSON.stringify({ wait: false }) });
  await loadSharedPortfolioTask(currentPortfolioTaskId);
  await loadBacktestModeTasks();
  setFeedback(`投资组合回测任务已启动：${currentPortfolioTaskId}`, "success");
}

function taskCanDelete(task = {}) {
  return !["pending", "running", "pause_requested", "cancel_requested"].includes(task.status);
}

function nativeModeTask(task, mode) {
  const independent = mode === "independent-screening";
  return {
    task_id: task.task_id,
    mode,
    mode_label: independent ? "独立账户批量回测" : "投资组合回测",
    name: task.config?.name || task.task_id,
    status: task.status,
    strategy_binding: { strategy_id: task.config?.strategy_id, strategy_version: task.config?.strategy_version },
    date_window: task.config?.date_window || {},
    universe_count: independent ? (task.progress?.total || 0) : (task.universe_count || 0),
    run_id: task.run_id,
    progress: task.progress || {},
    execution: task.execution || {},
    created_at: task.created_at,
    updated_at: task.updated_at,
    started_at: task.started_at,
    finished_at: task.finished_at,
    links: { report: "/api/reporting/backtest-modes/" + mode + "/" + encodeURIComponent(task.task_id) },
  };
}

async function deleteNativeModeTask(task, mode) {
  if (!task) return;
  if (!taskCanDelete(task)) throw new Error("\u8fd0\u884c\u4e2d\u4efb\u52a1\u8bf7\u5148\u53d6\u6d88\uff0c\u518d\u6267\u884c\u5220\u9664");
  if (!window.confirm(`\u786e\u8ba4\u5220\u9664\u4efb\u52a1 ${task.task_id}\uff1f\u5220\u9664\u540e\u4ecd\u4fdd\u7559\u5ba1\u8ba1\u8bb0\u5f55\uff0c\u4efb\u52a1\u7f16\u53f7\u4e0d\u4f1a\u91cd\u7528\u3002`)) return;
  const resource = mode === "independent-screening" ? "independent-screening-tasks" : "shared-portfolio-tasks";
  await requestJson(`/api/backtest/${resource}/${encodeURIComponent(task.task_id)}`, { method: "DELETE" });
  if (mode === "independent-screening") {
    if (currentScreeningTaskId === task.task_id) { currentScreeningTaskId = null; currentScreeningTask = null; }
    await loadIndependentScreeningTasks();
  } else {
    if (currentPortfolioTaskId === task.task_id) { currentPortfolioTaskId = null; currentPortfolioTask = null; }
    await loadSharedPortfolioTasks();
  }
  if (currentModeTask?.task_id === task.task_id && currentModeTask?.mode === mode) currentModeTask = null;
  renderBacktestWorkspace();
  renderBacktestResultsContext();
  setFeedback(`\u4efb\u52a1\u5df2\u5220\u9664\uff1a${task.task_id}`, "success");
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

function independentResultSelector() {
  let target = $("#independent-result-run-selector");
  if (target) return target;
  target = document.createElement("section");
  target.id = "independent-result-run-selector";
  target.className = "independent-result-run-selector";
  $("#backtest-result-panel-summary")?.before(target);
  return target;
}
function hideIndependentResultSelector() {
  const target = $("#independent-result-run-selector");
  if (target) target.hidden = true;
}
async function loadIndependentScreeningResultWorkspace(task, preferredRunId = "") {
  const selection = ++backtestResultSelectionSequence;
  const target = independentResultSelector();
  target.hidden = false;
  const items = [];
  let offset = 0;
  while (true) {
    const payload = await requestJson(`/api/backtest/independent-screening-tasks/${encodeURIComponent(task.task_id)}/items?entered_only=true&limit=100&offset=${offset}`);
    if (selection !== backtestResultSelectionSequence) return null;
    const page = payload.result || {};
    const rows = page.items || [];
    items.push(...rows.filter((item) => item.run_id));
    offset += rows.length;
    if (!rows.length || offset >= Number(page.total ?? offset)) break;
  }
  if (!items.length) {
    currentBacktestResultRunId = "";
    currentBacktestRunIdPrefix = "";
    target.innerHTML = '<div class="empty-cell">该任务暂无实际建仓股票，因此没有可展示的交易明细。</div>';
    $("#backtest-result-panel-tables").innerHTML = '<div class="empty-cell">独立账户批量回测仅展示实际建仓股票的真实回测结果。</div>';
    $("#backtest-result-page-table").innerHTML = "";
    $("#backtest-result-panel-output").textContent = "";
    return null;
  }
  const selectedRunId = items.some((item) => item.run_id === preferredRunId) ? preferredRunId : items[0].run_id;
  target.innerHTML = `<h4>实际建仓股票明细</h4><p>选择股票后查看其独立资金回测的交易、持仓和账户数据。</p><div class="independent-result-run-list">${items.map((item) => `<button type="button" data-independent-result-run="${escapeHtml(item.run_id)}" class="${item.run_id === selectedRunId ? "is-selected" : ""}">${escapeHtml(item.symbol)}${item.name ? ` · ${escapeHtml(item.name)}` : ""}</button>`).join("")}</div>`;
  target.querySelectorAll("[data-independent-result-run]").forEach((button) => button.addEventListener("click", async () => {
    target.querySelectorAll("[data-independent-result-run]").forEach((item) => item.classList.toggle("is-selected", item === button));
    await loadBacktestResultPanel(button.dataset.independentResultRun);
  }));
  await loadBacktestResultPanel(selectedRunId);
  return selectedRunId;
}

async function showBacktestTaskResults(task) {
  await selectBacktestModeTask(task, { schedule: false });
  activateBacktestView("results");
  renderBacktestResultsContext();
  if (task.mode === "shared-portfolio" && task.run_id) {
    hideIndependentResultSelector();
    await loadBacktestResultPanel(task.run_id);
  } else if (task.mode === "independent-screening") {
    await loadIndependentScreeningResultWorkspace(task);
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
      hideIndependentResultSelector();
      await loadBacktestResultPanel(context.task.run_id);
    } else if (context.task.mode === "independent-screening") {
      await loadIndependentScreeningResultWorkspace(context.task, currentBacktestResultRunId);
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

function returnFromBacktestResults() {
  const context = selectedResultContext();
  activateBacktestView(context?.kind === "mode"
    ? (context.task.mode === "independent-screening" ? "independent" : "portfolio")
    : "single");
}

async function deleteSelectedBacktestTask() {
  const context = selectedResultContext();
  if (!context) return;
  if (context.kind === "mode") {
    const returnView = context.task.mode === "independent-screening" ? "independent" : "portfolio";
    await deleteNativeModeTask(context.task, context.task.mode);
    activateBacktestView(returnView);
    return;
  }
  const runId = context.task.runId;
  if (!runId || !window.confirm(`\u786e\u8ba4\u5220\u9664\u5355\u80a1\u56de\u6d4b ${runId}\uff1f\u5220\u9664\u540e\u4ecd\u4fdd\u7559\u5ba1\u8ba1\u8bb0\u5f55\u3002`)) return;
  await requestJson(`/api/backtest/results/${encodeURIComponent(runId)}`, { method: "DELETE" });
  singleRunState = { status: "idle", phase: "\u7b49\u5f85\u914d\u7f6e", runId: "", strategyName: "", symbol: "", startedAt: null, elapsedSeconds: 0, result: null, error: "" };
  currentBacktestResultRunId = "";
  currentBacktestRunIdPrefix = "";
  const reportJump = $("#backtest-jump-reporting");
  if (reportJump) {
    reportJump.disabled = true;
    delete reportJump.dataset.runId;
  }
  renderSingleRunProgress();
  renderBacktestResultsContext();
  activateBacktestView("single");
  setFeedback(`\u5355\u80a1\u56de\u6d4b\u5df2\u5220\u9664\uff1a${runId}`, "success");
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
    { label: "独立账户批量回测", value: summary.mode_counts?.["independent-screening"] || 0 },
    { label: "投资组合回测", value: summary.mode_counts?.["shared-portfolio"] || 0 },
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
  target.querySelectorAll(".definition-item").forEach((card, index) => {
    const row = card.querySelector(".button-row");
    if (!row || !tasks[index]) return;
    row.insertAdjacentHTML("beforeend", '<button type="button" class="danger-button" data-research-delete="' + escapeHtml(tasks[index].task_id) + '">\u5220\u9664</button>');
  });
}
async function loadStrategyResearchTasks() {
  const payload = await requestJson("/api/backtest/research-tasks");
  renderStrategyResearchTasks(payload.tasks || []);
  document.querySelectorAll("[data-research-run]").forEach((button) => button.addEventListener("click", () => runStrategyResearchTask(button.dataset.researchRun)));
  document.querySelectorAll("[data-research-delete]").forEach((button) => button.addEventListener("click", () => deleteStrategyResearchTask(button.dataset.researchDelete).catch((error) => setFeedback(error.message, "error"))));
  return payload.tasks || [];
}
async function deleteStrategyResearchTask(taskId) {
  if (!taskId || !window.confirm(`\u786e\u8ba4\u5220\u9664\u7814\u7a76\u4efb\u52a1 ${taskId}\uff1f\u5220\u9664\u540e\u4ecd\u4fdd\u7559\u5ba1\u8ba1\u8bb0\u5f55\u3002`)) return;
  await requestJson(`/api/backtest/research-tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
  await loadStrategyResearchTasks();
  setFeedback(`\u7814\u7a76\u4efb\u52a1\u5df2\u5220\u9664\uff1a${taskId}`, "success");
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
  const sort = $("#strategy-library-sort")?.value || "name";
  const filtered = strategyCatalog.filter((strategy) => {
    const matchesSearch = !search || `${strategy.name} ${strategy.strategy_id} ${strategy.description}`.toLowerCase().includes(search);
    return matchesSearch && (!category || strategy.category === category);
  }).sort((left, right) => {
    if (sort === "category") return `${left.category || ""} ${left.name || ""}`.localeCompare(`${right.category || ""} ${right.name || ""}`, "zh-CN");
    if (sort === "versions") return Number(right.version_count || 0) - Number(left.version_count || 0) || String(left.name || "").localeCompare(String(right.name || ""), "zh-CN");
    return String(left.name || left.strategy_id || "").localeCompare(String(right.name || right.strategy_id || ""), "zh-CN");
  });
  $("#strategy-library-count").textContent = `${filtered.length} / ${strategyCatalog.length} 个策略`;
  $("#strategy-library").innerHTML = filtered.length ? filtered.map((strategy) => {
    const active = selectedStrategy?.strategy_id === strategy.strategy_id;
    return `<button type="button" class="strategy-library-item${active ? " is-selected" : ""}" data-strategy-id="${escapeHtml(strategy.strategy_id)}" title="${escapeHtml(strategy.description || strategy.name || strategy.strategy_id)}"><span class="strategy-library-item-main"><strong>${escapeHtml(strategy.name)}</strong><small>${escapeHtml(strategy.strategy_id)}</small></span><span class="strategy-library-item-meta"><em>${escapeHtml(strategy.category)}</em><span>${escapeHtml(strategy.latest_version || "v1")} · ${strategy.version_count || 1} 版</span></span></button>`;
  }).join("") : '<div class="empty-cell">没有符合条件的策略</div>';
}function strategyParameterLabel(key) {
  const labels = { short_window: "短均线周期", long_window: "长均线周期", atr_window: "ATR 周期", atr_multiplier: "ATR 止损倍数", position_size: "目标仓位", commission: "手续费率", breakout_window: "突破周期", max_position: "最大仓位", minimum_listing_bars: "最低上市交易日数", trough_window: "低点观察窗口", winner_window: "获利盘计算窗口", winner_spread_min: "获利盘差值下限", trailing_stop: "移动止损保留比例", volume_ratio_window: "成交量均值窗口", execution_price: "信号执行价格", index_symbol: "基准指数" };
  return labels[key] || key;
}
function coerceParameterValue(value, spec = {}) {
  if (spec.type === "integer") {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed)) throw new Error("整数参数不能为空或包含非法字符");
    return parsed;
  }
  if (spec.type === "number") {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) throw new Error("数值参数不能为空或包含非法字符");
    return parsed;
  }
  if (spec.type === "boolean") return value === true || value === "true" || value === "on";
  if (["list", "symbol_list"].includes(spec.type)) return String(value || "").split(/[,，\n\s]+/).map((item) => item.trim()).filter(Boolean);
  return value;
}
function collectStrategyParameters() {
  const parameters = { ...(selectedStrategy?.parameters || {}) };
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
    const value = parameters[key] ?? spec.default ?? "";
    const label = spec.label || strategyParameterLabel(key);
    const unit = spec.unit ? ` · ${escapeHtml(spec.unit)}` : "";
    const help = spec.help || spec.description || "";
    if (spec.type === "enum") {
      return `<label class="strategy-parameter-field"><span>${escapeHtml(label)}${unit}</span><select data-param-key="${escapeHtml(key)}">${(spec.options || []).map((option) => { const optionValue = typeof option === "object" ? option.value : option; const optionLabel = typeof option === "object" ? (option.label || option.value) : option; return `<option value="${escapeHtml(optionValue)}" ${optionValue === value ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`; }).join("")}</select><small>${escapeHtml(help || key)}</small></label>`;
    }
    if (spec.type === "boolean") {
      return `<label class="strategy-parameter-field strategy-toggle-field"><span>${escapeHtml(label)}${unit}</span><input data-param-key="${escapeHtml(key)}" type="checkbox" ${value ? "checked" : ""}><small>${escapeHtml(help || key)}</small></label>`;
    }
    if (["list", "symbol_list"].includes(spec.type)) return `<label class="strategy-parameter-field"><span>${escapeHtml(label)}${unit}</span><textarea data-param-key="${escapeHtml(key)}" rows="2" placeholder="使用逗号或换行分隔">${escapeHtml(Array.isArray(value) ? value.join(", ") : value)}</textarea><small>${escapeHtml(help || key)}</small></label>`;
    const numeric = spec.type === "integer" || spec.type === "number";
    const type = numeric ? "number" : spec.type === "date" ? "date" : "text";
    const step = spec.step ?? (spec.type === "integer" ? "1" : "any");
    const min = spec.min == null ? "" : ` min="${spec.min}"`;
    const max = spec.max == null ? "" : ` max="${spec.max}"`;
    const required = spec.required ? " required" : "";
    return `<label class="strategy-parameter-field"><span>${escapeHtml(label)}${unit}</span><input data-param-key="${escapeHtml(key)}" type="${type}" step="${step}"${min}${max}${required} value="${escapeHtml(value)}"><small>${escapeHtml(help || key)}</small></label>`;
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
  renderStage76CodeHighlight();
  renderParameterForm(strategy);
  try {
    const history = await requestJson(`/api/backtest/strategies/${encodeURIComponent(strategy.strategy_id)}/versions`);
    const versions = history.versions || [];
    const historyNode=$("#strategy-version-history");
    if(historyNode) historyNode.innerHTML = versions.slice().reverse().map((version, index) => `<button type="button" class="strategy-version-item${version.latest_version === strategy.latest_version ? " is-current" : ""}" data-strategy-version-index="${versions.length - index - 1}"><strong>${escapeHtml(version.latest_version)}</strong><span>${escapeHtml(version.saved_at || "")}</span><small>${escapeHtml((version.source_sha256 || "").slice(0, 12))}</small></button>`).join("") || '<div class="empty-cell">暂无版本</div>';
    const displayVersions=versions.slice().reverse();
    const versionSelect=$("#strategy-version-select");
    if(versionSelect){
      versionSelect.innerHTML=displayVersions.map((version,index)=>`<option value="${index}" ${version.latest_version===strategy.latest_version?"selected":""}>${escapeHtml(version.latest_version)} · ${escapeHtml(version.saved_at||"未记录时间")}</option>`).join("") || '<option value="">暂无版本</option>';
      versionSelect.onchange=()=>{const selected=displayVersions[Number(versionSelect.value)];if(selected)selectStrategy(selected).catch((error)=>setFeedback(error.message,"error"));};
    }
  } catch (error) {
    const historyNode=$("#strategy-version-history"); if(historyNode) historyNode.innerHTML = `<div class="empty-cell">版本加载失败：${escapeHtml(error.message)}</div>`;
    const versionSelect=$("#strategy-version-select"); if(versionSelect) versionSelect.innerHTML='<option value="">版本加载失败</option>';
  }
}
function inferStrategyParameterSchema(parameters = {}) {
  return Object.fromEntries(Object.entries(parameters).map(([key, value]) => {
    const type = typeof value === "boolean" ? "boolean" : Number.isInteger(value) ? "integer" : typeof value === "number" ? "number" : "string";
    const spec = { type };
    if (key === "position_size") Object.assign(spec, { min: 0, max: 1 });
    return [key, spec];
  }));
}
function startNewStrategy(seed = {}) {
  const parameters = { ...(seed.parameters || { position_size: 1.0 }) };
  selectedStrategy = {
    strategy_id: seed.strategy_id || "custom_strategy",
    name: seed.name || "自定义策略",
    category: seed.category || "自定义策略",
    description: seed.description || "",
    parameters,
    parameter_schema: seed.parameter_schema || inferStrategyParameterSchema(parameters),
    source_code: seed.source_code || newStrategyTemplate,
    latest_version: "未保存",
    version_count: 0,
    validation_status: "pending",
  };
  renderStrategyLibrary();
  renderBacktestWorkspace();
  $("#strategy-draft-id").value = selectedStrategy.strategy_id;
  $("#strategy-draft-id").readOnly = false;
  $("#strategy-draft-name").value = selectedStrategy.name;
  setStrategyCategory(selectedStrategy.category);
  $("#strategy-draft-description").value = selectedStrategy.description;
  $("#strategy-editor").value = selectedStrategy.source_code;
  renderStage76CodeHighlight();
  $("#strategy-editor-meta").textContent = "新策略 / 尚未保存";
  $("#strategy-editor-state").textContent = "新建中";
  $("#strategy-delete").disabled = true;
  const historyNode=$("#strategy-version-history"); if(historyNode) historyNode.innerHTML = '<div class="empty-cell">保存后生成 v1</div>';
  const versionSelect=$("#strategy-version-select"); if(versionSelect) versionSelect.innerHTML='<option value="">未保存</option>';
  $("#strategy-validation-output").textContent = "等待策略校验";
  $("#strategy-validation-output").className = "inline-status";
  renderParameterForm(selectedStrategy);
  $("#strategy-draft-name").focus();
}
async function validateStrategySource() {
  const payload = await requestJson("/api/backtest/strategies/validate", { method: "POST", body: JSON.stringify({ source_code: $("#strategy-editor").value }) });
  const validation = payload.validation || {};
  const issues = (validation.issues || []).map((item) => `${item.line ? `第 ${item.line} 行：` : ""}${item.message}`).join("；");
  const warnings = (validation.warnings || []).map((item) => item.message).join("；");
  if (validation.ok && Object.keys(validation.parameter_schema || {}).length) {
    selectedStrategy.parameter_schema = validation.parameter_schema;
    selectedStrategy.parameters = { ...(validation.parameter_defaults || {}), ...(selectedStrategy.parameters || {}) };
    selectedStrategy.parameters = Object.fromEntries(Object.entries(selectedStrategy.parameters).filter(([key]) => key in selectedStrategy.parameter_schema));
    renderParameterForm(selectedStrategy);
  }
  $("#strategy-validation-output").textContent = validation.ok ? `校验通过 · ${validation.contract || "target-weights-v1"}${warnings ? ` · 提示：${warnings}` : ""}` : `校验失败 · ${issues || "请检查策略源码"}`;
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
  const selection = ++backtestResultSelectionSequence;
  currentBacktestResultRunId = runId;
  openStage75ResultDock(runId);
  currentBacktestRunIdPrefix = runId.replace(/-\d+$/, "");
  const payload = await requestJson(`/api/backtest/results/${encodeURIComponent(runId)}/panel`);
  if (selection !== backtestResultSelectionSequence || currentBacktestResultRunId !== runId) return null;
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
  renderStage76ResultDetails(result);
  $("#backtest-result-panel-tables").innerHTML = `<h4>交易明细</h4>${renderTable(result.trades || [], [{key:"trade_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"side",label:"方向"},{key:"price",label:"价格"},{key:"quantity",label:"数量"},{key:"amount",label:"成交额"}])}<h4>持仓快照</h4>${renderTable(result.positions || [], [{key:"snapshot_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"quantity",label:"数量"},{key:"market_value",label:"市值"}])}<h4>账户快照</h4>${renderTable(result.accounts || [], [{key:"snapshot_time",label:"时间"},{key:"total_value",label:"总资产"},{key:"cash",label:"现金"},{key:"unit_net_value",label:"单位净值"}])}<h4>年度收益</h4>${renderTable(result.yearly_returns || [], [{key:"year",label:"年度"},{key:"portfolio_return",label:"组合收益"},{key:"benchmark_return",label:"基准收益"},{key:"excess_return",label:"超额收益"}])}`;
  $("#backtest-result-panel-output").textContent = JSON.stringify({ summary, metrics: result.metrics || {}, trade_attribution: result.trade_attribution || {}, risk_metrics: result.risk_metrics || {}, exposure_summary: result.exposure_summary || {}, parameter_snapshot: result.parameter_snapshot || {}, input_snapshot: result.input_snapshot || {}, data_asset_trace: result.data_asset_trace || {}, logs: result.logs || [] }, null, 2);
  await loadBacktestResultTable(0);
  return result;
}
async function loadBacktestResultTable(offset = 0, exportFormat = "json") {
  if (!currentBacktestResultRunId) return null;
  const runId = currentBacktestResultRunId;
  const selection = backtestResultSelectionSequence;
  const requestId = ++backtestTableRequestSequence;
  currentBacktestTableOffset = Math.max(0, offset);
  const query = buildQuery({ table: "trades", offset: currentBacktestTableOffset, limit: currentBacktestTableLimit, export_format: exportFormat });
  const payload = await requestJson(`/api/backtest/results/${encodeURIComponent(runId)}/table?${query}`);
  if (requestId !== backtestTableRequestSequence || selection !== backtestResultSelectionSequence || runId !== currentBacktestResultRunId) return null;
  const result = payload.result || {};
  $("#backtest-result-page-table").innerHTML = `<h4>分页交易明细 ${result.offset || 0} / ${result.total || 0}</h4>${renderTable(result.rows || [], [{key:"trade_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"side",label:"方向"},{key:"price",label:"价格"},{key:"quantity",label:"数量"},{key:"amount",label:"成交额"}])}`;
  if (exportFormat !== "json") $("#backtest-result-export-output").textContent = result.content || "";
  const prev = $("#backtest-table-prev"); const next = $("#backtest-table-next");
  if (prev) prev.disabled = (result.offset ?? 0) <= 0;
  if (next) next.disabled = result.has_next !== true;
  return result;
}
async function exportBacktestResultTable(format) {
  const result = await loadBacktestResultTable(currentBacktestTableOffset, format);
  if (!result) return;
  const content = format === "csv" ? (result?.content || "") : JSON.stringify(result?.content || result?.rows || [], null, 2);
  $("#backtest-result-export-output").textContent = content;
  const blob = new Blob([content], { type: format === "csv" ? "text/csv;charset=utf-8" : "application/json;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `${currentBacktestResultRunId}-trades.${format}`; link.click(); URL.revokeObjectURL(link.href);
  window.alert(`\u5bfc\u51fa\u6210\u529f\uff1a${link.download}\uff0c\u6587\u4ef6\u5df2\u4fdd\u5b58\u5230\u6d4f\u89c8\u5668\u9ed8\u8ba4\u4e0b\u8f7d\u76ee\u5f55\u3002`);
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
      phase: result.status === "failed" ? "单品种测试执行失败" : "单品种测试完成，结果已载入",
      elapsedSeconds: elapsed,
      startedAt: null,
      result,
      error: result.error_message || "",
    });
    await loadSingleRunHistory();
    activateBacktestView("results");
    return result;
  } catch (error) {
    const elapsed = singleRunState.startedAt ? (Date.now() - singleRunState.startedAt) / 1000 : 0;
    setSingleRunState({
      status: "failed",
      phase: "单品种测试失败：" + error.message,
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
async function deleteCurrentParameterMatrixTask() {
  if (!currentParameterMatrixTaskId) throw new Error("\u5c1a\u672a\u9009\u62e9\u53c2\u6570\u7ec4\u5408\u4efb\u52a1");
  if (!window.confirm(`\u786e\u8ba4\u5220\u9664\u53c2\u6570\u7ec4\u5408\u4efb\u52a1 ${currentParameterMatrixTaskId}\uff1f`)) return;
  await requestJson(`/api/backtest/parameter-matrix-tasks/${encodeURIComponent(currentParameterMatrixTaskId)}`, { method: "DELETE" });
  setFeedback(`\u53c2\u6570\u7ec4\u5408\u4efb\u52a1\u5df2\u5220\u9664\uff1a${currentParameterMatrixTaskId}`, "success");
  currentParameterMatrixTaskId = "";
  $("#strategy-matrix-output").textContent = "\u5c1a\u672a\u521b\u5efa\u53c2\u6570\u7ec4\u5408\u4efb\u52a1";
}
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
  const dimensions = normalized?.dimensions || [];
  if (!dimensions.length) { $("#report-radar").innerHTML = '<div class="empty-cell">当前 Run 缺少可用的 7 维评估证据，不使用演示值补齐。</div>'; $("#report-dimension-grid").innerHTML = ""; $("#report-score-summary").textContent = "证据不足"; return; }
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
function renderTable(rows, columns) { return '<div class="table-wrap"><table><thead><tr>' + columns.map((c) => '<th>' + c.label + '</th>').join("") + '</tr></thead><tbody>' + ((rows || []).map((row) => '<tr>' + columns.map((c) => '<td class="' + financialToneForLabel(c.label, row[c.key]) + '">' + (row[c.key] ?? "") + '</td>').join("") + '</tr>').join("") || '<tr><td colspan="' + columns.length + '" class="empty-cell">暂无数据</td></tr>') + '</tbody></table></div>'; }function configureReportingWorkspace() {
  bindModeReportWorkspace();
  const aiPanel = $("#report-ai-workflow-summary")?.closest(".panel"); if (aiPanel) aiPanel.id = "report-ai-workflow-panel";
  if (aiPanel && !$("#report-ai-workflow-delete")) { const button=document.createElement("button"); button.id="report-ai-workflow-delete"; button.className="danger-button"; button.type="button"; button.textContent="\u5220\u9664\u5f53\u524d\u590d\u76d8"; aiPanel.querySelector(".panel-header")?.append(button); button.addEventListener("click", deleteCurrentAIWorkflow); }
  const packagePanel = $("#report-package-list")?.closest(".panel"); if (packagePanel) packagePanel.id = "report-package-panel";
  if (packagePanel && !$("#report-package-delete")) { const button=document.createElement("button"); button.id="report-package-delete"; button.className="danger-button"; button.type="button"; button.textContent="\u5220\u9664\u5f53\u524d\u62a5\u544a\u5305"; button.disabled=true; packagePanel.querySelector(".panel-header")?.append(button); button.addEventListener("click", deleteCurrentReportPackage); }
  // 阶段 75：管理入口改为页面导航，不再用页内锚点混入报告正文。
}
async function deleteCurrentAIWorkflow() {
  if (!currentReportWorkflowId || !window.confirm("\u786e\u8ba4\u5220\u9664\u5f53\u524d AI \u590d\u76d8\uff1f\u5220\u9664\u540e\u4ecd\u4fdd\u7559\u5ba1\u8ba1\u8bb0\u5f55\u3002")) return;
  await requestJson(`/api/reporting/ai-workflows/${encodeURIComponent(currentReportWorkflowId)}`, { method: "DELETE" });
  currentReportWorkflowId = ""; const button=$("#report-ai-workflow-delete"); if(button) button.disabled=true; setFeedback("AI \u590d\u76d8\u5df2\u5220\u9664", "success");
}
async function deleteCurrentReportPackage() {
  if (!selectedReportPackageId || !window.confirm("\u786e\u8ba4\u5220\u9664\u5f53\u524d\u7814\u7a76\u62a5\u544a\u5305\uff1f\u5220\u9664\u540e\u4ecd\u4fdd\u7559\u5ba1\u8ba1\u8bb0\u5f55\u3002")) return;
  await requestJson(`/api/reporting/report-packages/${encodeURIComponent(selectedReportPackageId)}`, { method: "DELETE" });
  selectedReportPackageId = ""; const button=$("#report-package-delete"); if(button) button.disabled=true; await loadReportPackages(currentReportRunId); await loadReportPackageDirectory(); setFeedback("\u7814\u7a76\u62a5\u544a\u5305\u5df2\u5220\u9664", "success");
}

function renderReportAIWorkflow(replay) {
  currentReportWorkflowId = replay?.workflow_id || "";
  const deleteButton = $("#report-ai-workflow-delete"); if (deleteButton) deleteButton.disabled = !currentReportWorkflowId;
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
    document.querySelectorAll("[data-report-package]").forEach((item) => item.classList.toggle("is-selected", item === card));
    const deleteButton = $("#report-package-delete"); if (deleteButton) deleteButton.disabled = false;
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
      document.querySelectorAll("[data-report-package-directory]").forEach((item) => item.classList.toggle("is-selected", item === card));
      const deleteButton = $("#report-package-delete"); if (deleteButton) deleteButton.disabled = false;
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
function renderReturnDistributionHistogram(histogram = []) {
  const labels = ["\u8dcc\u505c", "-8%-", "-8~-6%", "-6~-4%", "-4~-2%", "-2~0%", "0~2%", "2~4%", "4~6%", "6~8%", "8%+", "\u6da8\u505c"];
  const counts = labels.map((label, index) => Number(histogram[index]?.count ?? histogram.find((row) => row.bucket === label)?.count ?? 0));
  const max = Math.max(...counts, 1);
  return `<div class="return-distribution-chart"><div class="return-y-axis"><span>${max}</span><span>${Math.round(max / 2)}</span><span>0</span></div><div class="return-chart-body"><div class="return-bars">${counts.map((count, index) => `<div class="return-bar" title="${labels[index]}：${count} 只"><strong style="height:${Math.max(count ? 4 : 0, count / max * 100)}%">${count || ""}</strong><span>${labels[index]}</span></div>`).join("")}</div><div class="return-x-axis">\u6536\u76ca\u6da8\u5e45\u533a\u95f4</div></div></div>`;
}
function sortIndustryRows(rows = []) {
  if (currentIndustrySortMode === "default") return rows;
  return [...rows].sort((a, b) => ((Number(a.mean) || 0) - (Number(b.mean) || 0)) * (currentIndustrySortMode === "asc" ? 1 : -1));
}

function renderModeReportContext(report = {}) {
  const target = $("#mode-report-context");
  if (!target) return;
  const boundary = report.semantic_boundary || {};
  const governance = report.credibility || report.professional_report?.advanced_analysis?.report_governance || {};
  const credibility = $("#mode-report-credibility");
  if (credibility) credibility.innerHTML = `<strong>历史回测证据</strong> · ${escapeHtml(governance.credibility_label || governance.evidence_level || "simulation_only")} · 市场冲击：${escapeHtml(governance.market_impact_model || "未建模")} · 模拟盘/实盘：${escapeHtml(governance.paper_or_live_validation || "未验证")}；不构成投资建议。`;  target.innerHTML = `<strong>${report.report_mode === "shared_portfolio" ? "投资组合回测报告" : "独立账户批量回测双层报告"}</strong><span>任务 ${escapeHtml(report.task_id || "-")}</span><span>版本 ${escapeHtml(report.report_version || "-")}</span><span>${escapeHtml(boundary.account_scope || report.report_contract?.scope || "-")}</span>`;
}
function configureModeReportTabs(mode) {
  const tabs = $("#mode-report-tabs");
  if (!tabs) return;
  tabs.hidden = mode !== "independent-screening";
  tabs.querySelectorAll("[data-mode-report-tab]").forEach((button) => button.classList.toggle("is-selected", button.dataset.modeReportTab === currentModeReportTab));
  const toolbar = $("#independent-report-run-toolbar");
  if (toolbar) toolbar.hidden = mode !== "independent-screening" || currentModeReportTab !== "single_run_evaluation";
}
function renderIndependentRunOptions(query = "") {
  const select = $("#independent-report-run-select");
  if (!select) return;
  const normalized = String(query || "").trim().toLowerCase();
  const rows = currentModeReportRunIndex.filter((item) => !normalized || `${item.symbol || ""} ${item.name || ""} ${item.run_id || ""}`.toLowerCase().includes(normalized));
  const selectedRunId = currentModeReportRunIndex[currentModeReportSelectedIndex]?.run_id || "";
  select.innerHTML = rows.map((item) => `<option value="${escapeHtml(item.run_id)}" ${item.run_id === selectedRunId ? "selected" : ""}>${escapeHtml(item.symbol || "-")} · ${escapeHtml(item.name || "-")}</option>`).join("");
}
function renderIndependentTaskStatistics(report = {}) {
  const modernTarget = $("#mode-report-content");
  if (modernTarget && window.ReportUI?.renderBatchAnalysis) {
    window.ReportUI.renderBatchAnalysis(
      modernTarget,
      {
        mode: "independent",
        task_id: report.task_id,
        name: report.title || "独立账户批量回测报告",
        status: report.status,
      },
      report,
    );
    $("#mode-report-output").textContent = JSON.stringify({
      methodology: report.methodology,
      data_quality_notes: report.data_quality_notes,
      report_contract: report.report_contract,
    }, null, 2);
    return;
  }
  const scope = report.sample_scope || {};
  const distribution = report.distribution || {};
  const coverage = report.classification_coverage || {};
  const factor = report.factor_analysis || {};
  const robustness = report.robustness_analysis || {};
  $("#mode-report-radar").hidden = true;
  renderSummaryGrid($("#mode-report-summary"), [
    { label: "任务状态", value: report.status || "unknown" },
    { label: "股票池", value: scope.universe_count ?? 0 },
    { label: "实际建仓", value: scope.entered_count ?? 0 },
    { label: "正收益占比", value: distribution.positive_probability == null ? "-" : formatPercent(distribution.positive_probability) },
    { label: "收益中位数", value: distribution.median == null ? "-" : formatPercent(distribution.median) },
    { label: "VaR 95%", value: distribution.var_95 == null ? "-" : formatPercent(distribution.var_95) },
    { label: "稳健性", value: robustness.status || "unknown" },
  ]);
  const histogramHtml = renderReturnDistributionHistogram(distribution.histogram || []);
  const groupSections = Object.entries(report.group_comparisons || {}).map(([dimension, rows]) => { const sortedRows = dimension === "industry" ? sortIndustryRows(rows || []) : (rows || []); const sortButton = dimension === "industry" ? `<button type="button" id="industry-sort-toggle">行业排序：${currentIndustrySortMode === "default" ? "默认" : currentIndustrySortMode === "asc" ? "正序" : "倒序"}</button>` : ""; return `<h4>${{market:"市场比较",board:"上市板块比较",entry_period:"建仓时段比较",industry:"历史行业比较",concept:"历史概念比较"}[dimension] || dimension}</h4>${sortButton}${renderTable(sortedRows, [{key:"category",label:"分类"},{key:"sample_size",label:"样本"},{key:"mean",label:"平均收益"},{key:"median",label:"中位数"},{key:"stddev",label:"标准差"},{key:"positive_probability",label:"正收益概率"}])}`; }).join("");
  const factorRegistry = renderTable(factor.factor_registry || [], [{key:"factor",label:"特征"},{key:"kind",label:"类型"},{key:"status",label:"数据状态"},{key:"as_of",label:"历史时点"},{key:"required_asset",label:"所需数据资产"}]);
  const relationships = renderTable(factor.numeric_relationships || [], [{key:"label",label:"绩效特征"},{key:"sample_size",label:"样本"},{key:"spearman",label:"Spearman"},{key:"interpretation",label:"解释边界"}]);
  const categorical = renderTable(factor.categorical_effects || [], [{key:"factor",label:"分类特征"},{key:"category_count",label:"分组数"},{key:"best_category",label:"最高收益组"},{key:"worst_category",label:"最低收益组"},{key:"mean_spread",label:"均值差"},{key:"status",label:"状态"}]);
  $("#mode-report-content").innerHTML = `<section class="mode-report-section"><h4>建仓股票收益分布</h4>${histogramHtml}</section><section class="mode-report-section"><h4>可观测特征注册表</h4><p>${escapeHtml(factor.causality_warning || "")}</p>${factorRegistry}</section><section class="mode-report-section"><h4>绩效特征与总收益关系</h4>${relationships}</section><section class="mode-report-section"><h4>分类特征收益差异</h4>${categorical}</section>${groupSections}<section class="mode-report-section"><h4>稳健性与分类覆盖</h4>${renderTable([{...robustness}], [{key:"sample_size",label:"样本"},{key:"mean",label:"均值"},{key:"median",label:"中位数"},{key:"trimmed_mean",label:"截尾均值"},{key:"conclusion_stable",label:"结论稳定"}])}${renderTable(Object.entries(coverage).map(([dimension, value]) => ({dimension,...value})),[{key:"dimension",label:"维度"},{key:"covered_count",label:"已覆盖"},{key:"missing_count",label:"缺失"},{key:"coverage_ratio",label:"覆盖率"}])}</section>`;
  $("#industry-sort-toggle")?.addEventListener("click", () => { currentIndustrySortMode = currentIndustrySortMode === "default" ? "asc" : currentIndustrySortMode === "asc" ? "desc" : "default"; renderIndependentTaskStatistics(currentIndependentModeReport || report); });
  $("#mode-report-output").textContent = JSON.stringify({ methodology: report.methodology, data_quality_notes: report.data_quality_notes, report_contract: report.report_contract }, null, 2);
}
function renderIndependentModeReport(report = {}) {
  currentIndependentModeReport = report;
  currentModeReportTaskId = report.task_id || "";
  currentModeReportRunIndex = report.run_index || [];
  currentModeReportSelectedIndex = 0;
  currentModeReportTab = "task_statistics";
  renderModeReportContext(report);
  renderIndependentRunOptions();
  configureModeReportTabs("independent-screening");
  renderIndependentTaskStatistics(report);
}
function renderScopedSevenDimension(target, professional = {}, detail = {}) {
  const normalized = normalizeEvaluationReport(professional);
  const dimensions = normalized?.dimensions || [];
  if (!dimensions.length) {
    target.innerHTML = '<div class="empty-cell">当前 Run 缺少可用的 7 维评估证据，不使用演示值补齐。</div>';
    return;
  }
  const evidence = professional.evidence_quality || {};
  target.innerHTML = `<div class="mode-evidence-banner">证据质量：<strong>${escapeHtml(evidence.grade || "unknown")}</strong>；报告版本 ${escapeHtml(professional.report_version || "-")}；无演示值回退</div><div class="dimension-grid">${dimensions.map((item) => `<article class="dimension-card"><div class="dimension-title"><h4>${item.title}</h4><span class="score-tag ${item.level.cls}">${item.level.text} ${item.score}</span></div><div class="dimension-metrics">${item.metrics.map(([label,value]) => `<div class="dimension-metric"><span>${label}</span><strong>${value}</strong></div>`).join("")}</div><div class="mini-chart">${item.chart}</div></article>`).join("")}</div><h4>交易明细</h4>${renderTable(detail.trades || [], [{key:"trade_time",label:"时间"},{key:"order_book_id",label:"标的"},{key:"side",label:"方向"},{key:"price",label:"价格"},{key:"quantity",label:"数量"}])}`;
}
async function loadIndependentModeSingleRun(runId = "") {
  const selected = currentModeReportRunIndex.find((item) => item.run_id === runId) || currentModeReportRunIndex[currentModeReportSelectedIndex];
  if (!selected) {
    $("#mode-report-content").innerHTML = '<div class="empty-cell">该任务没有可切换的实际建仓股票。</div>';
    return null;
  }
  currentModeReportSelectedIndex = Math.max(0, currentModeReportRunIndex.findIndex((item) => item.run_id === selected.run_id));
  renderIndependentRunOptions($("#independent-report-run-search")?.value || "");
  const payload = await requestJson(`/api/reporting/backtest-modes/independent-screening/${encodeURIComponent(currentModeReportTaskId)}/runs/${encodeURIComponent(selected.run_id)}`);
  const report = payload.report || {};
  const professional = report.professional_report || {};
  const detail = report.run_detail || {};
  renderSummaryGrid($("#mode-report-summary"), [
    {label:"股票",value:`${report.symbol || "-"} · ${report.name || "-"}`},
    {label:"Run",value:shortTechnicalId(report.run_id)},
    {label:"状态",value:report.status || "unknown"},
    {label:"综合评分",value:professional.average_score ?? "N/A"},
    {label:"证据质量",value:professional.evidence_quality?.grade || "unknown"},
  ]);
  const normalized = normalizeEvaluationReport(professional);
  const radar = $("#mode-report-radar");
  radar.hidden = !(normalized?.dimensions || []).length;
  if (!radar.hidden) renderRadar(radar, normalized.dimensions);
  renderScopedSevenDimension($("#mode-report-content"), professional, detail);
  $("#mode-report-output").textContent = JSON.stringify({ semantic_boundary: report.semantic_boundary, navigation: report.navigation, data_quality_notes: professional.data_quality_notes }, null, 2);
  return report;
}
function setModeReportTab(tab) {
  if (!currentIndependentModeReport) return;
  currentModeReportTab = tab;
  configureModeReportTabs("independent-screening");
  if (tab === "task_statistics") renderIndependentTaskStatistics(currentIndependentModeReport);
  else loadIndependentModeSingleRun().catch((error) => setFeedback(error.message, "error"));
}
function bindModeReportWorkspace() {
  const tabs = $("#mode-report-tabs");
  if (!tabs || tabs.dataset.bound === "true") return;
  tabs.dataset.bound = "true";
  tabs.querySelectorAll("[data-mode-report-tab]").forEach((button) => button.addEventListener("click", () => setModeReportTab(button.dataset.modeReportTab)));
  $("#independent-report-run-select")?.addEventListener("change", (event) => loadIndependentModeSingleRun(event.currentTarget.value).catch((error) => setFeedback(error.message, "error")));
  $("#independent-report-run-search")?.addEventListener("input", (event) => renderIndependentRunOptions(event.currentTarget.value));
  $("#independent-report-run-prev")?.addEventListener("click", () => { currentModeReportSelectedIndex = Math.max(0, currentModeReportSelectedIndex - 1); loadIndependentModeSingleRun().catch((error) => setFeedback(error.message, "error")); });
  $("#independent-report-run-next")?.addEventListener("click", () => { currentModeReportSelectedIndex = Math.min(currentModeReportRunIndex.length - 1, currentModeReportSelectedIndex + 1); loadIndependentModeSingleRun().catch((error) => setFeedback(error.message, "error")); });
}
function renderSharedModeReport(report = {}) {
  currentIndependentModeReport = null;
  currentModeReportTab = "portfolio_evaluation";
  renderModeReportContext(report);
  configureModeReportTabs("shared-portfolio");
  const professional = report.professional_report || {};
  const detail = report.run_detail || {};
  const gate = report.data_quality_gate || {};
  renderSummaryGrid($("#mode-report-summary"), [
    {label:"任务状态",value:report.status || "unknown"},
    {label:"Run",value:shortTechnicalId(report.run_id)},
    {label:"综合评分",value:gate.score_allowed ? (professional.average_score ?? "N/A") : "N/A"},
    {label:"证据门禁",value:gate.status || "unavailable"},
    {label:"账户语义",value:"单一共享资金账户"},
  ]);
  const normalized = normalizeEvaluationReport(professional);
  const radar = $("#mode-report-radar");
  radar.hidden = !(normalized?.dimensions || []).length;
  if (!radar.hidden) renderRadar(radar, normalized.dimensions);
  renderScopedSevenDimension($("#mode-report-content"), professional, detail);
  $("#mode-report-output").textContent = JSON.stringify({ report_contract: report.report_contract, portfolio_sections: report.portfolio_sections, data_quality_gate: gate, semantic_boundary: report.semantic_boundary }, null, 2);
}

async function loadBacktestModeReport(event) {
  if (event) event.preventDefault();
  bindModeReportWorkspace();
  const form = $("#mode-report-form");
  const values = Object.fromEntries(new FormData(form).entries());
  if (!values.task_id) throw new Error("请输入回测任务 ID");
  const payload = await requestJson(`/api/reporting/backtest-modes/${encodeURIComponent(values.mode)}/${encodeURIComponent(values.task_id)}`);
  const report = payload.report || {};
  if (values.mode === "shared-portfolio") {
    renderSharedModeReport(report);
    if (report.run_id && report.status === "completed") {
      try {
        await loadReports(report.run_id, report.run_id.replace(/-shared-portfolio$/, ""));
      } catch (error) {
        setFeedback(`投资组合回测主报告已生成；附属报告暂不可用：${error.message}`, "error");
        return report;
      }
    }
  } else {
    renderIndependentModeReport(report);
  }
  document.body.classList.add("mode-report-active");
  updateStage75Url({ page: "reporting", mode: values.mode, task: values.task_id });
  setFeedback(`双模式报告已生成：${values.task_id}`, "success");
  return report;
}

async function loadReports(runId = "phase1-demo-run-001", experimentId = "phase1-batch-001") {
  configureReportingWorkspace();
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
    document.querySelectorAll("[data-ai-workflow]").forEach((item) => item.classList.toggle("is-selected", item === card));
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
  renderRqalphaRuntimeConfig(cfg);
  $("#config-output").textContent = JSON.stringify({ ai_workflow: cfg.runtime_settings?.ai_workflow, rqalpha_runtime: cfg.runtime_settings?.rqalpha_runtime, cache_policy: cfg.cache_policy, report_templates: cfg.report_templates, profiles: profiles.profiles, llm_provider_status: cfg.llm_provider_status, rqalpha_runtime_status: cfg.rqalpha_runtime_status, security_notes: cfg.security_notes }, null, 2);
  const draftEditor = $("#config-draft-editor");
  if (draftEditor && !draftEditor.matches(":focus")) draftEditor.value = JSON.stringify(cfg.runtime_settings || {}, null, 2);
  return { status, profiles };
}
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
// 阶段 75：PC 量化工作台、内嵌结果、Run 对比与报告管理信息架构。
function updateStage75Url(patch = {}, replace = true) {
  const params = new URLSearchParams(window.location.search);
  Object.entries(patch).forEach(([key, value]) => {
    if (value === "" || value == null || value === false) params.delete(key);
    else params.set(key, String(value));
  });
  const url = `${window.location.pathname}?${params.toString()}`;
  window.history[replace ? "replaceState" : "pushState"]({}, "", url);
}

function stage75RunLabel(run = {}) {
  const date = String(run.created_at || run.started_at || "").replace("T", " ").slice(0, 16) || "时间未知";
  const strategy = run.strategy_name || run.strategy_id || "未命名策略";
  const universe = run.universe || run.symbol || run.extra_config?.symbol || "组合/股票池";
  const modeLabel={single:"单品种测试","independent-single":"独立账户批量回测单股","shared-portfolio":"投资组合回测"}[stage76RunMode(run)] || "回测";
  return `${modeLabel} · ${strategy} · ${universe} · ${run.start_date || "-"}~${run.end_date || "-"} · ${date}`;
}

function configureStage75Shell() {
  const workspace = document.querySelector("main.workspace");
  if (workspace && !$("#page-report-management")) {
    const section = document.createElement("section");
    section.id = "page-report-management";
    section.className = "page-section";
    section.innerHTML = '<div class="section-grid" id="report-management-grid"><section class="panel panel-wide report-management-intro"><div class="panel-header"><div><h3>报告管理</h3><p>集中管理研究报告包、归档目录与报告快照；阅读和 Run 对比仍在报告中心完成。</p></div></div><div class="workspace-callout">此处只负责报告资产生命周期，不展示回测诊断正文。</div></section></div>';
    workspace.insertBefore(section, $("#page-config"));
  }

  const header = $("#backtest-workspace-header");
  header?.querySelector(".backtest-workflow")?.setAttribute("hidden", "");
  const tabs = header?.querySelector(".backtest-view-tabs");
  if (tabs) {
    tabs.querySelector('[data-backtest-view-target="overview"]')?.setAttribute("hidden", "");
    tabs.querySelector('[data-backtest-view-target="results"]')?.setAttribute("hidden", "");
    const order = ["strategy", "single", "independent", "portfolio"];
    order.forEach((name) => { const button=tabs.querySelector(`[data-backtest-view-target="${name}"]`); if(button) tabs.append(button); });
    if (!tabs.querySelector('[data-backtest-view-target="research"]')) {
      const research = document.createElement("button");
      research.type = "button";
      research.className = "backtest-view-tab";
      research.dataset.backtestViewTarget = "research";
      research.textContent = "研究实验";
      tabs.append(research);
    }
  }
  document.querySelector('[data-backtest-view="overview"]')?.setAttribute("hidden", "");

  if (header && !$("#backtest-common-config")) {
    const common = document.createElement("section");
    common.id = "backtest-common-config";
    common.className = "backtest-common-config";
    common.innerHTML = '<div class="common-config-title"><div><strong>公共回测参数</strong><span>切换模式时保留，应用后同步到当前表单</span></div><button type="button" id="backtest-common-apply">应用到当前模式</button></div><div class="common-config-fields"><label><span>策略</span><select id="backtest-common-strategy"></select></label><label><span>开始日期</span><input id="backtest-common-start" type="date"></label><label><span>结束日期</span><input id="backtest-common-end" type="date"></label><label><span>复权</span><select id="backtest-common-adjustment"><option value="qfq">前复权</option><option value="raw">不复权</option><option value="hfq">后复权</option></select></label><label><span>初始资金</span><input id="backtest-common-cash" type="number" min="10000" value="1000000"></label></div>';
    header.append(common);
  }

  const strategyLibraryPanel = $("#strategy-library")?.closest(".backtest-view-panel");
  const strategyEditorPanel = $("#strategy-editor")?.closest(".backtest-view-panel");
  if (strategyLibraryPanel && strategyEditorPanel && !$("#strategy-pc-workbench")) {
    const shell = document.createElement("section");
    shell.id = "strategy-pc-workbench";
    shell.className = "strategy-pc-workbench backtest-view-panel";
    shell.dataset.backtestView = "strategy";
    strategyLibraryPanel.parentElement.insertBefore(shell, strategyLibraryPanel);
    strategyLibraryPanel.removeAttribute("data-backtest-view");
    strategyEditorPanel.removeAttribute("data-backtest-view");
    strategyLibraryPanel.classList.remove("panel-wide", "backtest-view-panel");
    strategyEditorPanel.classList.remove("panel-wide", "backtest-view-panel");
    strategyLibraryPanel.classList.add("strategy-pane", "strategy-list-pane");
    strategyEditorPanel.classList.add("strategy-pane", "strategy-editor-pane");
    const inspector = document.createElement("aside");
    inspector.id = "strategy-inspector-pane";
    inspector.className = "panel strategy-pane strategy-inspector-pane";
    inspector.innerHTML = '<div class="panel-header"><div><h3>校验与版本</h3><p>选中策略的校验结果、元数据和版本历史。</p></div></div>';
    [$("#strategy-editor-meta"), $("#strategy-validation-output"), $("#strategy-version-history")].filter(Boolean).forEach((node) => inspector.append(node));
    shell.append(strategyLibraryPanel, strategyEditorPanel, inspector);
  }

  const researchAnchors = [$("#strategy-research-list")?.closest(".backtest-view-panel"), $("#backtest-experiment-index-list")?.closest(".backtest-view-panel")].filter(Boolean);
  researchAnchors.forEach((panel) => { panel.dataset.backtestView = "research"; });

  const resultPanel = $("#backtest-result-panel-summary")?.closest(".backtest-view-panel");
  if (resultPanel && !resultPanel.classList.contains("stage75-result-dock")) {
    resultPanel.removeAttribute("data-backtest-view");
    resultPanel.classList.remove("backtest-view-panel", "is-active");
    resultPanel.classList.add("stage75-result-dock");
    resultPanel.hidden = true;
    const originalHeader = resultPanel.querySelector(".panel-header");
    originalHeader?.classList.add("result-dock-header");
    if (originalHeader) originalHeader.innerHTML = '<div><h3>策略回测分析报告</h3><p>分析结论与交易、持仓、账户证据在同一报告中查看。</p></div><div class="button-row"><button type="button" id="stage75-result-close">收起</button></div>';
  }

  ["screening-task-form", "portfolio-task-form"].forEach((id) => {
    const form = $("#" + id);
    if (!form || form.querySelector('[data-create-and-run]')) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary-action";
    button.dataset.createAndRun = id.startsWith("screening") ? "independent" : "portfolio";
    button.textContent = "创建并运行";
    const submit = form.querySelector('button[type="submit"]');
    submit?.after(button);
  });

  const reportingGrid = $("#page-reporting .section-grid");
  if (reportingGrid && !$("#stage75-report-compare")) {
    const compare = document.createElement("section");
    compare.id = "stage75-report-compare";
    compare.className = "panel panel-wide stage75-report-compare";
    compare.innerHTML = '<div class="panel-header"><div><h3>Run 对比工作台</h3><p>按策略、标的和日期选择，无需记忆 Run ID；最多叠加 4 个 Run。</p></div><button type="button" id="stage75-compare-refresh">刷新 Run</button></div><div class="run-picker"><label><span>搜索 Run</span><input id="stage75-run-search" type="search" placeholder="策略、股票、日期"></label><label><span>可选 Run</span><select id="stage75-run-picker"></select></label><button type="button" id="stage75-compare-add">添加对比</button></div><div id="stage75-compare-compatibility" class="inline-status">请选择 2—4 个 Run</div><div id="stage75-comparison-tray" class="comparison-tray"></div><div class="comparison-chart-grid"><section><h4>净值曲线叠加</h4><div id="stage75-equity-overlay" class="series-overlay"></div></section><section><h4>回撤曲线叠加</h4><div id="stage75-drawdown-overlay" class="series-overlay"></div></section></div><div id="stage75-metrics-comparison" class="table-wrap"></div>';
    reportingGrid.insertBefore(compare, reportingGrid.children[1] || null);
  }
  document.querySelectorAll("#page-reporting .panel").forEach((panel) => {
    if (panel.id !== "stage75-report-compare" && !panel.contains($("#mode-report-form")) && !panel.classList.contains("report-cover")) panel.classList.add("legacy-report-section");
  });
}

function configureStage75Relocations() {
  const aiGrid = $("#page-ai .section-grid");
  const aiPanel = $("#report-ai-workflow-panel");
  if (aiGrid && aiPanel) {
    aiPanel.classList.add("ai-linked-replay-panel");
    aiPanel.querySelector("h3").textContent = "回测联动复盘";
    aiGrid.append(aiPanel);
  }
  const managementGrid = $("#report-management-grid");
  [$("#report-package-panel"), $("#report-package-directory-list")?.closest(".panel"), $("#report-snapshot-list")?.closest(".panel")].filter(Boolean).forEach((panel) => managementGrid?.append(panel));
  $("#reporting-section-nav")?.remove();
}

function refreshStage75StrategyOptions() {
  const select = $("#backtest-common-strategy");
  if (!select) return;
  const current = selectedStrategy?.strategy_id || select.value;
  select.innerHTML = strategyCatalog.map((strategy) => `<option value="${escapeHtml(strategy.strategy_id)}">${escapeHtml(strategy.name || strategy.strategy_id)} · ${escapeHtml(strategy.latest_version || "-")}</option>`).join("") || '<option value="">请先在策略库选择</option>';
  if (current && [...select.options].some((item) => item.value === current)) select.value = current;
}

function applyStage75CommonConfig() {
  const mode = currentBacktestView;
  const form = mode === "single" ? $("#backtest-run-form") : mode === "independent" ? $("#screening-task-form") : mode === "portfolio" ? $("#portfolio-task-form") : null;
  if (!form) { setFeedback("请切换到单品种测试、独立账户批量回测或投资组合回测后再应用", "error"); return; }
  const mapping = { start_date: $("#backtest-common-start")?.value, end_date: $("#backtest-common-end")?.value, adjustment: $("#backtest-common-adjustment")?.value, initial_cash: $("#backtest-common-cash")?.value };
  Object.entries(mapping).forEach(([name, value]) => { if (form.elements[name] && value) form.elements[name].value = value; });
  const strategy = strategyCatalog.find((item) => item.strategy_id === $("#backtest-common-strategy")?.value);
  if (strategy) selectStrategy(strategy).catch((error) => setFeedback(error.message, "error"));
  form.dispatchEvent(new Event("input", { bubbles: true }));
  saveStage75Draft(mode);
  setFeedback(`公共参数已应用到${mode === "single" ? "单品种测试" : mode === "independent" ? "独立账户批量回测" : "投资组合回测"}`, "success");
}

function saveStage75Draft(mode = currentBacktestView) {
  const form = mode === "single" ? $("#backtest-run-form") : mode === "independent" ? $("#screening-task-form") : mode === "portfolio" ? $("#portfolio-task-form") : null;
  if (!form || !["single", "independent", "portfolio"].includes(mode)) return;
  const values = Object.fromEntries(new FormData(form).entries());
  delete values.task_id; delete values.run_id;
  localStorage.setItem(`sleepercloudquant.backtest.draft.${mode}`, JSON.stringify(values));
}

function restoreStage75Draft(mode) {
  const form = mode === "single" ? $("#backtest-run-form") : mode === "independent" ? $("#screening-task-form") : mode === "portfolio" ? $("#portfolio-task-form") : null;
  if (!form) return;
  try {
    const values = JSON.parse(localStorage.getItem(`sleepercloudquant.backtest.draft.${mode}`) || "{}");
    Object.entries(values).forEach(([name, value]) => { if (form.elements[name] && value !== "") form.elements[name].value = value; });
  } catch (_) { /* 忽略旧版本无效草稿 */ }
}

function openStage75ResultDock(runId = "") {
  const panel = document.querySelector(".stage75-result-dock");
  if (!panel) return;
  panel.hidden = false;
  stage75ResultDockOpen = true;
  if (runId) updateStage75Url({ page: "backtest", view: currentBacktestView, run: runId });
  panel.focus({ preventScroll: true });
}

function closeStage75ResultDock() {
  const panel = document.querySelector(".stage75-result-dock");
  if (panel) panel.hidden = true;
  stage75ResultDockOpen = false;
  updateStage75Url({ run: "" });
}

function fillStage75TaskForm(form, config = {}) {
  if (!form) return;
  const windowConfig = config.date_window || {};
  const values = { ...config, start_date: config.start_date || windowConfig.start_date, end_date: config.end_date || windowConfig.end_date, symbols: Array.isArray(config.symbols) ? config.symbols.join(",") : config.symbols };
  Object.entries(values).forEach(([name, value]) => { if (form.elements[name] && value != null && typeof value !== "object") form.elements[name].value = value; });
  if (form.elements.task_id) form.elements.task_id.value = "";
  form.dispatchEvent(new Event("input", { bubbles: true }));
}

async function restoreClonedBacktestConfig(mode, config, universe = []) {
  const payload = await requestJson(`/api/backtest/strategies/${encodeURIComponent(config.strategy_id)}/versions`);
  const version = (payload.versions || []).find((item) => String(item.latest_version) === String(config.strategy_version));
  if (!version) throw new Error("原任务的策略版本不可用，无法克隆");
  await selectStrategy({ ...version, parameters: { ...(version.parameters || {}), ...(config.parameters || {}) } });
  const form = $(mode === "single" ? "#backtest-run-form" : mode === "independent" ? "#screening-task-form" : "#portfolio-task-form");
  const restored = { ...config, ...(config.extra_config?.rqalpha_local || {}) };
  if (mode !== "single" && universe.length) restored.symbols = universe.map((item) => item.rqalpha_symbol || item.symbol);
  fillStage75TaskForm(form, restored);
  const dates = config.date_window || config;
  const common = { start: dates.start_date, end: dates.end_date, adjustment: config.adjustment, cash: config.initial_cash ?? config.initial_cash_per_symbol };
  Object.entries(common).forEach(([key,value]) => { const input=$("#backtest-common-"+key); if(input && value != null) input.value=value; });
  if(form.elements.initial_cash && common.cash != null) form.elements.initial_cash.value=common.cash;
  activateStage76Workspace("create", mode);
  saveStage75Draft(mode);
}

async function cloneStage75SingleRun(runId) {
  if (!stage75RunCatalog.length) await loadStage75RunCatalog();
  const run=stage75RunCatalog.find((item)=>item.run_id===runId);
  if(!run) throw new Error("未找到单股 Run 配置");
  const payload=await requestJson(`/api/backtest/results/${encodeURIComponent(runId)}/panel`);
  const detail=payload.result||{}, snapshot=detail.parameter_snapshot||{}, account=(detail.accounts||[])[0];
  const extra=snapshot.extra_config||run.extra_config||{};
  const initialCash=account?.unit_net_value?account.total_value/account.unit_net_value:null;
  if(!initialCash || !extra.strategy_version) throw new Error("历史结果缺少资金或策略版本快照，无法可靠克隆");
  await restoreClonedBacktestConfig("single", {run_id:newTaskId("single"),strategy_name:run.strategy_name,strategy_id:run.strategy_id,strategy_version:extra.strategy_version,symbol:run.universe,benchmark:run.benchmark,date_window:{start_date:run.start_date,end_date:run.end_date},initial_cash:initialCash,adjustment:snapshot.parameters?.adjustment||extra.adjustment||"raw",parameters:snapshot.parameters||{},extra_config:extra});
  setFeedback("已克隆单股配置并生成新回测编号，请确认后运行", "success");
}
async function cloneStage75Task(mode, taskId) {
  const independent = mode === "independent";
  const resource = independent ? "independent-screening-tasks" : "shared-portfolio-tasks";
  const payload = await requestJson(`/api/backtest/${resource}/${encodeURIComponent(taskId)}`);
  const task = payload.task || {};
  await restoreClonedBacktestConfig(mode, task.config || {}, task.universe || []);
  setFeedback("已克隆任务配置，请确认范围后创建；不会自动启动", "success");
}

function decorateStage75TaskLists() {
  [["#single-run-history", "single", "singleHistoryRun"], ["#screening-task-list", "independent", "screeningTask"], ["#portfolio-task-list", "portfolio", "portfolioTask"]].forEach(([selector, mode, datasetKey]) => {
    const target = $(selector); if (!target) return;
    target.querySelectorAll(".compact-task-row").forEach((row) => {
      if (row.querySelector("[data-stage75-clone]")) return;
      const taskId = row.dataset[datasetKey]; if (!taskId) return;
      const actions = row.querySelector(".task-row-actions") || row;
      const button = document.createElement("button");
      button.type = "button"; button.dataset.stage75Clone = mode; button.dataset.taskId = taskId; button.textContent = "克隆此任务";
      button.addEventListener("click", (event) => { event.stopPropagation(); const action=mode === "single" ? cloneStage75SingleRun(taskId) : cloneStage75Task(mode, taskId); action.catch((error) => setFeedback(error.message, "error")); });
      actions.append(button);
    });
  });
}

async function createAndRunStage75(mode, button) {
  const independent = mode === "independent";
  const form = independent ? $("#screening-task-form") : $("#portfolio-task-form");
  const original = button.textContent;
  button.disabled = true; button.textContent = "创建中...";
  try {
    const createButton=form.querySelector('button[type="submit"]');
    const event = { preventDefault() {}, currentTarget: form, submitter: createButton };
    if (independent) { await createIndependentScreeningTask(event); button.textContent = "启动中..."; await runIndependentScreeningTask(); }
    else { await createSharedPortfolioTask(event); button.textContent = "启动中..."; await runSharedPortfolioTask(); }
    setFeedback(`${independent ? "独立账户批量回测" : "投资组合回测"}任务已创建并启动`, "success");
    setStage76ModeTaskState(mode,true,independent?currentScreeningTask:currentPortfolioTask);
  } finally { button.disabled = false; button.textContent = original; }
}

function stage75Series(result, key) {
  const rows = result?.[key] || result?.result?.[key] || [];
  return rows.map((row, index) => ({ label: row.snapshot_time || row.date || String(index + 1), value: Number(row.value ?? row.unit_net_value ?? row.drawdown) })).filter((row) => Number.isFinite(row.value));
}

function renderStage75Overlay(target, seriesList) {
  if (!target || !seriesList.length) { if(target) target.innerHTML='<div class="empty-cell">至少添加 2 个可用 Run</div>'; return; }
  const width=860, height=250, pad=34;
  const all=seriesList.flatMap((item)=>item.rows.map((row)=>row.value)); const min=Math.min(...all), max=Math.max(...all), span=max-min||1;
  const longest=Math.max(...seriesList.map((item)=>item.rows.length),1);
  const x=(i)=>pad+i/Math.max(longest-1,1)*(width-pad*2); const y=(v)=>pad+(max-v)/span*(height-pad*2);
  const lines=seriesList.map((item,index)=>`<polyline points="${item.rows.map((row,i)=>`${x(i)},${y(row.value)}`).join(" ")}" fill="none" stroke="${stage75ComparisonColors[index]}" stroke-width="2.5"/>`).join("");
  const legend=seriesList.map((item,index)=>`<span><i style="background:${stage75ComparisonColors[index]}"></i>${escapeHtml(item.label)}</span>`).join("");
  target.innerHTML=`<div class="overlay-legend">${legend}</div><svg viewBox="0 0 ${width} ${height}" role="img"><line x1="${pad}" x2="${width-pad}" y1="${height-pad}" y2="${height-pad}" class="grid-line"/>${lines}<text x="4" y="${pad}" class="axis-label">${max.toFixed(4)}</text><text x="4" y="${height-pad}" class="axis-label">${min.toFixed(4)}</text></svg>`;
}

async function loadStage75RunCatalog() {
  const payload = await requestJson("/api/backtest/runs");
  stage75RunCatalog = payload.runs || [];
  renderStage75RunPicker();
  return stage75RunCatalog;
}

function renderStage75RunPicker() {
  const picker=$("#stage75-run-picker"); if(!picker) return;
  const query=$("#stage75-run-search")?.value.trim().toLowerCase() || "";
  const rows=stage75RunCatalog.filter((run)=>!query || stage75RunLabel(run).toLowerCase().includes(query) || String(run.run_id).toLowerCase().includes(query));
  picker.innerHTML=rows.map((run)=>`<option value="${escapeHtml(run.run_id)}">${escapeHtml(stage75RunLabel(run))}</option>`).join("") || '<option value="">没有匹配的 Run</option>';
}

async function renderStage75Comparison() {
  const tray=$("#stage75-comparison-tray");
  tray.innerHTML=stage75ComparisonRuns.map((item,index)=>`<button type="button" data-remove-compare="${escapeHtml(item.run.run_id)}"><i style="background:${stage75ComparisonColors[index]}"></i>${escapeHtml(stage75RunLabel(item.run))}<span>×</span></button>`).join("") || '<div class="empty-cell">尚未添加 Run</div>';
  tray.querySelectorAll("[data-remove-compare]").forEach((button)=>button.addEventListener("click",()=>{stage75ComparisonRuns=stage75ComparisonRuns.filter((item)=>item.run.run_id!==button.dataset.removeCompare); renderStage75Comparison();}));
  const modes=new Set(stage75ComparisonRuns.map((item)=>item.run.extra_config?.mode || item.run.extra_config?.portfolio_mode || "single"));
  const versions=new Set(stage75ComparisonRuns.map((item)=>item.result?.summary?.data_version || item.result?.data_asset_trace?.asset?.data_version || "unknown"));
  const compatible=modes.size<=1;
  $("#stage75-compare-compatibility").className=`inline-status ${compatible ? "is-success" : "is-warning"}`;
  $("#stage75-compare-compatibility").textContent=stage75ComparisonRuns.length<2 ? "请选择 2—4 个 Run" : `${compatible ? "模式兼容" : "模式不同，仅供观察"} · 数据版本 ${[...versions].join(" / ")}`;
  renderStage75Overlay($("#stage75-equity-overlay"),stage75ComparisonRuns.map((item)=>({label:stage75RunLabel(item.run),rows:stage75Series(item.result,"equity_curve")})).filter((item)=>item.rows.length));
  renderStage75Overlay($("#stage75-drawdown-overlay"),stage75ComparisonRuns.map((item)=>({label:stage75RunLabel(item.run),rows:stage75Series(item.result,"drawdown_curve")})).filter((item)=>item.rows.length));
  const metricKeys=["total_returns","annualized_returns","max_drawdown","sharpe","volatility"];
  $("#stage75-metrics-comparison").innerHTML=stage75ComparisonRuns.length ? `<table><thead><tr><th>指标</th>${stage75ComparisonRuns.map((item)=>`<th>${escapeHtml(stage75RunLabel(item.run))}</th>`).join("")}</tr></thead><tbody>${metricKeys.map((key)=>`<tr><th>${key}</th>${stage75ComparisonRuns.map((item)=>`<td class="${financialToneForLabel(key,item.result?.metrics?.[key] ?? item.result?.summary?.metrics?.[key])}">${item.result?.metrics?.[key] ?? item.result?.summary?.metrics?.[key] ?? "-"}</td>`).join("")}</tr>`).join("")}</tbody></table>` : "";
  updateStage75Url({ compare: stage75ComparisonRuns.map((item)=>item.run.run_id).join(",") });
}

async function addStage75ComparisonRun(runId) {
  if(!runId || stage75ComparisonRuns.some((item)=>item.run.run_id===runId)) return;
  if(stage75ComparisonRuns.length>=4) throw new Error("最多同时对比 4 个 Run");
  const run=stage75RunCatalog.find((item)=>item.run_id===runId) || {run_id:runId};
  const existingMode=stage75ComparisonRuns[0]?stage76RunMode(stage75ComparisonRuns[0].run):"";
  if(existingMode && stage76RunMode(run)!==existingMode) throw new Error("仅支持相同回测模式的 Run 对比");
  const payload=await requestJson(`/api/backtest/results/${encodeURIComponent(runId)}/panel`);
  const result=payload.result || payload.panel || payload;
  const firstVersion=stage75ComparisonRuns[0]?.result?.data_asset_trace?.asset?.data_version;
  const nextVersion=result?.data_asset_trace?.asset?.data_version;
  if(firstVersion && nextVersion && firstVersion!==nextVersion) throw new Error("数据版本不同，不能叠加为同口径对比");
  stage75ComparisonRuns.push({run,result});
  await renderStage75Comparison();
}

function bindStage75Events() {
  document.querySelectorAll("[data-stage75-page]").forEach((button)=>button.addEventListener("click",()=>activatePage(button.dataset.stage75Page)));
  $("#reporting-query-form")?.addEventListener("submit",()=>document.body.classList.remove("mode-report-active"));  $("#backtest-common-apply")?.addEventListener("click", applyStage75CommonConfig);
  $("#backtest-common-strategy")?.addEventListener("focus", refreshStage75StrategyOptions);
  [$("#backtest-run-form"),$("#screening-task-form"),$("#portfolio-task-form")].filter(Boolean).forEach((form)=>form.addEventListener("input",()=>saveStage75Draft(form.id==="backtest-run-form"?"single":form.id.startsWith("screening")?"independent":"portfolio")));
  document.querySelectorAll("[data-create-and-run]").forEach((button)=>button.addEventListener("click",()=>createAndRunStage75(button.dataset.createAndRun,button).catch((error)=>setFeedback(error.message,"error"))));
  $("#stage75-result-close")?.addEventListener("click",closeStage75ResultDock);
  $("#stage75-result-full-report")?.addEventListener("click",()=>openSelectedBacktestReport().catch((error)=>setFeedback(error.message,"error")));
  $("#stage75-run-search")?.addEventListener("input",renderStage75RunPicker);
  $("#stage75-compare-refresh")?.addEventListener("click",()=>loadStage75RunCatalog().then(()=>setFeedback("Run 列表已刷新","success")).catch((error)=>setFeedback(error.message,"error")));
  $("#stage75-compare-add")?.addEventListener("click",()=>addStage75ComparisonRun($("#stage75-run-picker")?.value).catch((error)=>setFeedback(error.message,"error")));
  const observer=new MutationObserver(decorateStage75TaskLists);
  [$("#single-run-history"),$("#screening-task-list"),$("#portfolio-task-list")].filter(Boolean).forEach((target)=>observer.observe(target,{childList:true,subtree:true}));
  decorateStage75TaskLists();
  const now=new Date(); const pad=(v)=>String(v).padStart(2,"0");
  $("#backtest-common-start").value=`${now.getFullYear()}-01-01`;
  $("#backtest-common-end").value=`${now.getFullYear()}-${pad(now.getMonth()+1)}-01`;
  refreshStage75StrategyOptions();
  loadStage75RunCatalog().catch(()=>{});
}
let stage76TaskCatalog = [];
let stage76SelectedTask = null;
let stage76TaskPollTimer = null;
let stage76Workspace = "strategy";
let stage76CurrentResult = null;
let stage76TaskPage = 1;
let stage76TaskPageSize = 20;
let stage76TaskTotal = 0;
let stage76TaskRequestSequence = 0;
let backtestResultSelectionSequence = 0;
let backtestTableRequestSequence = 0;
let stage76ActionSequence = 0;
let stage76ReportRequestSequence = 0;
function syncStage76CommonFields(mode=currentBacktestView) {
  const form=mode==="single"?$("#backtest-run-form"):mode==="independent"?$("#screening-task-form"):mode==="portfolio"?$("#portfolio-task-form"):null;
  if(!form)return;
  const mapping={start_date:$("#backtest-common-start")?.value,end_date:$("#backtest-common-end")?.value,adjustment:$("#backtest-common-adjustment")?.value,initial_cash:$("#backtest-common-cash")?.value};
  Object.entries(mapping).forEach(([name,value])=>{if(form.elements[name]&&value)form.elements[name].value=value;});
  form.dispatchEvent(new Event("input",{bubbles:true}));
}

function highlightStage76Python(source="") {
  const keywords=new Set("and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield".split(" "));
  const builtins=new Set("abs all any bool dict enumerate filter float int len list map max min print range reversed round set sorted str sum tuple type zip".split(" "));
  const pattern=/(#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b)/g;
  let result="", cursor=0;
  for(const match of source.matchAll(pattern)) {
    result+=escapeHtml(source.slice(cursor,match.index));
    const token=match[0], before=source.slice(0,match.index), after=source.slice(match.index+token.length);
    let type="";
    if(token.startsWith("#")) type="comment";
    else if(token.startsWith("\"")||token.startsWith("'")) type="string";
    else if(/^\d/.test(token)) type="number";
    else if(keywords.has(token)) type="keyword";
    else if(/\b(?:def|class)\s+$/.test(before)) type=before.trimEnd().endsWith("class")?"class":"function";
    else if(/^\s*\(/.test(after)) type=builtins.has(token)?"builtin":"function-call";
    else if(/\.\s*$/.test(before)) type="property";
    else if(/^[A-Z]\w*$/.test(token)) type="class";
    result+=type?`<span class="syntax-${type}">${escapeHtml(token)}</span>`:escapeHtml(token);
    cursor=match.index+token.length;
  }
  return result+escapeHtml(source.slice(cursor))+"\n";
}function renderStage76CodeHighlight() {
  const editor=$("#strategy-editor"), shell=editor?.closest(".stage76-code-editor-shell");
  if(!editor||!shell)return;
  const highlight=shell.querySelector(".stage76-code-highlight"), gutter=shell.querySelector(".stage76-code-gutter");
  if(highlight)highlight.innerHTML=highlightStage76Python(editor.value);
  if(gutter)gutter.textContent=Array.from({length:Math.max(1,editor.value.split("\n").length)},(_,index)=>String(index+1)).join("\n")+"\n";
  if(highlight){highlight.scrollTop=editor.scrollTop;highlight.scrollLeft=editor.scrollLeft;}
  if(gutter)gutter.scrollTop=editor.scrollTop;
}
function setStage76CodeTheme(theme) {
  const shell=$("#strategy-editor")?.closest(".stage76-code-editor-shell"), button=$("#stage76-code-theme");
  const normalized=theme==="dark"?"dark":"light";
  if(shell)shell.dataset.theme=normalized;
  if(button){button.textContent=normalized==="dark"?"浅色背景":"深色背景";button.setAttribute("aria-pressed",String(normalized==="dark"));}
  try{localStorage.setItem("sleepercloudquant-code-theme",normalized);}catch(_){ }
}
function configureStage76CodeEditor() {
  const editor=$("#strategy-editor"); if(!editor||editor.closest(".stage76-code-editor-shell"))return;
  const shell=document.createElement("div"); shell.className="stage76-code-editor-shell";
  const gutter=document.createElement("pre"); gutter.className="stage76-code-gutter"; gutter.setAttribute("aria-hidden","true");
  const stack=document.createElement("div"); stack.className="stage76-code-stack";
  const highlight=document.createElement("pre"); highlight.className="stage76-code-highlight"; highlight.setAttribute("aria-hidden","true");
  const resizeHandle=document.createElement("button"); resizeHandle.type="button"; resizeHandle.className="stage76-code-resize-handle"; resizeHandle.title="拖动以调整代码区高度"; resizeHandle.setAttribute("aria-label","调整代码区高度"); resizeHandle.textContent="⋰";
  editor.parentElement.insertBefore(shell,editor); shell.append(gutter,stack,resizeHandle); stack.append(highlight,editor); editor.classList.add("stage76-code-input");
  const setEditorHeight=(height)=>{shell.style.flex="0 0 auto";shell.style.height=`${Math.max(360,Math.min(1200,height))}px`;renderStage76CodeHighlight();};
  resizeHandle.addEventListener("pointerdown",(event)=>{event.preventDefault();const startY=event.clientY,startHeight=shell.getBoundingClientRect().height;resizeHandle.setPointerCapture?.(event.pointerId);const move=(moveEvent)=>setEditorHeight(startHeight+moveEvent.clientY-startY);const stop=()=>{window.removeEventListener("pointermove",move);window.removeEventListener("pointerup",stop);};window.addEventListener("pointermove",move);window.addEventListener("pointerup",stop,{once:true});});
  resizeHandle.addEventListener("keydown",(event)=>{if(event.key==="ArrowUp"||event.key==="ArrowDown"){event.preventDefault();setEditorHeight(shell.getBoundingClientRect().height+(event.key==="ArrowDown"?32:-32));}});
  resizeHandle.addEventListener("dblclick",()=>{shell.style.height="560px";shell.style.flex="0 0 auto";renderStage76CodeHighlight();});
  editor.addEventListener("input",renderStage76CodeHighlight);
  editor.addEventListener("scroll",()=>{highlight.scrollTop=editor.scrollTop;highlight.scrollLeft=editor.scrollLeft;gutter.scrollTop=editor.scrollTop;});
  let theme="light"; try{theme=localStorage.getItem("sleepercloudquant-code-theme")||"light";}catch(_){ }
  setStage76CodeTheme(theme); renderStage76CodeHighlight();
}
function setStage76ModeTaskState(mode,visible,task={}) {
  const state=document.querySelector(`[data-stage76-mode-state="${mode}"]`); if(!state)return;
  state.classList.toggle("has-task",Boolean(visible));
  const placeholder=state.querySelector(".stage76-task-state-placeholder"), content=state.querySelector(".stage76-task-state-content");
  if(placeholder)placeholder.hidden=Boolean(visible); if(content)content.hidden=!visible;
  if(mode==="single"&&visible){
    const summary=$("#stage76-single-task-summary");
    if(summary)renderSummaryGrid(summary,[{label:"任务编号",value:shortTechnicalId(task.task_id||task.run_id||"-")},{label:"状态",value:backtestStatusInfo(task.status||"ready").label},{label:"股票",value:task.symbol||task.config?.symbol||"-"},{label:"创建时间",value:formatTaskTimestamp(task.created_at)}]);
  }
  const completed=["completed","partial_completed","partial_failed"].includes(task.status);
  const canResult=Boolean(visible&&(task.capabilities?.can_view_result||completed));
  const canReport=Boolean(visible&&(task.capabilities?.can_view_report||completed));
  document.querySelectorAll(`[data-stage76-form-action][data-stage76-action-mode="${mode}"]`).forEach((button)=>{
    button.disabled=!(canResult||canReport);
  });
}

function configureStage76ModeForm(mode,form) {
  if(!form||form.classList.contains("stage76-mode-form"))return;
  form.classList.add("stage76-mode-form");
  const fields=document.createElement("div"); fields.className="stage76-form-fields";
  const actions=document.createElement("aside"); actions.className="stage76-form-actions"; actions.innerHTML='<div class="stage76-form-actions-title"><strong>任务操作</strong><span>完成参数编辑后，在此创建或执行任务</span></div>';
  Array.from(form.children).forEach((node)=>{(node.tagName==="BUTTON"?actions:fields).append(node);});
  actions.insertAdjacentHTML("beforeend", `<button type="button" data-stage76-form-action="analysis" data-stage76-action-mode="${mode}" disabled>分析报告</button>`);
  form.replaceChildren(fields,actions);
  ["strategy_name","start_date","end_date","adjustment","initial_cash"].forEach((name)=>{const label=form.elements[name]?.closest("label");if(label){label.hidden=true;label.classList.add("stage76-common-duplicate");}});
  const panel=form.closest("[data-backtest-view]"); if(panel)panel.classList.add("stage76-mode-panel");
  const legacyHeaderControl=mode==="single"?$("#single-run-status"):mode==="independent"?$("#screening-task-refresh"):$("#portfolio-task-refresh"); if(legacyHeaderControl)legacyHeaderControl.hidden=true;
  const state=document.createElement("section"); state.className="stage76-mode-task-state"; state.dataset.stage76ModeState=mode;
  state.innerHTML='<div class="stage76-task-state-placeholder"><strong>尚未创建当前任务</strong><span>任务创建后，这里将显示任务信息、状态和真实进度。</span></div><div class="stage76-task-state-content" hidden><div class="stage76-task-state-heading"><strong>当前任务</strong><span>状态和进度会随执行刷新</span></div></div>';
  const content=state.querySelector(".stage76-task-state-content");
  const selectors=mode==="single"?["#single-run-progress"]:mode==="independent"?["#screening-live-progress","#screening-progress","#screening-summary"]:["#portfolio-live-progress","#portfolio-task-progress","#portfolio-task-summary"];
  if(mode==="single"){const summary=document.createElement("div");summary.id="stage76-single-task-summary";summary.className="summary-grid";content.append(summary);}
  selectors.map((selector)=>$(selector)?.closest("details")||$(selector)).filter(Boolean).forEach((node)=>content.append(node));
  const preview=mode==="independent"?$("#screening-config-preview"):mode==="portfolio"?$("#portfolio-config-preview"):null;
  (preview||form).after(state);
  setStage76ModeTaskState(mode,false);
}
function currentStage76FormTask(mode) {
  const raw=mode==="single"?currentSingleTask:mode==="independent"?currentScreeningTask:currentPortfolioTask;
  if(!raw?.task_id)return null;
  const taskMode=mode==="single"?"single":mode==="independent"?"independent-screening":"shared-portfolio";
  const catalogTask=stage76TaskCatalog.find((task)=>task.task_id===raw.task_id&&task.mode===taskMode);
  if(catalogTask)return catalogTask;
  return taskMode==="single"?{...raw,mode:"single",mode_label:"单品种测试"}:nativeModeTask(raw,taskMode);
}
async function handleStage76FormTaskAction(mode,action) {
  const task=currentStage76FormTask(mode);
  if(!task)throw new Error("请先创建或选择当前模式任务");
  stage76SelectedTask=task;
  await handleStage76TaskAction(task,action);
}
function configureStage76InformationArchitecture() {
  const header = $("#backtest-workspace-header");
  if (!header) return;
  const oldTabs = header.querySelector(".backtest-view-tabs");
  const nav = $("#stage76-workspace-nav");
  if (!nav) throw new Error("策略与回测导航缺失");
  if (oldTabs) oldTabs.remove();
  const redundantHeader = header.querySelector(".panel-header");
  if (redundantHeader) redundantHeader.hidden = true;
  const contextSummary = $("#backtest-context-summary");
  if (contextSummary) contextSummary.hidden = true;
  const common = $("#backtest-common-config");
  if (common) { common.hidden = true; const note=common.querySelector(".common-config-title span"); if(note) note.textContent="公共参数是三种模式的唯一设置入口，自动同步到当前表单"; const apply=common.querySelector("#backtest-common-apply"); if(apply) apply.textContent="同步公共参数"; }
  const modeTabs = document.createElement("div");
  modeTabs.id = "stage76-create-mode-tabs";
  modeTabs.className = "stage76-create-mode-tabs";
  modeTabs.hidden = true;
  modeTabs.innerHTML = '<button type="button" data-stage76-mode="single">单品种测试</button><button type="button" data-stage76-mode="independent">独立账户批量回测</button><button type="button" data-stage76-mode="portfolio">投资组合回测</button>';
  common?.before(modeTabs);
  const singleForm = $("#backtest-run-form");
  if (singleForm) {
    if (!singleForm.elements.adjustment) { const input=document.createElement("input"); input.type="hidden"; input.name="adjustment"; input.value="qfq"; singleForm.append(input); }
    if (!singleForm.elements.initial_cash) { const input=document.createElement("input"); input.type="hidden"; input.name="initial_cash"; input.value="1000000"; singleForm.append(input); }
    const runInput=singleForm.elements.run_id;
    const runLabel=runInput?.closest("label")?.querySelector("span");
    if(runInput){ runInput.value=newTaskId("single-run"); runInput.readOnly=true; runInput.title="每次创建任务时自动生成新的唯一回测编号"; }
    if(runLabel) runLabel.textContent="回测编号（自动生成）";
    const submit=singleForm.querySelector('button[type="submit"]'); if(submit) submit.textContent="创建并执行";
    if (!$("#single-task-create-only")) { const only=document.createElement("button"); only.type="button"; only.id="single-task-create-only"; only.textContent="仅创建任务"; submit?.after(only); }
  }
  configureStage76ModeForm("single",$("#backtest-run-form"));
  configureStage76ModeForm("independent",$("#screening-task-form"));
  configureStage76ModeForm("portfolio",$("#portfolio-task-form"));
  [$("#single-run-history")?.closest(".history-section"), $("#screening-task-list"), $("#portfolio-task-list")].filter(Boolean).forEach((node)=>node.classList.add("stage76-legacy-history"));
  const screeningEnteredResults = $("#screening-entered-results");
  if (screeningEnteredResults) { screeningEnteredResults.hidden = true; screeningEnteredResults.replaceChildren(); }

  const strategyToolbar = $("#strategy-library")?.closest(".strategy-list-pane")?.querySelector(".strategy-library-toolbar");
  if (strategyToolbar && !$("#strategy-library-sort")) {
    const sortLabel = document.createElement("label");
    sortLabel.innerHTML = '<span>排序</span><select id="strategy-library-sort"><option value="name">名称</option><option value="category">分类</option><option value="versions">版本数</option></select>';
    strategyToolbar.insertBefore(sortLabel, $("#strategy-library-refresh"));
  }
  const strategyShell = $("#strategy-pc-workbench");
  const listPane = strategyShell?.querySelector(".strategy-list-pane");
  const editorPane = strategyShell?.querySelector(".strategy-editor-pane");
  const inspector = $("#strategy-inspector-pane");
  if (strategyShell && listPane && editorPane && inspector) {
    const editorMeta = $("#strategy-editor-meta");
    const stage76Validation = $("#strategy-validation-output");
    const versionHistory = $("#strategy-version-history");
    const editorHeader = editorPane.querySelector(".panel-header");
    const editorHeaderContent = editorHeader?.querySelector("div");
    if (editorMeta && editorHeaderContent) editorHeaderContent.append(editorMeta);
    inspector.className = "panel strategy-pane strategy-config-pane";
    inspector.replaceChildren();
    const fields = editorPane.querySelector(".strategy-editor-fields");
    const actions = editorPane.querySelector(".strategy-editor-actions");
    const parameterSection = $("#strategy-parameter-schema")?.closest(".strategy-editor-section");
    const legacyVersionSection = editorPane.querySelector(".stage76-code-guide")
      || [...editorPane.querySelectorAll(".strategy-editor-section")]
        .find((section) => section.querySelector(".subsection-header h4")?.textContent.trim() === "版本历史");
    [editorHeader, fields, actions, parameterSection].filter(Boolean).forEach((node) => inspector.append(node));
    const versionSelectorBlock = document.createElement("section");
    versionSelectorBlock.className = "strategy-editor-section stage76-version-selector";
    versionSelectorBlock.innerHTML = '<div class="subsection-header"><h4>策略版本</h4><span>切换只用于查看；保存代码会创建新版本</span></div><label><span>当前查看版本</span><select id="strategy-version-select"><option value="">请选择策略</option></select></label>';
    inspector.append(versionSelectorBlock);
    if (versionHistory) { versionHistory.hidden = true; versionSelectorBlock.append(versionHistory); }
    const guideBlock = legacyVersionSection || document.createElement("section");
    guideBlock.className = "strategy-editor-section stage76-code-guide";
    guideBlock.innerHTML = '<div class="subsection-header"><h4>策略代码编写指南</h4><span>先理解输入、输出和安全边界，再编写策略</span></div><ol><li><strong>入口函数</strong><code>generate_target_weights(bars, parameters)</code></li><li><strong>输入数据</strong><span><code>bars</code> 是按时间升序排列的 OHLC 字典列表；<code>parameters</code> 来自下方参数配置。</span></li><li><strong>输出结果</strong><span>返回与 <code>bars</code> 等长的目标仓位列表，取值建议在 0 到 1 之间。</span></li><li><strong>保存流程</strong><span>先点击“校验代码”，通过后再点击“保存新版本”。系统会记录版本和源码 SHA-256。</span></li></ol><pre class="code-block">def generate_target_weights(bars, parameters):\n    weights = [0.0] * len(bars)\n    # 在这里计算信号并设置目标仓位\n    return weights</pre><p class="stage76-code-guide-note">安全限制：禁止网络访问、文件读写、动态执行和未授权导入。</p>';
    if (!legacyVersionSection) editorPane.append(guideBlock);
    const sourceSection = $("#strategy-editor")?.closest(".strategy-editor-section");
    const validation = stage76Validation;
    const codeHeader = document.createElement("div");
    codeHeader.className = "panel-header stage76-code-header";
    codeHeader.innerHTML = '<div><h3>策略代码</h3><p>采用 Atom One Light / One Dark Pro 风格着色函数、关键字与数据；拖动右下角手柄调整高度。</p></div><div class="button-row"><button type="button" id="stage76-code-theme" aria-pressed="false">深色背景</button><button type="button" id="stage76-code-validate">校验代码</button></div>';
    editorPane.prepend(codeHeader);
    if (validation && sourceSection) sourceSection.before(validation);
    editorPane.classList.add("strategy-code-pane");
    configureStage76CodeEditor();
    const researchPanel = $("#strategy-research-list")?.closest(".panel");
    const secondaryActions = editorPane.querySelector(".secondary-actions");
    const scanOutput = $("#strategy-scan-output");
    const matrixOutput = $("#strategy-matrix-output");
    if (researchPanel && (secondaryActions || scanOutput || matrixOutput)) {
      const tools = document.createElement("section");
      tools.className = "strategy-editor-section stage76-research-tools";
      tools.innerHTML = '<div class="subsection-header"><h4>参数研究工具</h4><span>扫描、矩阵和快照从日常策略维护区分流</span></div>';
      [secondaryActions, scanOutput, matrixOutput].filter(Boolean).forEach((node) => tools.append(node));
      researchPanel.append(tools);
    }
    strategyShell.replaceChildren(listPane, inspector, editorPane);
  }
  const taskPanel = document.createElement("section");
  taskPanel.id = "stage76-task-workbench";
  taskPanel.className = "panel panel-wide stage76-task-workbench";
  taskPanel.hidden = true;
  taskPanel.innerHTML = '<div class="panel-header"><div><h3>任务工作台</h3><p>表格式分页查看三种回测任务；操作按钮由任务当前能力决定。</p></div><button type="button" id="stage76-task-refresh">刷新任务</button></div><form id="stage76-task-filter" class="task-filter-bar"><label><span>模式</span><select name="mode"><option value="">全部模式</option><option value="single">单品种测试</option><option value="independent-screening">独立账户批量回测</option><option value="shared-portfolio">投资组合回测</option></select></label><label><span>状态</span><select name="status"><option value="">全部状态</option><option value="ready">待执行</option><option value="running">运行中</option><option value="completed">已完成</option><option value="partial_completed">部分完成</option><option value="failed">失败</option></select></label><label><span>搜索</span><input name="search" placeholder="任务编号、策略或股票"></label><label><span>每页</span><select id="stage76-task-page-size"><option value="20">20 条</option><option value="50">50 条</option><option value="100">100 条</option></select></label><input name="limit" type="hidden" value="500"><button type="submit">查询</button></form><div id="stage76-task-summary" class="summary-grid"></div><div id="stage76-task-table" class="stage76-task-table"><div class="empty-cell">正在读取任务...</div></div><div id="stage76-task-pager" class="stage76-task-pager"><button type="button" id="stage76-task-prev">上一页</button><span id="stage76-task-page-info">第 1 页</span><button type="button" id="stage76-task-next">下一页</button></div>';
  $("#page-backtest .section-grid")?.append(taskPanel);
  const resultPanel=document.querySelector(".stage75-result-dock");
  if(resultPanel && !$("#stage76-result-tabs")) {
    const switcher=document.createElement("aside"); switcher.id="stage76-result-task-switcher"; switcher.className="stage76-result-task-switcher";
    const tabs=document.createElement("nav"); tabs.id="stage76-result-tabs"; tabs.className="stage76-result-tabs";
    tabs.innerHTML='<button type="button" data-stage76-result-tab="analysis">回测分析</button><button type="button" data-stage76-result-tab="trades">交易明细</button><button type="button" data-stage76-result-tab="positions">持仓快照</button><button type="button" data-stage76-result-tab="accounts">账户快照</button>';
    resultPanel.querySelector(".result-dock-header")?.after(switcher,tabs);
    const overview=document.createElement("section"); overview.className="stage76-result-section"; overview.dataset.stage76ResultSection="analysis";
    [$("#independent-result-run-selector"),$("#backtest-result-panel-summary"),$("#backtest-data-version-summary"),$("#backtest-result-panel-metrics"),$("#backtest-result-equity-chart"),$("#backtest-result-drawdown-chart"),$("#backtest-trade-attribution"),$("#backtest-risk-metrics"),$("#backtest-exposure-summary"),$("#backtest-portfolio-panel-summary"),$("#backtest-asset-consistency-summary"),$("#backtest-portfolio-equity-chart")].filter(Boolean).forEach((node)=>overview.append(node));
    const trades=document.createElement("section"); trades.className="stage76-result-section"; trades.dataset.stage76ResultSection="trades"; trades.innerHTML='<div class="panel-header"><div><h4>交易明细</h4><p>按当前任务和股票上下文展示真实成交记录。</p></div></div><div id="stage76-result-trades"></div>';
    const positions=document.createElement("section"); positions.className="stage76-result-section"; positions.dataset.stage76ResultSection="positions"; positions.innerHTML='<div class="panel-header"><div><h4>持仓快照</h4><p>单股为独立账户持仓；投资组合回测为组合账户多票持仓。</p></div></div><div id="stage76-result-positions"></div>';
    const accounts=document.createElement("section"); accounts.className="stage76-result-section"; accounts.dataset.stage76ResultSection="accounts"; accounts.innerHTML='<div class="panel-header"><div><h4>账户快照</h4><p>独立账户批量回测切换股票后查看对应独立资金账户。</p></div></div><div id="stage76-result-accounts"></div>';
    resultPanel.append(overview,trades,positions,accounts);
    window.ReportUI?.mount(resultPanel);
    const legacyTables=$("#backtest-result-panel-tables"); if(legacyTables) legacyTables.hidden=true;
    resultPanel.tabIndex=-1;
    [$("#backtest-portfolio-panel-output")?.closest("details"), $("#backtest-input-snapshot-output")?.closest("details"), $("#backtest-result-panel-output")?.closest("details"), $("#backtest-table-prev")?.closest(".button-row"), $("#backtest-result-page-table"), $("#backtest-result-export-output"), $("#backtest-experiment-panel-output")].filter(Boolean).forEach((node)=>{node.hidden=true;node.classList.add("stage76-retired-result-technical");});
  }
}
function activateStage76ResultTab(tab) {
  tab = tab === "overview" || tab === "report" ? "analysis" : tab;
  document.querySelectorAll("[data-stage76-result-tab]").forEach((button)=>button.classList.toggle("is-active",button.dataset.stage76ResultTab===tab));
  document.querySelectorAll("[data-stage76-result-section]").forEach((section)=>section.hidden=section.dataset.stage76ResultSection!==tab);
  if(tab==="analysis" && stage76SelectedTask) loadStage76EmbeddedReport(stage76SelectedTask).catch((error)=>{window.ReportUI?.renderResult(stage76SelectedTask||{},stage76CurrentResult||{});setFeedback(`专业分析加载失败，已保留基础分析：${error.message}`,"error");});
  updateStage75Url({result_tab:tab});
}

function renderStage76ResultTaskSwitcher(task=stage76SelectedTask) {
  const target=$("#stage76-result-task-switcher"); if(!target||!task)return;
  const peers=stage76TaskCatalog.filter((item)=>item.mode===task.mode && item.capabilities?.can_view_result).slice(0,20);
  target.innerHTML='<div><strong>同模式任务</strong><span>快速切换，不混合不同账户语义</span></div><div class="stage76-result-task-list">'+peers.map((item)=>`<button type="button" data-stage76-result-task="${escapeHtml(item.task_id)}" class="${item.task_id===task.task_id?"is-selected":""}">${escapeHtml(item.name||item.task_id)}</button>`).join("")+'</div>';
  target.querySelectorAll("[data-stage76-result-task]").forEach((button)=>button.addEventListener("click",()=>{const selected=peers.find((item)=>item.task_id===button.dataset.stage76ResultTask);if(selected){stage76SelectedTask=selected;handleStage76TaskAction(selected,"analysis").catch((error)=>setFeedback(error.message,"error"));}}));
}

function renderStage76ResultDetails(result={}) {
  stage76CurrentResult=result;
  const trades=result.trades||[], positions=result.positions||[], accounts=result.accounts||[];
  const tradesTarget=$("#stage76-result-trades"), positionsTarget=$("#stage76-result-positions"), accountsTarget=$("#stage76-result-accounts");
  if(tradesTarget) tradesTarget.innerHTML=renderTable(trades,[{key:"trade_time",label:"时间"},{key:"order_book_id",label:"股票"},{key:"side",label:"方向"},{key:"price",label:"价格"},{key:"quantity",label:"数量"},{key:"amount",label:"成交额"},{key:"commission",label:"佣金"},{key:"tax",label:"印花税"}]);
  if(positionsTarget) positionsTarget.innerHTML=renderTable(positions,[{key:"snapshot_time",label:"时间"},{key:"order_book_id",label:"股票"},{key:"quantity",label:"数量"},{key:"market_value",label:"市值"},{key:"avg_price",label:"成本价"},{key:"weight",label:"权重"}]);
  if(accountsTarget) accountsTarget.innerHTML=renderTable(accounts,[{key:"snapshot_time",label:"时间"},{key:"total_value",label:"总资产"},{key:"cash",label:"现金"},{key:"market_value",label:"持仓市值"},{key:"unit_net_value",label:"单位净值"}]);
  window.ReportUI?.renderResult(stage76SelectedTask||{},result);
  window.ReportUI?.renderRawTables(result,stage76SelectedTask?.mode||"single");
  renderStage76ResultTaskSwitcher();
}
function activateStage76Workspace(workspace, mode = "", updateUrl = true) {
  stage76Workspace = workspace;
  document.querySelectorAll("[data-stage76-workspace]").forEach((button)=>button.classList.toggle("is-active",button.dataset.stage76Workspace===workspace));
  const taskPanel=$("#stage76-task-workbench"); if(taskPanel) taskPanel.hidden=!['tasks','results'].includes(workspace);
  const common=$("#backtest-common-config"); const modeTabs=$("#stage76-create-mode-tabs");
  if(common) common.hidden=workspace!=="create"; if(modeTabs) modeTabs.hidden=workspace!=="create";
  if(workspace==="strategy") activateBacktestView("strategy");
  else if(workspace==="research") activateBacktestView("research");
  else if(workspace==="create") activateStage76CreateMode(mode || (["single","independent","portfolio"].includes(currentBacktestView)?currentBacktestView:"single"));
  else if(workspace==="tasks") {
    document.querySelectorAll("[data-backtest-view]").forEach((panel)=>panel.classList.remove("is-active"));
    loadStage76Tasks().catch((error)=>setFeedback(error.message,"error"));
  }
  else if(workspace==="results") {
    document.querySelectorAll("[data-backtest-view]").forEach((panel)=>panel.classList.remove("is-active"));
    loadStage76Tasks().then((tasks)=>{
      const selected = tasks.find((task)=>task.task_id===stage76SelectedTask?.task_id && task.capabilities?.can_view_result)
        || tasks.find((task)=>task.capabilities?.can_view_result || task.capabilities?.can_view_report);
      if (!selected) {
        openStage75ResultDock();
        setFeedback("当前没有可查看的回测结果，请先完成回测任务", "error");
        return;
      }
      stage76SelectedTask=selected;
      return handleStage76TaskAction(selected,"analysis");
    }).catch((error)=>setFeedback(error.message,"error"));
  }
  if (updateUrl) updateStage75Url({page:"backtest",workspace,view:workspace==="create"?(mode||currentBacktestView):workspace});
}

function activateStage76CreateMode(mode) {
  activateBacktestView(mode);
  syncStage76CommonFields(mode);
  document.querySelectorAll("[data-stage76-mode]").forEach((button)=>button.classList.toggle("is-active",button.dataset.stage76Mode===mode));
  $("#backtest-common-config").hidden=false; $("#stage76-create-mode-tabs").hidden=false;
}

async function submitSingleBacktestTask(event, onlyCreate = false) {
  event?.preventDefault?.();
  const form=$("#backtest-run-form");
  const runId=newTaskId("single-run");
  if(form.elements.run_id) form.elements.run_id.value=runId;
  const values=Object.fromEntries(new FormData(form).entries());
  const body={
    task_id:null, run_id:runId,
    name:(selectedStrategy?.name || values.strategy_name || "策略")+" · "+values.symbol,
    strategy_name:values.strategy_name, strategy_id:values.strategy_id || selectedStrategy?.strategy_id,
    strategy_version:values.strategy_version || selectedStrategy?.latest_version,
    symbol:values.symbol, benchmark:values.benchmark, start_date:values.start_date, end_date:values.end_date,
    initial_cash:Number(values.initial_cash || 1000000), frequency:"1d", adjustment:values.adjustment || "qfq",
    parameters:collectStrategyParameters(), extra_config:{rqalpha_local:buildRqalphaLocalConfig(values)},
  };
  setFeedback("正在创建单股后台任务...");
  const created=await requestJson("/api/backtest/single-backtest-tasks",{method:"POST",body:JSON.stringify(body)});
  let task=created.task||{};
  currentSingleTask=task;
  stage76SelectedTask=null;
  if (!onlyCreate) {
    const started=await requestJson(task.links?.run || `/api/backtest/single-backtest-tasks/${encodeURIComponent(task.task_id)}/run`,{method:"POST",body:JSON.stringify({wait:false})});
    task=started.task||task;
    currentSingleTask=task;
    setFeedback("单股任务已创建并启动", "success");
  } else setFeedback("单股任务已创建，等待执行", "success");
  setStage76ModeTaskState("single",true,task);
  renderTaskProgress("#single-run-progress",{status:task.status||"ready",percent:Number(task.progress?.percent||0),phase:task.progress?.phase||backtestStatusInfo(task.status||"ready").label,processed:task.progress?.processed||0,total:task.progress?.total||1});
  await loadStage76Tasks();
}

function renderStage76TaskTable(tasks=[]) {
  const target=$("#stage76-task-table"); if(!target) return;
  const totalPages=Math.max(1,Math.ceil(stage76TaskTotal/stage76TaskPageSize));
  stage76TaskPage=Math.min(Math.max(1,stage76TaskPage),totalPages);
  const start=(stage76TaskPage-1)*stage76TaskPageSize;
  const pageTasks=tasks;
  const header='<div class="stage76-task-table-header"><span>任务</span><span>策略</span><span>模式与范围</span><span>进度</span><span>操作</span></div>';
  const rows=pageTasks.map((task)=>{
    const info=backtestStatusInfo(task.status); const p=task.progress||{}; const cap=task.capabilities||{};
    return `<article class="stage76-task-row ${stage76SelectedTask?.task_id===task.task_id?"is-selected":""}" data-stage76-task="${escapeHtml(task.task_id)}" data-stage76-mode-value="${escapeHtml(task.mode)}"><div class="stage76-task-main"><span class="task-status-badge is-${info.tone}">${escapeHtml(info.label)}</span><h4>${escapeHtml(task.name||task.task_id)}</h4><p title="${escapeHtml(task.task_id)}">${escapeHtml(shortTechnicalId(task.task_id))} · ${escapeHtml(formatTaskTimestamp(task.created_at))}</p></div><div class="stage76-task-cell"><strong>${escapeHtml(task.strategy_binding?.strategy_id||"-")}</strong><small>${escapeHtml(task.strategy_binding?.strategy_version||"-")}</small></div><div class="stage76-task-cell"><strong>${escapeHtml(task.mode_label||task.mode)}</strong><small>${task.symbol?escapeHtml(task.symbol):(task.universe_count||0)+" 只股票"}</small></div><div class="stage76-task-progress"><strong>${Math.round(Number(p.percent||0))}% · ${escapeHtml(p.phase||info.label)}</strong><div class="task-card-progress"><div><i style="width:${Math.max(0,Math.min(100,Number(p.percent||0)))}%"></i></div><span>${p.processed||0}/${p.total||0}</span></div></div><div class="stage76-task-actions">${cap.can_start?'<button type="button" data-stage76-action="start">执行</button>':''}${cap.can_pause?'<button type="button" data-stage76-action="pause">暂停</button>':''}${cap.can_cancel?'<button type="button" data-stage76-action="cancel">取消</button>':''}${cap.can_view_result||cap.can_view_report?'<button type="button" data-stage76-action="analysis">分析报告</button>':''}${cap.can_clone?'<button type="button" data-stage76-action="clone">克隆</button>':''}${cap.can_delete?'<button type="button" class="danger-button" data-stage76-action="delete">删除</button>':''}</div></article>`;
  }).join("");
  target.innerHTML=header+(rows||'<div class="empty-cell">没有符合条件的任务</div>');
  const info=$("#stage76-task-page-info"); if(info) info.textContent=stage76TaskTotal?`${start+1}—${Math.min(start+tasks.length,stage76TaskTotal)} / ${stage76TaskTotal} · 第 ${stage76TaskPage}/${totalPages} 页`:'0 条任务';
  const prev=$("#stage76-task-prev"), next=$("#stage76-task-next"); if(prev) prev.disabled=stage76TaskPage<=1; if(next) next.disabled=stage76TaskPage>=totalPages;
  target.querySelectorAll("[data-stage76-task]").forEach((row)=>row.addEventListener("click",(event)=>{
    const task=stage76TaskCatalog.find((item)=>item.task_id===row.dataset.stage76Task && item.mode===row.dataset.stage76ModeValue); if(!task)return;
    stage76SelectedTask=task; renderStage76TaskTable(stage76TaskCatalog);
    const button=event.target.closest("[data-stage76-action]"); if(button) handleStage76TaskAction(task,button.dataset.stage76Action).catch((error)=>setFeedback(error.message,"error"));
  }));
}
async function loadStage76Tasks(filters={}) {
  const requestId = ++stage76TaskRequestSequence;
  const form=$("#stage76-task-filter"); const values=form?Object.fromEntries(new FormData(form).entries()):{};
  const payload=await requestJson(`/api/backtest/mode-tasks?${buildQuery({...values,...filters,limit:stage76TaskPageSize,offset:(stage76TaskPage-1)*stage76TaskPageSize})}`);
  if(requestId !== stage76TaskRequestSequence) return stage76TaskCatalog;
  stage76TaskTotal=Number(payload.summary?.task_count || 0);
  if(stage76TaskPage > Math.max(1,Math.ceil(stage76TaskTotal/stage76TaskPageSize))) {
    stage76TaskPage=Math.max(1,Math.ceil(stage76TaskTotal/stage76TaskPageSize));
    return loadStage76Tasks(filters);
  }
  stage76TaskCatalog=payload.tasks||[]; renderStage76TaskTable(stage76TaskCatalog);
  // 运行中任务独立取详情，不依赖列表筛选结果。
  const running = new Set(["running","pause_requested","cancel_requested"]);
  const refreshed = new Map();
  const activeTasks=[["single",currentSingleTask],["independent",currentScreeningTask],["portfolio",currentPortfolioTask]];
  await Promise.all(activeTasks.map(async ([mode,current])=>{
    if(!current?.task_id || !running.has(current.status)) return;
    const resource=mode==="single"?"single-backtest-tasks":mode==="independent"?"independent-screening-tasks":"shared-portfolio-tasks";
    try { const detail=await requestJson(`/api/backtest/${resource}/${encodeURIComponent(current.task_id)}`); if(detail.task) refreshed.set(mode,detail.task); }
    catch(error) { setFeedback(`任务状态刷新失败：${error.message}`,"error"); }
  }));
  if(requestId !== stage76TaskRequestSequence) return stage76TaskCatalog;
  activeTasks.forEach(([mode,current])=>{
    if(!current?.task_id)return;
    const latest=refreshed.get(mode)||stage76TaskCatalog.find((task)=>task.task_id===current.task_id); if(!latest)return;
    if(mode==="single"){
      currentSingleTask=latest; setStage76ModeTaskState(mode,true,latest);
      renderTaskProgress("#single-run-progress",{status:latest.status||"ready",percent:Number(latest.progress?.percent||0),phase:latest.progress?.phase||backtestStatusInfo(latest.status||"ready").label,processed:latest.progress?.processed||0,total:latest.progress?.total||1});
    } else if(mode==="independent"){currentScreeningTask=latest;setStage76ModeTaskState(mode,true,latest);renderScreeningTask(latest);}
    else {currentPortfolioTask=latest;setStage76ModeTaskState(mode,true,latest);renderPortfolioTask(latest);}
  });
  const summary=payload.summary||{}; renderSummaryGrid($("#stage76-task-summary"),[{label:"任务总数",value:summary.task_count||0},{label:"单品种测试",value:summary.mode_counts?.single||0},{label:"独立账户批量回测",value:summary.mode_counts?.["independent-screening"]||0},{label:"投资组合回测",value:summary.mode_counts?.["shared-portfolio"]||0}]);
  if(stage76TaskPollTimer) clearTimeout(stage76TaskPollTimer);
  if([...stage76TaskCatalog,currentSingleTask,currentScreeningTask,currentPortfolioTask].some((task)=>running.has(task?.status))) stage76TaskPollTimer=setTimeout(()=>loadStage76Tasks().catch((error)=>setFeedback(error.message,"error")),2000);
  return stage76TaskCatalog;
}

async function handleStage76TaskAction(task, action) {
  if(action==="start") { await requestJson(task.links.run,{method:"POST",body:JSON.stringify({wait:false})}); await loadStage76Tasks(); return; }
  if(action==="pause"||action==="cancel") { await requestJson(task.links.detail+"/control",{method:"POST",body:JSON.stringify({action})}); await loadStage76Tasks(); return; }
  if(action==="delete") { if(!window.confirm(`确认删除任务 ${task.task_id}？`))return; await requestJson(task.links.delete||task.links.detail,{method:"DELETE"}); await loadStage76Tasks(); return; }
  if(action==="clone") {
    if(task.mode==="single") { const payload=await requestJson(task.links.detail); await restoreClonedBacktestConfig("single",payload.task.config||{}); $("#backtest-run-form").elements.run_id.value=newTaskId("single-run"); }
    else { const mode=task.mode==="independent-screening"?"independent":"portfolio"; await cloneStage75Task(mode,task.task_id); }
    return;
  }
  currentModeTask=task;
  if(action==="analysis" || action==="result" || action==="report") {
    const actionId=++stage76ActionSequence;
    ++stage76ReportRequestSequence;
    if(task.mode==="single") { hideIndependentResultSelector(); await loadBacktestResultPanel(task.run_id); }
    else if(task.mode==="independent-screening") await loadIndependentScreeningResultWorkspace(task);
    else { hideIndependentResultSelector(); await loadBacktestResultPanel(task.run_id); }
    if(actionId !== stage76ActionSequence) return;
    openStage75ResultDock(task.run_id||"");
    activateStage76ResultTab("analysis");
    return;
  }
}

function stage76ReportDimensions(professional={}, detail={}) {
  const normalized=normalizeEvaluationReport(professional); const dimensions=normalized?.dimensions||[];
  if(!dimensions.length) return '<div class="empty-cell">当前结果缺少足够的 7 维评估证据，不使用演示值补齐。</div>';
  return `<div class="stage76-report-dimensions">${dimensions.map((item,index)=>`<details ${index===0?"open":""}><summary><span>${escapeHtml(item.title)}</span><strong>${item.score} · ${escapeHtml(item.level?.text||"")}</strong></summary><div class="dimension-metrics">${(item.metrics||[]).map(([label,value])=>`<div class="dimension-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div><div class="mini-chart">${item.chart||""}</div></details>`).join("")}</div><details><summary>报告证据：交易记录</summary>${renderTable(detail.trades||[],[{key:"trade_time",label:"时间"},{key:"order_book_id",label:"股票"},{key:"side",label:"方向"},{key:"price",label:"价格"},{key:"quantity",label:"数量"}])}</details>`;
}

async function loadStage76EmbeddedIndependentRun(task, runId) {
  const requestId=++stage76ReportRequestSequence;
  const payload=await requestJson(`/api/reporting/backtest-modes/independent-screening/${encodeURIComponent(task.task_id)}/runs/${encodeURIComponent(runId)}`); const report=payload.report||{};
  if(requestId !== stage76ReportRequestSequence) return;
  const target=$("#stage76-independent-single-report"); if(!target)return;
  window.ReportUI?.renderSingleAnalysis(target,task,report.professional_report||{},report.run_detail||{},stage76ReportDimensions(report.professional_report||{},report.run_detail||{}));
}

async function loadStage76EmbeddedReport(task) {
  const requestId=++stage76ReportRequestSequence;
  const target=$("#report-result-overview"); if(!target||!task)return;
  target.innerHTML='<div class="empty-cell">正在加载专业报告...</div>';
  if(task.mode==="single") {
    const payload=await requestJson(`/api/reporting/strategy-evaluation/${encodeURIComponent(task.run_id)}`); const professional=payload.report||{};
    if(requestId !== stage76ReportRequestSequence) return;
    window.ReportUI?.renderSingleAnalysis(target,task,professional,stage76CurrentResult||{},stage76ReportDimensions(professional,stage76CurrentResult||{}));
    return;
  }
  const payload=await requestJson(`/api/reporting/backtest-modes/${encodeURIComponent(task.mode)}/${encodeURIComponent(task.task_id)}`); const report=payload.report||{};
  if(requestId !== stage76ReportRequestSequence) return;
  if(task.mode==="shared-portfolio") {
    const gate=report.data_quality_gate||{};
    window.ReportUI?.renderPortfolioAnalysis(target,task,report,stage76ReportDimensions(report.professional_report||{},report.run_detail||{}));
    return;
  }
  const scope=report.sample_scope||{}, distribution=report.distribution||{}, runs=report.run_index||[];
  const runHtml=`<div class="stage76-independent-run-picker"><input id="stage76-independent-run-search" type="search" placeholder="搜索股票"><select id="stage76-independent-run-select">${runs.map((item)=>`<option value="${escapeHtml(item.run_id)}">${escapeHtml(item.symbol||"-")} · ${escapeHtml(item.name||"-")}</option>`).join("")}</select></div><div id="stage76-independent-single-report"><div class="empty-cell">选择实际建仓股票查看独立 Run 报告</div></div>`;
  window.ReportUI?.renderBatchAnalysis(target,task,report,runHtml);
  const select=$("#stage76-independent-run-select"), search=$("#stage76-independent-run-search");
  select?.addEventListener("change",()=>loadStage76EmbeddedIndependentRun(task,select.value).catch((error)=>setFeedback(error.message,"error")));
  search?.addEventListener("input",()=>{const q=search.value.trim().toLowerCase(); select.innerHTML=runs.filter((item)=>!q||`${item.symbol||""} ${item.name||""}`.toLowerCase().includes(q)).map((item)=>`<option value="${escapeHtml(item.run_id)}">${escapeHtml(item.symbol||"-")} · ${escapeHtml(item.name||"-")}</option>`).join("");});
  if(runs[0]) await loadStage76EmbeddedIndependentRun(task,runs[0].run_id);
}

function stage76RunMode(run={}) {
  if(run.extra_config?.screening_task_id) return "independent-single";
  if(run.extra_config?.mode==="shared_cash_portfolio"||run.extra_config?.portfolio_mode==="shared_cash") return "shared-portfolio";
  return "single";
}
function bindStage76Events() {
  document.querySelectorAll("[data-stage76-workspace]").forEach((button)=>button.addEventListener("click",()=>{activatePage("backtest");activateStage76Workspace(button.dataset.stage76Workspace);}));
  document.querySelectorAll("[data-stage76-mode]").forEach((button)=>button.addEventListener("click",()=>activateStage76Workspace("create",button.dataset.stage76Mode)));
  document.querySelectorAll("[data-stage76-form-action]").forEach((button)=>button.addEventListener("click",()=>handleStage76FormTaskAction(button.dataset.stage76ActionMode,button.dataset.stage76FormAction).catch((error)=>setFeedback(error.message,"error"))));
  document.querySelectorAll("[data-stage76-result-tab]").forEach((button)=>button.addEventListener("click",()=>activateStage76ResultTab(button.dataset.stage76ResultTab)));
  activateStage76ResultTab("analysis");
  $("#stage76-code-validate")?.addEventListener("click",()=>$("#strategy-validate")?.click());
  $("#stage76-code-theme")?.addEventListener("click",()=>setStage76CodeTheme($("#strategy-editor")?.closest(".stage76-code-editor-shell")?.dataset.theme==="dark"?"light":"dark"));
  $("#strategy-library-sort")?.addEventListener("change",renderStrategyLibrary);
  $("#backtest-common-config")?.addEventListener("input",()=>syncStage76CommonFields(currentBacktestView));
  $("#backtest-common-strategy")?.addEventListener("change",(event)=>{const strategy=strategyCatalog.find((item)=>item.strategy_id===event.currentTarget.value);if(strategy)selectStrategy(strategy).catch((error)=>setFeedback(error.message,"error"));});
  $("#single-task-create-only")?.addEventListener("click",(event)=>submitSingleBacktestTask(event,true).catch((error)=>setFeedback(error.message,"error")));
  $("#stage76-task-filter")?.addEventListener("submit",(event)=>{event.preventDefault();stage76TaskPage=1;loadStage76Tasks().catch((error)=>setFeedback(error.message,"error"));});
  $("#stage76-task-refresh")?.addEventListener("click",()=>loadStage76Tasks().catch((error)=>setFeedback(error.message,"error")));
  $("#stage76-task-prev")?.addEventListener("click",()=>{stage76TaskPage=Math.max(1,stage76TaskPage-1);loadStage76Tasks().catch((error)=>setFeedback(error.message,"error"));});
  $("#stage76-task-next")?.addEventListener("click",()=>{stage76TaskPage+=1;loadStage76Tasks().catch((error)=>setFeedback(error.message,"error"));});
  $("#stage76-task-page-size")?.addEventListener("change",(event)=>{stage76TaskPageSize=Number(event.currentTarget.value)||20;stage76TaskPage=1;loadStage76Tasks().catch((error)=>setFeedback(error.message,"error"));});
  activateStage76Workspace("strategy", "", false);
}
function bindEvents() { configureStage75Shell(); configureStage76InformationArchitecture(); bindBacktestWorkspace(); bindStrategyManager(); configureReportingWorkspace(); configureStage75Relocations(); configureUnifiedNavigation(); bindStage75Events(); bindStage76Events(); document.querySelectorAll(".nav-tab").forEach((button) => button.addEventListener("click", () => { activatePage(button.dataset.page, false); if (button.dataset.page === "market" && !aShareWorkspaceLoaded) { loadAShareOverview().then(() => { aShareWorkspaceLoaded = true; setFeedback("A 股数据基座已加载", "success"); }).catch((error) => setFeedback(error.message, "error")); } })); document.querySelectorAll("[data-jump]").forEach((button) => button.addEventListener("click", () => activatePage(button.dataset.jump, false))); const marketQueryForm = $("#market-query-form"); if (marketQueryForm) marketQueryForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadMarket(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("数据中心已刷新", "success"); }); const aShareSymbolForm = $("#a-share-symbol-form"); if (aShareSymbolForm) aShareSymbolForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadAShareSymbols(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("A 股股票目录已刷新", "success"); }); const aShareDailyForm = $("#a-share-daily-form"); if (aShareDailyForm) aShareDailyForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadAShareDaily(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("A 股真实日线已刷新", "success"); }); const aShareSymbolBody = $("#a-share-symbol-body"); if (aShareSymbolBody) aShareSymbolBody.addEventListener("click", async (event) => { const button = event.target.closest("[data-a-share-symbol]"); if (!button) return; aShareDailyForm.elements.symbol.value = button.dataset.aShareSymbol; await loadAShareDaily(Object.fromEntries(new FormData(aShareDailyForm).entries())); setFeedback("已加载 " + button.dataset.aShareSymbol + " 真实日线", "success"); }); const repairGapsButton = $("#market-repair-gaps"); if (repairGapsButton) repairGapsButton.addEventListener("click", repairMarketGaps); const assetDirectoryForm = $("#backtest-asset-directory-form"); if (assetDirectoryForm) assetDirectoryForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadBacktestAssetDirectory(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("回测资产目录已刷新", "success"); }); const migrationDryRun = $("#backtest-asset-migration-dry-run"); if (migrationDryRun) migrationDryRun.addEventListener("click", async () => { await migrateBacktestInputSnapshots(true); setFeedback("历史输入快照迁移预检完成", "success"); }); const migrationRun = $("#backtest-asset-migration-run"); if (migrationRun) migrationRun.addEventListener("click", async () => { await migrateBacktestInputSnapshots(false); setFeedback("历史输入快照迁移完成", "success"); }); $("#factor-query-form").addEventListener("submit", async (event) => { event.preventDefault(); await loadFactors(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("因子分析已刷新", "success"); }); $("#backtest-run-form").addEventListener("submit", (event) => submitSingleBacktestTask(event, false).catch((error) => setFeedback(error.message, "error"))); const resultsRefresh = $("#backtest-results-refresh"); if (resultsRefresh) resultsRefresh.addEventListener("click", () => refreshBacktestResults().then(() => setFeedback("回测结果已刷新", "success")).catch((error) => setFeedback(error.message, "error"))); const resultsReport = $("#backtest-results-report"); if (resultsReport) resultsReport.addEventListener("click", () => openSelectedBacktestReport().catch((error) => setFeedback(error.message, "error"))); const modeTaskForm = $("#mode-task-directory-form"); if (modeTaskForm) modeTaskForm.addEventListener("submit", async (event) => { event.preventDefault(); await loadBacktestModeTasks(Object.fromEntries(new FormData(event.currentTarget).entries())); setFeedback("双模式回测任务已筛选", "success"); }); const modeTaskRefresh = $("#mode-task-directory-refresh"); if (modeTaskRefresh) modeTaskRefresh.addEventListener("click", () => loadBacktestModeTasks().then(() => setFeedback("双模式回测任务已刷新", "success")).catch((error) => setFeedback(error.message, "error"))); const screeningForm = $("#screening-task-form"); if (screeningForm) screeningForm.addEventListener("submit", (event) => createIndependentScreeningTask(event).catch(() => {})); const screeningRun = $("#screening-task-run"); if (screeningRun) screeningRun.addEventListener("click", () => runIndependentScreeningTask().catch((error) => setFeedback(error.message, "error"))); const screeningPause = $("#screening-task-pause"); if (screeningPause) screeningPause.addEventListener("click", () => controlIndependentScreeningTask("pause").catch((error) => setFeedback(error.message, "error"))); const screeningCancel = $("#screening-task-cancel"); if (screeningCancel) screeningCancel.addEventListener("click", () => controlIndependentScreeningTask("cancel").catch((error) => setFeedback(error.message, "error"))); const screeningRefresh = $("#screening-task-refresh"); if (screeningRefresh) screeningRefresh.addEventListener("click", () => loadIndependentScreeningTasks().then(() => setFeedback("独立账户批量回测任务已刷新", "success")).catch((error) => setFeedback(error.message, "error")));  const portfolioForm = $("#portfolio-task-form"); if (portfolioForm) portfolioForm.addEventListener("submit", (event) => createSharedPortfolioTask(event).catch(() => {})); const portfolioRun = $("#portfolio-task-run"); if (portfolioRun) portfolioRun.addEventListener("click", () => runSharedPortfolioTask().catch((error) => setFeedback(error.message, "error"))); const portfolioRefresh = $("#portfolio-task-refresh"); if (portfolioRefresh) portfolioRefresh.addEventListener("click", () => loadSharedPortfolioTasks().then(() => setFeedback("投资组合回测任务已刷新", "success")).catch((error) => setFeedback(error.message, "error"))); const researchCreate = $("#strategy-research-create"); if (researchCreate) researchCreate.addEventListener("click", createStrategyResearchTask); const experimentCreate = $("#backtest-experiment-index-create"); if (experimentCreate) experimentCreate.addEventListener("click", createCurrentExperimentIndex); const experimentRefresh = $("#backtest-experiment-index-refresh"); if (experimentRefresh) experimentRefresh.addEventListener("click", loadExperimentIndex); const experimentCompare = $("#backtest-experiment-compare"); if (experimentCompare && typeof compareSelectedExperiments === "function") experimentCompare.addEventListener("click", compareSelectedExperiments); $("#strategy-parameter-scan").addEventListener("click", runParameterScan); const matrixCreate = $("#strategy-matrix-create"); if (matrixCreate) matrixCreate.addEventListener("click", createParameterMatrixTask); const matrixRun = $("#strategy-matrix-run"); if (matrixRun) matrixRun.addEventListener("click", runCurrentParameterMatrixTask); $("#strategy-scan-save-snapshot").addEventListener("click", saveCurrentScanComparisonSnapshot); $("#backtest-jump-reporting").addEventListener("click", async (event) => { const runId = event.currentTarget.dataset.runId; activatePage("reporting"); $('#reporting-query-form input[name="run_id"]').value = runId; try { await loadReports(runId, "phase1-batch-001"); } catch (_) { setFeedback("已跳转报告中心，请刷新 seeded run 或检查 run_id", "error"); } }); $("#ai-analysis-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); await runAI(form.get("symbol"), form.get("analysis_date")); setFeedback("AI 摘要已生成", "success"); }); const modeReportForm = $("#mode-report-form"); if (modeReportForm) modeReportForm.addEventListener("submit", (event) => loadBacktestModeReport(event).catch((error) => setFeedback(error.message, "error"))); $("#reporting-query-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); await loadReports(form.get("run_id"), form.get("experiment_id")); setFeedback("报告中心已刷新", "success"); }); $("#config-refresh").addEventListener("click", async () => { await loadConfig(); setFeedback("配置状态已刷新", "success"); }); $("#config-save-draft").addEventListener("click", saveConfigDraft); $("#report-save-snapshot").addEventListener("click", saveCurrentReportSnapshot); $("#report-package-create").addEventListener("click", createCurrentReportPackage); const comparisonPackageCreate = $("#report-comparison-package-create"); if (comparisonPackageCreate) comparisonPackageCreate.addEventListener("click", createExperimentComparisonPackage); const packageDirectoryRefresh = $("#report-package-directory-refresh"); if (packageDirectoryRefresh) packageDirectoryRefresh.addEventListener("click", async () => { await loadReportPackageDirectory(); setFeedback("报告包归档目录已刷新", "success"); }); const exportManifestCreate = $("#report-package-export-manifest-create"); if (exportManifestCreate) exportManifestCreate.addEventListener("click", createReportPackageExportManifest); const lifecycleActive = $("#report-package-lifecycle-active"); if (lifecycleActive) lifecycleActive.addEventListener("click", () => updateSelectedReportPackageLifecycle("active", { protected: false, reason: "恢复为活跃报告包" })); const lifecycleArchive = $("#report-package-lifecycle-archive"); if (lifecycleArchive) lifecycleArchive.addEventListener("click", () => updateSelectedReportPackageLifecycle("archived", { protected: false, reason: "阶段56 归档保留" })); const lifecycleProtect = $("#report-package-lifecycle-protect"); if (lifecycleProtect) lifecycleProtect.addEventListener("click", () => updateSelectedReportPackageLifecycle("protected", { protected: true, retention_policy: "retain-protected", reason: "阶段56 保护保留" })); $("#report-package-export-html").addEventListener("click", () => exportSelectedReportPackage("html")); $("#report-package-export-json").addEventListener("click", () => exportSelectedReportPackage("json")); $("#report-package-export-pdf").addEventListener("click", () => exportSelectedReportPackage("pdf")); $("#report-package-export-word").addEventListener("click", () => exportSelectedReportPackage("word")); }
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
async function main() {
  const params = new URLSearchParams(window.location.search);
  bindEvents();
  bindBacktestResultControls();
  renderTraceability();
  renderAcceptanceMatrix();
  const requestedPage = params.get("page");
  const requestedView = params.get("view");
  const requestedWorkspace = params.get("workspace");
  if (requestedView && ["strategy", "single", "independent", "portfolio", "research"].includes(requestedView)) activateBacktestView(requestedView);
  const requestedNavigationGroup = requestedPage === "market" && params.get("dc_view") === "assets" ? "market-data" : "";
  if (requestedPage && pageTitles[requestedPage]) activatePage(requestedPage, true, true, requestedNavigationGroup);
  if (requestedPage === "backtest" && ["strategy", "create", "tasks", "research", "results"].includes(requestedWorkspace)) activateStage76Workspace(requestedWorkspace, requestedView);
  try {
    await loadDashboard();
    await loadBacktestModeTasks();
    await loadStage76Tasks();
    const compareIds = (params.get("compare") || "").split(",").filter(Boolean).slice(0, 4);
    for (const runId of compareIds) await addStage75ComparisonRun(runId);
    const runId = params.get("run");
    if (runId && requestedPage === "backtest") {
      stage76SelectedTask = stage76TaskCatalog.find((task) => task.run_id === runId) || stage76SelectedTask;
      await loadBacktestResultPanel(runId);
      renderStage76ResultTaskSwitcher();
    }
    const resultTab = params.get("result_tab");
    if (resultTab && ["overview", "trades", "positions", "accounts", "report"].includes(resultTab)) activateStage76ResultTab(resultTab);
    setFeedback("MVP 数据加载完成", "success");
  } catch (error) {
    setFeedback(error.message, "error");
  }
}
main();











































