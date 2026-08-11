(function () {
  "use strict";

  const COLORS = {
    rise: "#e74c3c",
    fall: "#2ecc71",
    neutral: "#95a5a6",
    warning: "#f39c12",
    ink: "#243746",
    grid: "#dfe7ec",
  };

  const MODE_LABELS = {
    single: "单品种测试",
    "independent-screening": "独立账户批量回测",
    "shared-portfolio": "投资组合回测",
  };

  const METRIC_TOOLTIPS = {
    "年化收益率": "将回测区间收益折算为一年收益，用于比较不同周期策略。",
    "最大回撤": "净值从历史高点到后续低点的最大跌幅，越接近 0 风险越低。",
    "夏普比率": "单位波动承担获得的超额收益，常用公式为（年化收益－无风险收益）÷年化波动。",
    "卡玛比率": "年化收益与最大回撤绝对值之比，衡量收益对回撤的补偿。",
    "盈亏比": "盈利交易平均盈利与亏损交易平均亏损绝对值之比。",
    "交易次数 / 胜率": "已完成交易数量及其中盈利交易占比。",
    "超额收益": "策略收益减去同期基准收益。",
    "信息比率": "超额收益与跟踪误差之比。",
    "跟踪误差": "策略相对基准收益差的波动程度。",
    "IC均值": "本报告为策略收盘持仓权重与下一交易日标的收益的平均 Pearson 相关系数。",
    "ICIR": "日度 IC 均值除以 IC 标准差并乘以 √252，衡量横截面预测稳定性。",
    "IC正数比率": "IC 为正的统计周期占比。",
    "分层单调性": "因子分组收益是否随排序方向稳定递增或递减。",
    "总收益率": "回测起点至终点的累计收益率，不进行年化折算。",
    "年化波动率": "基于真实账户净值的日收益标准差乘以 √252。",
    "平均持有天数": "按同一标的先进先出配对买卖，以平仓数量加权计算自然日持有期。",
    "双边年化换手率": "买卖成交额绝对值之和除以平均账户资产，并按有效交易期折算至一年。",
    "有效日期覆盖率": "账户净值有效日期数相对基准时间轴日期数的比例。",
    "无法成交尝试占比": "无法成交尝试数除以无法成交尝试数与成交记录数之和。",
    "证据等级": "综合数据覆盖、明细完整性和七维评估证据得出的报告可靠性等级。",
  };

  const escapeHtml = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");

  function finite(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function pick(source, keys, fallback = null) {
    for (const key of keys) {
      const parts = key.split(".");
      let value = source;
      for (const part of parts) value = value == null ? null : value[part];
      if (value !== null && value !== undefined && value !== "") return value;
    }
    return fallback;
  }

  function formatPercent(value) {
    const number = finite(value);
    if (number === null) return "暂无数据";
    return `${(number * 100).toFixed(2)}%`;
  }

  function formatNumber(value, digits = 2) {
    const number = finite(value);
    return number === null ? "暂无数据" : number.toFixed(digits);
  }

  function formatRatio(value) {
    const number = finite(value);
    if (number === null) return "暂无数据";
    return number !== 0 && Math.abs(number) < 0.01 ? number.toFixed(4) : number.toFixed(2);
  }

  function tone(value, invert = false) {
    const number = finite(value);
    if (number === null || number === 0) return "is-neutral";
    const positive = number > 0;
    return (invert ? !positive : positive) ? "is-rise" : "is-fall";
  }

  function metricCard(title, value, options = {}) {
    const tooltip = options.tooltip || METRIC_TOOLTIPS[title] || "该指标来自当前回测结果；缺少证据时不使用演示值补齐。";
    const toneClass = options.tone || "is-neutral";
    const meta = options.meta ? `<small>${escapeHtml(options.meta)}</small>` : "";
    return `<article class="report-metric-card ${toneClass}">
      <div class="report-metric-title"><span>${escapeHtml(title)}</span><button type="button" class="metric-help" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(title)}说明">?</button></div>
      <strong>${escapeHtml(value)}</strong>${meta}
    </article>`;
  }

  function emptyState(message) {
    return `<div class="report-empty">${escapeHtml(message)}</div>`;
  }

  function normalizeSeries(rows, valueKeys = ["value"]) {
    return (rows || []).map((row, index) => {
      const raw = valueKeys.map((key) => pick(row, [key])).find((value) => finite(value) !== null);
      return {
        label: pick(row, ["snapshot_time", "date", "time", "trade_time"], String(index + 1)),
        value: finite(raw),
      };
    }).filter((item) => item.value !== null);
  }

  function deriveDrawdown(series) {
    let peak = null;
    return (series || []).map((item) => {
      peak = peak === null ? item.value : Math.max(peak, item.value);
      return { label: item.label, value: peak ? item.value / peak - 1 : 0 };
    });
  }

  function deriveTradeMetrics(trades) {
    const books = new Map();
    const lots = new Map();
    const realized = [];
    let holdingDayQuantity = 0;
    let holdingDayWeighted = 0;
    for (const row of trades || []) {
      const symbol = String(pick(row, ["order_book_id", "symbol"], "-") || "-");
      const side = String(row.side || "").toUpperCase();
      const quantity = Math.abs(finite(row.quantity) || 0);
      const amount = Math.abs(finite(row.amount) ?? ((finite(row.price) || 0) * quantity));
      const fees = Math.abs(finite(row.commission) || 0) + Math.abs(finite(row.tax) || 0);
      const timestamp = Date.parse(pick(row, ["trade_time", "trade_date", "date"], ""));
      if (!quantity) continue;
      const book = books.get(symbol) || { quantity: 0, averageCost: 0 };
      const symbolLots = lots.get(symbol) || [];
      if (side === "BUY") {
        book.averageCost = (book.quantity * book.averageCost + amount + fees) / (book.quantity + quantity);
        book.quantity += quantity;
        symbolLots.push({ quantity, timestamp: Number.isFinite(timestamp) ? timestamp : null });
      } else if (side === "SELL" && book.quantity > 0) {
        const closed = Math.min(quantity, book.quantity);
        const explicit = finite(pick(row, ["pnl", "realized_pnl", "profit"], null));
        realized.push(explicit ?? (amount - fees - closed * book.averageCost));
        let remaining = closed;
        while (remaining > 1e-9 && symbolLots.length) {
          const lot = symbolLots[0];
          const consumed = Math.min(remaining, lot.quantity);
          if (lot.timestamp !== null && Number.isFinite(timestamp)) {
            holdingDayWeighted += Math.max(0, timestamp - lot.timestamp) / 86400000 * consumed;
            holdingDayQuantity += consumed;
          }
          lot.quantity -= consumed;
          remaining -= consumed;
          if (lot.quantity <= 1e-9) symbolLots.shift();
        }
        book.quantity -= closed;
        if (book.quantity <= 1e-9) book.averageCost = 0;
      }
      books.set(symbol, book);
      lots.set(symbol, symbolLots);
    }
    const wins = realized.filter((value) => value > 0);
    const losses = realized.filter((value) => value < 0);
    const average = (values) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    return {
      trade_count: realized.length,
      win_rate: realized.length ? wins.length / realized.length : null,
      profit_loss_ratio: wins.length && losses.length ? average(wins) / Math.abs(average(losses)) : null,
      average_holding_days: holdingDayQuantity ? holdingDayWeighted / holdingDayQuantity : null,
      realized,
    };
  }

  function unavailableMetric(title, reason, tooltip = "当前报告缺少计算该指标所需的真实底层证据。") {
    return metricCard(title, "不可用", { tone: "is-warning", meta: reason, tooltip });
  }

  function annualizedVolatility(series) {
    const returns = [];
    for (let index = 1; index < (series || []).length; index += 1) {
      const previous = finite(series[index - 1]?.value);
      const current = finite(series[index]?.value);
      if (previous !== null && current !== null && previous !== 0) returns.push(current / previous - 1);
    }
    if (returns.length < 2) return null;
    const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
    const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / returns.length;
    return Math.sqrt(variance) * Math.sqrt(252);
  }

  function annualizeTotalReturn(totalReturn, pointCount) {
    const total = finite(totalReturn);
    if (total === null || total <= -1 || pointCount < 2) return null;
    return (1 + total) ** (252 / (pointCount - 1)) - 1;
  }

  function drawdownWindow(series) {
    if (!(series || []).length) return null;
    let trough = 0;
    for (let index = 1; index < series.length; index += 1) {
      if (series[index].value < series[trough].value) trough = index;
    }
    let peak = trough;
    for (let index = trough; index >= 0; index -= 1) {
      if (series[index].value >= -1e-10) { peak = index; break; }
    }
    if (trough === peak && series[trough].value >= -1e-10) return null;
    return `${String(series[peak].label).slice(0, 10)} → ${String(series[trough].label).slice(0, 10)}`;
  }

  function deriveAnnualizedTurnover(trades, equity) {
    const amounts = (trades || []).map((row) => Math.abs(finite(row.amount) ?? ((finite(row.price) || 0) * (finite(row.quantity) || 0)))).filter(Number.isFinite);
    const capital = (equity || []).map((item) => finite(item.value)).filter((value) => value !== null && value > 0);
    if (!amounts.length || capital.length < 2) return null;
    const averageCapital = capital.reduce((sum, value) => sum + value, 0) / capital.length;
    return amounts.reduce((sum, value) => sum + value, 0) / averageCapital * 252 / (capital.length - 1);
  }

  function deriveDateCoverage(equity, benchmark) {
    if (!(equity || []).length || !(benchmark || []).length) return null;
    const effective = new Set(equity.map((item) => String(item.label).slice(0, 10))).size;
    const expected = new Set(benchmark.map((item) => String(item.label).slice(0, 10))).size;
    return expected ? Math.min(1, effective / expected) : null;
  }

  function benchmarkUsable(task, detail, metrics) {
    const alignment = task?.config?.extra_config?.rqalpha_local?.benchmark_alignment
      || task?.extra_config?.rqalpha_local?.benchmark_alignment
      || detail?.extra_config?.rqalpha_local?.benchmark_alignment;
    if (alignment === "zero_return") return false;
    return finite(pick(metrics, ["benchmark_return", "benchmark_annualized_return"], null)) !== null
      || Boolean(detail?.benchmark_curve?.length);
  }

  function svgMultiLine(definitions, options = {}) {
    const active = (definitions || []).map((definition) => ({ ...definition, series: definition.series || [] })).filter((definition) => definition.series.length);
    if (!active.length) return emptyState(options.empty || "暂无可绘制的对比数据");
    const width = 920, height = options.height || 240, pad = 42;
    const values = active.flatMap((definition) => definition.series.map((item) => item.value));
    const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
    const x = (index, length) => pad + index / Math.max(length - 1, 1) * (width - pad * 2);
    const y = (value) => pad + (max - value) / span * (height - pad * 2);
    const lines = active.map((definition) => {
      const points = definition.series.map((item, index) => `${x(index, definition.series.length)},${y(item.value)}`).join(" ");
      return `<polyline points="${points}" fill="none" stroke="${definition.color}" stroke-width="3" stroke-dasharray="${definition.dash || ""}"/><text x="${width - pad}" y="${pad + active.indexOf(definition) * 17}" text-anchor="end" fill="${definition.color}" class="report-axis-label">${escapeHtml(definition.label)}</text>`;
    }).join("");
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.label || "净值对比图")}"><line x1="${pad}" x2="${width - pad}" y1="${height - pad}" y2="${height - pad}" class="report-grid-line"/>${lines}<text x="4" y="${pad + 4}" class="report-axis-label">${max.toFixed(4)}</text><text x="4" y="${height - pad}" class="report-axis-label">${min.toFixed(4)}</text></svg>`;
  }
  function svgLine(series, options = {}) {
    if (!series.length) return emptyState(options.empty || "暂无可绘制的时序数据");
    const width = 920, height = options.height || 240, pad = 42;
    const values = series.map((item) => item.value);
    const min = options.zeroFloor ? Math.min(0, ...values) : Math.min(...values);
    const max = options.zeroCeiling ? Math.max(0, ...values) : Math.max(...values);
    const span = max - min || 1;
    const x = (index) => pad + index / Math.max(series.length - 1, 1) * (width - pad * 2);
    const y = (value) => pad + (max - value) / span * (height - pad * 2);
    const points = series.map((item, index) => `${x(index)},${y(item.value)}`).join(" ");
    const circles = series.map((item, index) => `<circle cx="${x(index)}" cy="${y(item.value)}" r="8" fill="transparent"><title>${escapeHtml(String(item.label).slice(0, 19))}：${item.value.toFixed(4)}</title></circle>`).join("");
    const zero = min < 0 && max > 0 ? `<line x1="${pad}" x2="${width - pad}" y1="${y(0)}" y2="${y(0)}" class="report-zero-line"/>` : "";
    const fill = options.area ? `<polygon points="${pad},${y(0)} ${points} ${width - pad},${y(0)}" fill="${options.fill || "rgba(46,204,113,.18)"}"/>` : "";
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.label || "时序图")}">
      <line x1="${pad}" x2="${width - pad}" y1="${pad}" y2="${pad}" class="report-grid-line"/>
      <line x1="${pad}" x2="${width - pad}" y1="${height - pad}" y2="${height - pad}" class="report-grid-line"/>
      ${zero}${fill}<polyline points="${points}" fill="none" stroke="${options.color || COLORS.rise}" stroke-width="3" stroke-linejoin="round"/>
      ${circles}<text x="4" y="${pad + 4}" class="report-axis-label">${max.toFixed(4)}</text>
      <text x="4" y="${height - pad}" class="report-axis-label">${min.toFixed(4)}</text>
      <text x="${pad}" y="${height - 10}" class="report-axis-label">${escapeHtml(String(series[0].label).slice(0, 10))}</text>
      <text x="${width - pad}" y="${height - 10}" text-anchor="end" class="report-axis-label">${escapeHtml(String(series.at(-1).label).slice(0, 10))}</text>
    </svg>`;
  }

  function svgBars(rows, options = {}) {
    const series = (rows || []).map((row, index) => ({
      label: pick(row, ["label", "year", "group", "name"], String(index + 1)),
      value: finite(pick(row, ["value", "return", "annualized_return", "portfolio_return", "excess_return", "pnl", "count"], null)),
    })).filter((item) => item.value !== null);
    if (!series.length) return emptyState(options.empty || "暂无可绘制的分布数据");
    const width = 920, height = options.height || 240, pad = 44;
    const maxAbs = Math.max(...series.map((item) => Math.abs(item.value)), 0.0001);
    const zeroY = height / 2;
    const band = (width - pad * 2) / series.length;
    const bars = series.map((item, index) => {
      const barHeight = Math.abs(item.value) / maxAbs * (height / 2 - pad);
      const y = item.value >= 0 ? zeroY - barHeight : zeroY;
      const color = item.value >= 0 ? COLORS.rise : COLORS.fall;
      return `<rect x="${pad + index * band + band * .12}" y="${y}" width="${band * .76}" height="${Math.max(2, barHeight)}" rx="3" fill="${color}">
        <title>${escapeHtml(item.label)}：${item.value.toFixed(4)}</title></rect>`;
    }).join("");
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.label || "柱状图")}">
      <line x1="${pad}" x2="${width - pad}" y1="${zeroY}" y2="${zeroY}" class="report-zero-line"/>${bars}
      <text x="${pad}" y="${height - 10}" class="report-axis-label">${escapeHtml(series[0].label)}</text>
      <text x="${width - pad}" y="${height - 10}" text-anchor="end" class="report-axis-label">${escapeHtml(series.at(-1).label)}</text>
    </svg>`;
  }

  function chart(title, body, subtitle = "") {
    return `<article class="report-chart-card">
      <header><div><h4>${escapeHtml(title)}</h4>${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}</div>
      <div class="report-chart-tools"><button type="button" data-report-download="svg">SVG</button><button type="button" data-report-download="png">PNG</button></div></header>
      <div class="report-chart-canvas">${body}</div>
    </article>`;
  }

  function section(title, subtitle, content, className = "") {
    return `<section class="report-section ${className}"><header class="report-section-header"><div><span>REPORT SECTION</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(subtitle || "")}</p></div></header>${content}</section>`;
  }

  function collapsibleSection(title, subtitle, content, open = false) {
    return `<details class="report-collapsible" ${open ? "open" : ""}><summary><div><span>ANALYSIS DIMENSION</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(subtitle || "")}</p></div><strong>展开 / 折叠</strong></summary><div class="report-collapsible-body">${content}</div></details>`;
  }

  function dataTable(rows, columns, options = {}) {
    const id = `report-table-${Math.random().toString(36).slice(2, 9)}`;
    if (!(rows || []).length) return emptyState(options.empty || "暂无原始数据");
    const head = columns.map((column) => `<th><button type="button" data-table-sort="${escapeHtml(column.key)}">${escapeHtml(column.label)}</button></th>`).join("");
    const body = rows.map((row) => `<tr>${columns.map((column) => {
      const raw = pick(row, [column.key], "-");
      const side = /side|direction/.test(column.key) ? String(raw).toLowerCase() : "";
      const cellTone = side.includes("buy") || side.includes("买") ? "is-rise" : side.includes("sell") || side.includes("卖") ? "is-fall" : "";
      return `<td class="${cellTone}" data-value="${escapeHtml(raw)}">${escapeHtml(raw)}</td>`;
    }).join("")}</tr>`).join("");
    return `<div class="report-table-tools"><label>筛选<input type="search" data-table-filter="${id}" placeholder="输入关键字"></label><button type="button" data-table-export="${id}">导出 CSV</button></div>
      <div class="table-wrap report-data-table" data-report-table="${id}"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function mount(panel) {
    if (!panel || panel.dataset.reportUiMounted === "true") return;
    panel.dataset.reportUiMounted = "true";
    panel.classList.add("report-workspace");
    const switcher = panel.querySelector("#stage76-result-task-switcher");
    const legacyTabs = panel.querySelector("#stage76-result-tabs");
    const overview = panel.querySelector('[data-stage76-result-section="analysis"]');
    if (!switcher || !legacyTabs || !overview) return;

    const header = document.createElement("header");
    header.id = "report-workspace-header";
    header.className = "report-workspace-header";
    header.innerHTML = `<div class="report-heading"><span id="report-mode-badge" class="report-mode-badge">回测分析</span><h2 id="report-task-name">请选择回测任务</h2><p id="report-task-meta">选择已完成任务后展示统一分析报告与原始证据</p></div>
      <div class="report-header-controls">
        <label class="report-benchmark-control"><span>基准</span><select id="report-benchmark-select" disabled><option value="task">任务基准</option></select><small id="report-benchmark-status">随任务结果读取</small></label>
        <label class="report-cost-control" title="成本变化必须重新执行回测，不能在已完成结果上伪重算"><span>成本</span><select id="report-cost-preset" disabled><option>任务实际成本</option></select><small>变更需重新回测</small></label>
        <button type="button" id="report-export-pdf">导出 PDF</button>
      </div>`;
    panel.insertBefore(header, switcher);

    const toolbar = document.createElement("aside");
    toolbar.className = "report-floating-toolbar";
    toolbar.innerHTML = `<strong>图表工具</strong><label>时间窗口 <input id="report-window-size" type="range" min="25" max="100" step="25" value="100"><span id="report-window-value">100%</span></label><span class="report-toolbar-note">图表可导出 SVG / PNG；原始表格可筛选、排序和导出 CSV</span>`;
    panel.insertBefore(toolbar, switcher);

    legacyTabs.classList.add("report-primary-tabs");
    legacyTabs.setAttribute("aria-label", "策略回测分析报告");
    legacyTabs.innerHTML = `<button type="button" data-stage76-result-tab="analysis">回测分析</button><button type="button" data-stage76-result-tab="trades">交易明细</button><button type="button" data-stage76-result-tab="positions">持仓快照</button><button type="button" data-stage76-result-tab="accounts">账户快照</button>`;
    overview.dataset.stage76ResultSection = "analysis";

    const original = Array.from(overview.children);
    overview.innerHTML = `<div id="report-result-overview"></div><details class="report-evidence-drawer"><summary>查看数据版本与底层证据</summary><div id="report-legacy-evidence"></div></details>`;
    const evidence = overview.querySelector("#report-legacy-evidence");
    original.forEach((node) => evidence.append(node));

    panel.addEventListener("click", handleAction);
    panel.addEventListener("input", handleInput);
    panel.addEventListener("click", handleTableAction);

  }

  function updateHeader(task = {}, result = {}) {
    const mode = task.mode || "single";
    const dateWindow = task.date_window || task.config?.date_window || {};
    const summary = result.summary || {};
    const metrics = { ...(summary || {}), ...(result.metrics || {}) };
    const start = dateWindow.start_date || summary.start_date || "-";
    const end = dateWindow.end_date || summary.end_date || "-";
    const badge = document.querySelector("#report-mode-badge");
    const name = document.querySelector("#report-task-name");
    const meta = document.querySelector("#report-task-meta");
    const benchmarkSelect = document.querySelector("#report-benchmark-select");
    const benchmarkStatus = document.querySelector("#report-benchmark-status");
    if (badge) badge.textContent = MODE_LABELS[mode] || task.mode_label || "回测报告";
    if (name) name.textContent = task.name || task.task_id || task.run_id || "回测结果";
    const assetScope = task.symbol || summary.order_book_id || (task.universe_count != null ? `${task.universe_count} 只股票` : "-");
    if (meta) meta.textContent = `${start} — ${end} · ${task.strategy_binding?.strategy_id || summary.strategy_id || "策略"} · ${assetScope}`;
    const benchmark = task.benchmark || task.config?.benchmark || result.benchmark || "未配置";
    if (benchmarkSelect) benchmarkSelect.innerHTML = `<option>${escapeHtml(benchmark)}</option>`;
    if (benchmarkStatus) benchmarkStatus.textContent = benchmarkUsable(task, result, metrics) ? "真实基准已对齐" : "基准行情不可用";
  }

  function renderResult(task = {}, result = {}) {
    const target = document.querySelector("#report-result-overview");
    if (!target) return;
    updateHeader(task, result);
    const mode = task.mode || "single";
    const metrics = { ...(result.summary || {}), ...(result.metrics || {}) };
    const trades = result.trades || [];
    const tradeStats = deriveTradeMetrics(trades);
    const hasBenchmark = benchmarkUsable(task, result, metrics);
    const positions = result.positions || [];
    const accounts = result.accounts || [];
    const equity = normalizeSeries(result.equity_curve || accounts, ["value", "unit_net_value", "total_value"]);
    const drawdown = normalizeSeries(result.drawdown_curve || [], ["value", "drawdown"]);
    const pnlRows = trades.map((row, index) => ({ label: String(index + 1), value: pick(row, ["pnl", "profit", "realized_pnl"], null) }));

    let cards;
    if (mode === "shared-portfolio") {
      const annual = pick(metrics, ["annualized_returns", "annualized_return"]);
      const excess = hasBenchmark ? pick(metrics, ["excess_annualized_return", "excess_return"]) : null;
      cards = [
        metricCard("年化收益率", formatPercent(annual), { tone: tone(annual) }),
        metricCard("最大回撤", formatPercent(pick(metrics, ["max_drawdown"])), { tone: "is-fall" }),
        metricCard("夏普比率", formatNumber(pick(metrics, ["sharpe", "sharpe_ratio"]))),
        metricCard("卡玛比率", formatNumber(pick(metrics, ["calmar", "calmar_ratio"]))),
        metricCard("超额年化收益", formatPercent(excess), { tone: tone(excess) }),
        metricCard("超额最大回撤", formatPercent(pick(metrics, ["excess_max_drawdown"])), { tone: "is-fall" }),
        metricCard("信息比率", formatNumber(pick(metrics, ["information_ratio"]))),
        metricCard("跟踪误差", formatPercent(pick(metrics, ["tracking_error"]))),
      ];
    } else if (mode === "independent-screening") {
      cards = [
        metricCard("股票池", task.universe_count ?? "暂无数据"),
        metricCard("实际建仓", pick(metrics, ["entered_count", "entered"], "暂无数据")),
        metricCard("独立账户", pick(metrics, ["account_count"], task.universe_count ?? "暂无数据")),
        metricCard("结果口径", "横截面统计"),
        metricCard("组合净值", "禁止汇总", { tone: "is-warning", tooltip: "独立账户资金不可合并，因此不提供总净值。" }),
      ];
    } else {
      const annual = pick(metrics, ["annualized_returns", "annualized_return"]);
      const excess = hasBenchmark ? pick(metrics, ["excess_return", "benchmark_excess_return"]) : null;
      const winRate = pick(metrics, ["win_rate"], tradeStats.win_rate);
      cards = [
        metricCard("年化收益率", formatPercent(annual), { tone: tone(annual) }),
        metricCard("最大回撤", formatPercent(pick(metrics, ["max_drawdown"])), { tone: "is-fall" }),
        metricCard("夏普比率", formatNumber(pick(metrics, ["sharpe", "sharpe_ratio"]))),
        metricCard("盈亏比", formatRatio(pick(metrics, ["profit_loss_ratio", "payoff_ratio"], tradeStats.profit_loss_ratio))),
        metricCard("交易次数 / 胜率", `${pick(metrics, ["trade_count"], tradeStats.trade_count)}次 / ${formatPercent(winRate)}`),
        metricCard("超额收益", formatPercent(excess), { tone: tone(excess), meta: hasBenchmark ? "相对任务基准" : "基准行情不可用" }),
      ];
    }

    const warning = mode === "independent-screening" ? independentWarning() : "";
    target.innerHTML = `${section("分析摘要", "核心指标全部来自当前任务结果；红色表示正收益，绿色表示负收益或回撤。", `<div class="report-metric-grid">${cards.join("")}</div>`)}
      ${warning}
      ${section("核心诊断", mode === "single" ? "净值、回撤与交易行为共享同一报告时间范围。" : mode === "shared-portfolio" ? "组合净值、基准与风险按共享资金账户口径解释。" : "仅展示横截面和独立账户证据，不生成汇总净值。", `<div class="report-core-grid">
        ${mode === "independent-screening" ? chart("独立账户结果分布", svgBars(pnlRows, { empty: "正在读取任务级横截面分析证据" })) : chart(mode === "single" ? "策略净值与交易轨迹" : "组合净值", svgLine(equity, { label: "净值曲线", color: COLORS.rise }))}
        ${mode === "independent-screening" ? chart("账户证据覆盖", emptyState("IC 与分层收益只在接口提供真实证据时展示")) : chart("回撤曲线", svgLine(drawdown, { label: "回撤曲线", color: COLORS.fall, area: true, zeroCeiling: true }))}
        ${chart("交易盈亏分布", svgBars(pnlRows, { empty: "当前结果没有逐笔盈亏字段" }))}
      </div>`)}
      ${section("稳定性与账户证据", "年度、月度及参数敏感性在接口提供真实证据时显示；当前先展示持仓与账户时序。", `<div class="report-secondary-grid">
        ${chart("持仓状态与市值", svgLine(normalizeSeries(positions, ["market_value", "quantity"]), { label: "持仓时序", color: COLORS.rise }))}
        ${chart("账户资产轨迹", svgLine(normalizeSeries(accounts, ["total_value", "unit_net_value"]), { label: "账户资产", color: COLORS.rise }))}
      </div><details class="report-optional"><summary>参数敏感性分析</summary>${emptyState("当前任务未返回参数扫描证据，请从参数研究工具生成后再分析。")}</details>`)}`;
  }

  function independentWarning() {
    return `<aside class="report-warning"><strong>⚠️ 重要提示</strong><p>本报告基于“独立账户、无限资金”假设，所有汇总统计仅用于评估信号在横截面上的统计预测能力，不代表可实现的投资组合收益。本报告不提供总的汇总净值曲线。交易明细、持仓快照、账户快照默认对应当前选择的独立账户，不可拼接为总账户或视为实盘账户状态。</p></aside>`;
  }

  function monthlyHeatmap(payload = {}) {
    const rows = payload.rows || [];
    if (!rows.length) return emptyState(payload.reason || "当前报告未返回完整日历收益矩阵");
    const byYear = new Map();
    rows.forEach((row) => {
      const year = String(row.year || String(row.month || "").slice(0, 4));
      if (!byYear.has(year)) byYear.set(year, new Map());
      byYear.get(year).set(Number(row.month_number || String(row.month || "").slice(5, 7)), finite(row.return));
    });
    return `<div class="report-table-wrap report-monthly-heatmap"><table><thead><tr><th>年度</th>${Array.from({ length: 12 }, (_, index) => `<th>${index + 1}月</th>`).join("")}</tr></thead><tbody>${[...byYear].map(([year, months]) => `<tr><th>${escapeHtml(year)}</th>${Array.from({ length: 12 }, (_, index) => { const value = months.get(index + 1); return `<td class="${value === null || value === undefined ? "" : value >= 0 ? "is-rise" : "is-fall"}">${value === null || value === undefined ? "—" : formatPercent(value)}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  function renderSingleAnalysis(target, task, professional = {}, detail = {}, dimensionHtml = "") {
    const metrics = { ...(detail.summary || {}), ...(detail.metrics || {}) };
    const trades = detail.trades || [];
    const tradeStats = deriveTradeMetrics(trades);
    const hasBenchmark = benchmarkUsable(task, detail, metrics);
    const equity = normalizeSeries(detail.equity_curve || detail.account_value_chart || detail.accounts || [], ["value", "unit_net_value", "total_value"]);
    const drawdown = normalizeSeries(detail.drawdown_curve || [], ["value", "drawdown"]);
    const safeDrawdown = drawdown.length ? drawdown : deriveDrawdown(equity);
    const annual = finite(pick(metrics, ["annualized_returns", "annualized_return"]));
    const total = finite(pick(metrics, ["total_returns", "total_return"]));
    const maxDrawdown = finite(pick(metrics, ["max_drawdown"]));
    const volatility = finite(pick(metrics, ["annual_volatility", "volatility"], annualizedVolatility(equity)));
    const calmar = finite(pick(metrics, ["calmar", "calmar_ratio"], annual !== null && maxDrawdown ? annual / Math.abs(maxDrawdown) : null));
    const benchmarkTotal = hasBenchmark ? finite(pick(metrics, ["benchmark_return"])) : null;
    const benchmarkAnnual = annualizeTotalReturn(benchmarkTotal, equity.length);
    const annualDiff = annual !== null && benchmarkAnnual !== null ? annual - benchmarkAnnual : null;
    const excess = hasBenchmark ? finite(pick(metrics, ["excess_return"])) : null;
    const excessDrawdown = normalizeSeries(detail.excess_drawdown_curve || [], ["value", "drawdown"]);
    const excessMaxDrawdown = finite(pick(metrics, ["excess_max_drawdown"], excessDrawdown.length ? Math.min(...excessDrawdown.map((item) => item.value)) : null));
    const drawdownPeriod = drawdownWindow(safeDrawdown);
    const cards = [
      metricCard("年化收益率", formatPercent(annual), { tone: tone(annual), meta: "回测引擎指标" }),
      metricCard("总收益率", formatPercent(total), { tone: tone(total), meta: "起止净值累计收益" }),
      metricCard("最大回撤", formatPercent(maxDrawdown), { tone: "is-fall", meta: drawdownPeriod || "区间无法定位" }),
      volatility === null ? unavailableMetric("年化波动率", "净值点不足") : metricCard("年化波动率", formatPercent(volatility), { meta: "日净值收益 × √252" }),
      metricCard("夏普比率", formatNumber(pick(metrics, ["sharpe", "sharpe_ratio"])), { meta: "回测引擎指标" }),
      calmar === null ? unavailableMetric("卡玛比率", "缺少年化收益或最大回撤") : metricCard("卡玛比率", formatNumber(calmar), { meta: "年化收益 / |最大回撤|" }),
      metricCard("盈亏比", formatRatio(pick(metrics, ["profit_loss_ratio", "payoff_ratio"], tradeStats.profit_loss_ratio)), { meta: "已完成交易口径" }),
      metricCard("交易次数", String(pick(metrics, ["trade_count"], tradeStats.trade_count)), { meta: `${trades.length} 条成交记录` }),
      metricCard("胜率", formatPercent(pick(metrics, ["win_rate"], tradeStats.win_rate)), { meta: "盈利平仓 / 已完成交易" }),
      tradeStats.average_holding_days === null ? unavailableMetric("平均持有天数", "成交无法形成完整买卖配对") : metricCard("平均持有天数", `${formatNumber(tradeStats.average_holding_days, 1)} 天`, { meta: "FIFO、按平仓数量加权" }),
      excess === null ? unavailableMetric("超额收益", hasBenchmark ? "接口未返回同期超额收益" : "基准行情不可用") : metricCard("超额收益", formatPercent(excess), { tone: tone(excess), meta: "策略总收益－基准总收益" }),
      benchmarkAnnual === null ? unavailableMetric("基准年化收益", hasBenchmark ? "缺少可年化的区间证据" : "基准行情不可用") : metricCard("基准年化收益", formatPercent(benchmarkAnnual), { tone: tone(benchmarkAnnual), meta: "按账户有效交易期折算" }),
      annualDiff === null ? unavailableMetric("策略/基准年化差", "缺少可比较的基准年化收益") : metricCard("策略/基准年化差", formatPercent(annualDiff), { tone: tone(annualDiff), meta: "同一有效交易期" }),
      excessMaxDrawdown === null ? unavailableMetric("超额最大回撤", "接口未返回超额净值或超额回撤曲线") : metricCard("超额最大回撤", formatPercent(excessMaxDrawdown), { tone: "is-fall", meta: drawdownWindow(excessDrawdown) || "区间无法定位" }),
    ].join("");
    const yearly = detail.yearly_returns || detail.yearly_return_chart || [];
    const realizedRows = tradeStats.realized.map((value, index) => ({ label: String(index + 1), value }));
    target.innerHTML = `<div class="report-analysis-shell">
      ${section("单品种测试报告", "收益、风险、交易与基准指标均标注真实来源；无法计算的指标明确显示不可用。", `<div class="report-metric-grid report-metric-grid-four">${cards}</div>`)}
      ${section("全景诊断", "K线数据缺失时以真实净值与成交证据替代，不绘制伪造行情。", `<div class="report-panorama">
        ${chart("策略净值与交易时间轴", svgLine(equity, { label: "策略净值", color: COLORS.rise }), "当前接口未提供 OHLC 时仅显示账户净值")}
        ${chart("回撤曲线", svgLine(safeDrawdown, { label: "回撤", color: COLORS.fall, area: true, zeroCeiling: true }), drawdownPeriod ? `最大回撤区间：${drawdownPeriod}` : "")}
        ${chart("持仓状态与浮动盈亏", svgLine(normalizeSeries(detail.positions || [], ["unrealized_pnl", "market_value", "quantity"]), { label: "持仓与浮盈", color: COLORS.rise }))}
      </div>`)}
      ${collapsibleSection("收益稳定性与参数检验", "年度收益与已完成交易盈亏来自当前 Run；月度和参数扫描缺失时不补演示值。", `<div class="report-secondary-grid">
        ${chart("年度收益", svgBars(yearly, { empty: "当前报告未返回年度收益序列" }))}
        ${chart("已完成交易盈亏分布", svgBars(realizedRows, { empty: "成交记录不足以形成已实现盈亏分布" }))}
        ${chart("日收益分布", svgBars(equity.slice(1).map((item, index) => ({ label: String(index + 1), value: equity[index]?.value ? item.value / equity[index].value - 1 : null })), { empty: "净值点不足，无法生成日收益分布" }))}
        ${chart("月度收益热力图", monthlyHeatmap(detail.monthly_return_heatmap || {}))}
      </div>${dataTable((detail.market_regimes || {}).rows || [], [{ key: "regime", label: "市场状态" }, { key: "sample_size", label: "样本" }, { key: "portfolio_return", label: "策略收益" }, { key: "benchmark_return", label: "基准收益" }, { key: "excess_return", label: "超额收益" }], { empty: (detail.market_regimes || {}).reason || "暂无无前视市场环境证据" })}
      ${dataTable((detail.robustness || {}).segments || [], [{ key: "segment", label: "区间" }, { key: "start_date", label: "开始" }, { key: "end_date", label: "结束" }, { key: "annualized_return", label: "年化收益" }, { key: "max_drawdown", label: "最大回撤" }, { key: "sharpe", label: "夏普" }], { empty: (detail.robustness || {}).reason || "暂无样本外分段证据" })}
      <details class="report-optional"><summary>参数敏感性分析</summary>${(detail.parameter_sensitivity || {}).status === "ready" ? `<pre class="report-json-evidence">${escapeHtml(JSON.stringify(detail.parameter_sensitivity, null, 2))}</pre>` : emptyState((detail.parameter_sensitivity || {}).reason || "请先生成参数扫描结果；报告不使用演示值。")}</details>`)}
      <details class="report-evidence-drawer"><summary>7 维评估与证据</summary>${dimensionHtml}</details>
    </div>`;
    bindTables(target);
  }

  function renderBatchAnalysis(target, task, report = {}, runHtml = "") {
    const scope = report.sample_scope || {};
    const factor = report.factor_analysis || {};
    const distribution = report.distribution || {};
    const ic = report.ic_analysis || {};
    const layers = report.layered_returns || {};
    const signalCount = finite(pick(report, ["signal_summary.total_signal_stock_count"], pick(scope, ["entered_count", "processed_count"])));
    const crossWinRate = finite(pick(distribution, ["positive_probability"]));
    const crossProfitLoss = finite(pick(distribution, ["gain_loss_ratio"]));
    const icMean = finite(pick(ic, ["mean", "ic_mean"]));
    const icT = finite(pick(ic, ["newey_west_t", "nw_t", "t_stat"]));
    const icir = finite(pick(ic, ["icir", "information_ratio"]));
    const rankIc = finite(pick(ic, ["rank_mean", "rank_ic_mean"]));
    const monoP = finite(pick(layers, ["monotonicity_p_value", "monotonicity_p"]));
    const layerUnavailableReason = layers.reason === "at_least_five_valid_symbols_per_period_required" ? "每期至少需要 5 个有效标的；当前样本不足" : "缺少 Q1—Q5 分组收益序列";
    const cards = [
      icMean === null ? unavailableMetric("IC均值", "缺少逐期因子值与未来收益") : metricCard("IC均值", formatNumber(icMean), { tone: tone(icMean), meta: `${ic.period_count || 0} 个日度横截面` }),
      icT === null ? unavailableMetric("Newey-West IC t值", "缺少逐期 IC 序列") : metricCard("Newey-West IC t值", formatNumber(icT), { meta: "HAC 自相关稳健标准误" }),
      icir === null ? unavailableMetric("ICIR", "缺少逐期 IC 均值与标准差") : metricCard("ICIR", formatNumber(icir), { meta: "日度 IC，按 √252 年化" }),
      rankIc === null ? unavailableMetric("Rank IC均值", "缺少逐期横截面秩相关证据") : metricCard("Rank IC均值", formatNumber(rankIc), { tone: tone(rankIc), meta: "Spearman 秩相关" }),
      monoP === null ? unavailableMetric("分层单调性p值", layerUnavailableReason) : metricCard("分层单调性p值", formatNumber(monoP, 4)),
      finite(pick(ic, ["positive_ratio"])) === null ? unavailableMetric("IC正数比率", "缺少逐期 IC 序列") : metricCard("IC正数比率", formatPercent(pick(ic, ["positive_ratio"]))),
      finite(pick(ic, ["stddev", "std", "ic_std"])) === null ? unavailableMetric("IC标准差", "缺少逐期 IC 序列") : metricCard("IC标准差", formatNumber(pick(ic, ["stddev", "std", "ic_std"]))),
      signalCount === null ? unavailableMetric("总信号股票数", "任务范围未返回实际建仓数量") : metricCard("总信号股票数", String(signalCount), { meta: "曾出现正持仓权重的股票" }),
      finite(pick(report, ["signal_summary.average_per_period"])) === null ? unavailableMetric("平均每期信号数", "缺少按期信号明细") : metricCard("平均每期信号数", formatNumber(pick(report, ["signal_summary.average_per_period"]), 1)),
      finite(pick(layers, ["q1_annualized"])) === null ? unavailableMetric("Q1年化收益", layerUnavailableReason) : metricCard("Q1年化收益", formatPercent(pick(layers, ["q1_annualized"])), { tone: tone(pick(layers, ["q1_annualized"])) }),
      finite(pick(layers, ["q5_annualized"])) === null ? unavailableMetric("Q5年化收益", layerUnavailableReason) : metricCard("Q5年化收益", formatPercent(pick(layers, ["q5_annualized"])), { tone: tone(pick(layers, ["q5_annualized"])) }),
      finite(pick(layers, ["long_short_annualized"])) === null ? unavailableMetric("多空年化收益", layerUnavailableReason) : metricCard("多空年化收益", formatPercent(pick(layers, ["long_short_annualized"])), { tone: tone(pick(layers, ["long_short_annualized"])) }),
      crossWinRate === null ? unavailableMetric("横截面平均胜率", "缺少任务级收益分布") : metricCard("横截面平均胜率", formatPercent(crossWinRate), { meta: `${distribution.sample_size || 0} 个独立账户样本` }),
      crossProfitLoss === null ? unavailableMetric("横截面盈亏比", "样本中缺少盈利或亏损账户") : metricCard("横截面盈亏比", formatNumber(crossProfitLoss), { meta: "平均正收益 / |平均负收益|" }),
    ].join("");
    const histogram = distribution.histogram || [];
    const icSeries = ic.series || [];
    const layerSeries = layers.series || [];
    const layerReason = `${layerUnavailableReason}，Q1—Q5 保持不可用`;
    const failures = (report.failure_summary || {}).items || [];
    const coverage = finite(scope.coverage_ratio);

    target.innerHTML = `<div class="report-analysis-shell">
      ${section("独立账户批量回测报告", `股票池 ${scope.universe_count ?? "-"} · 成功 ${scope.successful_count ?? "-"} · 实际建仓 ${scope.entered_count ?? "-"} · 失败 ${scope.failed_count ?? 0} · 覆盖率 ${coverage === null ? "-" : formatPercent(coverage)}`, `<div class="report-metric-grid report-metric-grid-four">${cards}</div>`)}
      ${independentWarning()}
      ${failures.length ? section("失败股票与诊断", report.selection_bias_warning || "失败股票不按零收益计入绩效。", dataTable(failures, [
        { key: "symbol", label: "股票" }, { key: "name", label: "名称" },
        { key: "error_stage", label: "失败阶段" }, { key: "error_code", label: "错误码" },
        { key: "error_message", label: "错误信息" }, { key: "retryable", label: "可重试" },
      ], { empty: "无失败股票" })) : ""}
      ${section("横截面诊断", "IC 使用收盘后真实持仓权重与下一交易日复权收益，严格按 t→t+1 对齐；绝不提供总汇总净值曲线。", `<div class="report-panorama">
        ${chart("Q1—Q5 分层累计收益", layerSeries.length ? svgMultiLine([1, 2, 3, 4, 5].map((index) => ({ label: `Q${index}`, color: [COLORS.rise, "#f39c12", COLORS.neutral, "#3498db", COLORS.fall][index - 1], series: normalizeSeries(layerSeries, [`q${index}`]) })), { empty: layerReason }) : emptyState(layerReason))}
        ${chart("日度 IC 与累计 IC", svgMultiLine([{ label: "日度 IC", color: COLORS.neutral, series: normalizeSeries(icSeries, ["ic"]) }, { label: "累计 IC", color: COLORS.rise, series: normalizeSeries(icSeries, ["cumulative_ic"]) }], { empty: "有效横截面少于 3 个或信号无差异，IC 不可计算" }), ic.status === "ready" ? `${ic.period_count || 0} 期 · 横截面 ${ic.minimum_cross_section_size || 0}—${ic.maximum_cross_section_size || 0} 个标的` : "")}
        ${chart("多空净值与回撤", layerSeries.length ? svgMultiLine([{ label: "Q1-Q5 多空净值", color: COLORS.rise, series: normalizeSeries(layerSeries, ["long_short"]) }, { label: "多空回撤", color: COLORS.fall, series: deriveDrawdown(normalizeSeries(layerSeries, ["long_short"])) }], { empty: layerReason }) : emptyState(layerReason))}
      </div>`)}
      ${collapsibleSection("普适性与稳定性分析", "已实现部分展示真实任务级收益分布与特征关系；这些关系只描述样本关联，不标记为 IC。", `<div class="report-secondary-grid">
        ${chart("实际建仓股票收益分布", svgBars(histogram.map((row) => ({ label: pick(row, ["label", "bucket"], "-"), value: pick(row, ["count", "value"], null) })), { empty: "暂无实际建仓收益分布" }))}
        ${chart("行业—IC", dataTable((report.industry_analysis || {}).industry_rows || [], [{ key: "industry", label: "行业" }, { key: "period_count", label: "期数" }, { key: "ic_mean", label: "IC均值" }, { key: "icir", label: "ICIR" }], { empty: (report.industry_analysis || {}).reason || "暂无逐期行业IC证据" }))}
      </div>${dataTable((report.market_regimes || {}).rows || [], [{ key: "regime", label: "市场环境" }, { key: "sample_size", label: "样本" }, { key: "ic_mean", label: "IC均值" }, { key: "rank_ic_mean", label: "Rank IC" }, { key: "long_short_return", label: "多空收益" }], { empty: (report.market_regimes || {}).reason || "暂无市场环境分段证据" })}
      ${dataTable(factor.numeric_relationships || [], [{ key: "label", label: "特征" }, { key: "sample_size", label: "样本" }, { key: "spearman", label: "Spearman" }, { key: "interpretation", label: "解释边界" }], { empty: "暂无数值特征与账户收益关系证据" })}
      <details class="report-optional"><summary>原始因子与策略暴露对照</summary>${(report.raw_factor_analysis || {}).status === "ready" ? `<pre class="report-json-evidence">${escapeHtml(JSON.stringify(report.raw_factor_analysis, null, 2))}</pre>` : emptyState((report.raw_factor_analysis || {}).reason || "历史任务未保存原始分数")}</details>`)}
      <details class="report-evidence-drawer" open><summary>任务内单品种诊断</summary>${runHtml}</details>
    </div>`;
    bindTables(target);
  }

  function renderPortfolioAnalysis(target, task, report = {}, dimensionHtml = "") {
    const detail = report.run_detail || {};
    const metrics = { ...(detail.summary || {}), ...(detail.metrics || {}) };
    const hasBenchmark = benchmarkUsable(task, detail, metrics);
    const equity = normalizeSeries(detail.equity_curve || detail.account_value_chart || detail.accounts || [], ["unit_net_value", "value", "total_value"]);
    const drawdown = normalizeSeries(detail.drawdown_curve || [], ["value", "drawdown"]);
    const safeDrawdown = drawdown.length ? drawdown : deriveDrawdown(equity);
    const benchmark = normalizeSeries(detail.benchmark_curve || [], ["value", "unit_net_value"]);
    const excessCurve = normalizeSeries(detail.excess_curve || [], ["value", "excess_return"]);
    const excessDrawdown = excessCurve.length ? deriveDrawdown(excessCurve) : [];
    const positions = detail.positions || detail.position_exposure_chart || [];
    const trades = detail.trades || detail.trade_activity_chart || [];
    const yearly = detail.yearly_returns || detail.yearly_return_chart || [];
    const tradeStats = deriveTradeMetrics(detail.trades || []);
    const annual = finite(pick(metrics, ["annualized_returns", "annualized_return"]));
    const total = finite(pick(metrics, ["total_returns", "total_return"]));
    const maxDrawdown = finite(pick(metrics, ["max_drawdown"]));
    const volatility = finite(pick(metrics, ["annual_volatility", "volatility"], annualizedVolatility(equity)));
    const excess = hasBenchmark ? finite(pick(metrics, ["excess_annualized_return", "excess_return"])) : null;
    const excessMaxDrawdown = finite(pick(metrics, ["excess_max_drawdown"], excessDrawdown.length ? Math.min(...excessDrawdown.map((item) => item.value)) : null));
    const capitalSeries = normalizeSeries(detail.accounts || detail.account_value_chart || [], ["total_value", "value", "unit_net_value"]);
    const turnover = deriveAnnualizedTurnover(detail.trades || [], capitalSeries);
    const coverage = deriveDateCoverage(equity, benchmark);
    const rejected = finite(pick(metrics, ["rejected_order_count"], 0));
    const fills = finite(pick(metrics, ["trade_fill_count"], (detail.trades || []).length));
    const rejectedRatio = rejected !== null && fills !== null && rejected + fills > 0 ? rejected / (rejected + fills) : null;
    const grade = String(pick(report, ["data_quality_gate.evidence_quality.grade"], "")).toLowerCase();
    const gradeLabel = ({ high: "高", medium: "中", low: "低" })[grade] || null;
    const cards = [
      metricCard("年化收益率", formatPercent(annual), { tone: tone(annual), meta: "组合账户口径" }),
      metricCard("总收益率", formatPercent(total), { tone: tone(total), meta: "起止净值累计收益" }),
      excess === null ? unavailableMetric("超额年化收益", hasBenchmark ? "缺少同期超额年化指标" : "基准行情不可用") : metricCard("超额年化收益", formatPercent(excess), { tone: tone(excess), meta: "相对任务基准" }),
      metricCard("最大回撤", formatPercent(maxDrawdown), { tone: "is-fall", meta: drawdownWindow(safeDrawdown) || "区间无法定位" }),
      volatility === null ? unavailableMetric("年化波动率", "净值点不足") : metricCard("年化波动率", formatPercent(volatility), { meta: "引擎指标或日净值推导" }),
      excessMaxDrawdown === null ? unavailableMetric("超额最大回撤", "缺少超额净值/回撤证据") : metricCard("超额最大回撤", formatPercent(excessMaxDrawdown), { tone: "is-fall", meta: drawdownWindow(excessDrawdown) || "区间无法定位" }),
      metricCard("夏普比率", formatNumber(pick(metrics, ["sharpe", "sharpe_ratio"])), { meta: "回测引擎指标" }),
      metricCard("卡玛比率", formatNumber(pick(metrics, ["calmar", "calmar_ratio"])), { meta: "年化收益 / |最大回撤|" }),
      hasBenchmark ? metricCard("信息比率", formatNumber(pick(metrics, ["information_ratio"])), { meta: "超额收益 / 跟踪误差" }) : unavailableMetric("信息比率", "基准行情不可用"),
      metricCard("盈亏比", formatRatio(pick(metrics, ["profit_loss_ratio", "payoff_ratio"], tradeStats.profit_loss_ratio)), { meta: "已完成交易口径" }),
      metricCard("胜率", formatPercent(pick(metrics, ["win_rate"], tradeStats.win_rate)), { meta: "盈利平仓 / 已完成交易" }),
      metricCard("交易次数", String(pick(metrics, ["trade_count"], tradeStats.trade_count)), { meta: `${(detail.trades || []).length} 条成交记录` }),
      turnover === null ? unavailableMetric("双边年化换手率", "缺少原始成交额或账户净值") : metricCard("双边年化换手率", formatPercent(turnover), { meta: "买卖成交额合计 / 平均资产" }),
      tradeStats.average_holding_days === null ? unavailableMetric("平均持有天数", "成交无法形成完整买卖配对") : metricCard("平均持有天数", `${formatNumber(tradeStats.average_holding_days, 1)} 天`, { meta: "FIFO、按平仓数量加权" }),
      coverage === null ? unavailableMetric("有效日期覆盖率", "缺少可对齐的基准时间轴") : metricCard("有效日期覆盖率", formatPercent(coverage), { meta: `${equity.length} 个净值点 / ${benchmark.length} 个基准点` }),
      rejectedRatio === null ? unavailableMetric("无法成交尝试占比", "缺少成交与拒绝计数") : metricCard("无法成交尝试占比", formatPercent(rejectedRatio), { tone: rejectedRatio > 0 ? "is-warning" : "is-rise", meta: `${rejected || 0} 次拒绝 / ${(rejected || 0) + (fills || 0)} 次尝试证据` }),
      finite(pick(metrics, ["simulated_vwap_deviation", "vwap_deviation"])) === null ? unavailableMetric("模拟成交/VWAP偏离", "未保存逐笔市场 VWAP 基准") : metricCard("模拟成交/VWAP偏离", formatPercent(pick(metrics, ["simulated_vwap_deviation", "vwap_deviation"]))),
      gradeLabel === null ? unavailableMetric("证据等级", "数据质量门禁未返回等级") : metricCard("证据等级", gradeLabel, { tone: grade === "high" ? "is-rise" : grade === "medium" ? "is-warning" : "is-fall", meta: "数据质量门禁" }),
    ].join("");
    target.innerHTML = `<div class="report-analysis-shell">
      ${section("投资组合回测报告", "共享资金账户的投资业绩与执行可靠性审计；每项指标标明口径或缺失原因。", `<div class="report-metric-grid report-metric-grid-four">${cards}</div>`)}
      ${section("双净值全景图", "组合、基准和超额收益在同一真实时间轴上解释。", `<div class="report-panorama">
        ${chart("组合净值、基准与超额净值", svgMultiLine([{ label: "组合净值", color: COLORS.rise, series: equity }, { label: "基准净值", color: COLORS.neutral, dash: "8 5", series: benchmark }, { label: "超额净值", color: COLORS.fall, series: excessCurve }], { empty: "当前报告没有可用净值证据" }), hasBenchmark ? "三条曲线来自同一任务时间轴" : "基准行情不可用，仅展示组合净值")}
        ${chart("组合回撤", svgLine(safeDrawdown, { label: "组合回撤", color: COLORS.fall, area: true, zeroCeiling: true }), drawdownWindow(safeDrawdown) ? `最大回撤区间：${drawdownWindow(safeDrawdown)}` : "")}
        ${chart("滚动一年超额收益", svgLine(normalizeSeries(detail.rolling_excess_returns || [], ["value", "excess_return"]), { label: "滚动超额", color: COLORS.rise, zeroFloor: true, zeroCeiling: true }), "样本不足 252 个有效交易日时不可用")}
      </div>`)}
      ${collapsibleSection("风险与压力测试", "年度、月度、市场环境与行业贡献只展示已保存的真实证据。", `<div class="report-secondary-grid">
        ${chart("年度收益：组合与基准", svgBars(yearly, { empty: "当前报告未返回年度收益序列" }))}
        ${chart("月度收益热力图", monthlyHeatmap(detail.monthly_return_heatmap || {}))}
      </div>${dataTable(report.portfolio_sections?.market_regimes || [], [{ key: "regime", label: "市场状态" }, { key: "portfolio_return", label: "组合收益" }, { key: "benchmark_return", label: "基准收益" }, { key: "excess_return", label: "超额收益" }, { key: "max_drawdown", label: "最大回撤" }], { empty: "暂无市场环境分段数据" })}
      <details class="report-optional" open><summary>收益归因证据</summary><pre class="report-json-evidence">${escapeHtml(JSON.stringify(report.portfolio_sections?.attribution || report.portfolio_sections || {}, null, 2))}</pre></details>`)}
      ${collapsibleSection("持仓与交易归因", "持仓集中度、盈亏贡献和交易行为来自共享资金账户。", `<div class="report-panorama">
        ${chart("持仓数量", svgLine(normalizeSeries(positions, ["position_count", "quantity"]), { color: COLORS.neutral }))}
        ${chart("持仓市值", svgLine(normalizeSeries(positions, ["position_market_value", "market_value"]), { color: COLORS.rise, area: true }))}
        ${chart("已实现交易盈亏", svgBars(tradeStats.realized.map((value, index) => ({ label: String(index + 1), value })), { empty: "成交记录不足以形成已实现盈亏分布" }))}
      </div>`)}
      ${collapsibleSection("参数敏感性与执行可靠性", "成本敏感性、极端回撤、过拟合检验与成交偏离只展示已有证据。", `<div class="report-secondary-grid">
        ${chart("成本敏感性矩阵", dataTable(report.portfolio_sections?.cost_capacity_stress?.cost_matrix || [], [{ key: "commission_multiplier", label: "佣金倍数" }, { key: "slippage_multiplier", label: "滑点倍数" }, { key: "analytical_cost", label: "分析成本" }, { key: "analytical_return_after_cost", label: "成本后收益" }], { empty: "当前报告未返回成本网格结果" }))}
        ${chart("参数敏感性与样本外表现", dataTable(report.portfolio_sections?.robustness?.segments || [], [{ key: "segment", label: "区间" }, { key: "annualized_return", label: "年化收益" }, { key: "max_drawdown", label: "最大回撤" }, { key: "sharpe", label: "夏普" }], { empty: "当前报告未返回样本内外对比证据" }))}
      </div>${dataTable(report.portfolio_sections?.cost_capacity_stress?.capacity?.scenarios || [], [{ key: "capital_multiplier", label: "资金倍数" }, { key: "projected_max_participation", label: "预计最大成交量占比" }, { key: "within_10pct_volume_limit", label: "10%容量约束内" }], { empty: report.portfolio_sections?.cost_capacity_stress?.capacity?.reason || "暂无容量证据" })}`)}
      <details class="report-evidence-drawer"><summary>7 维评估与组合证据</summary>${dimensionHtml}</details>
    </div>`;
    bindTables(target);
  }

  function renderRawTables(result = {}, mode = "single") {
    const tradesTarget = document.querySelector("#stage76-result-trades");
    const positionsTarget = document.querySelector("#stage76-result-positions");
    const accountsTarget = document.querySelector("#stage76-result-accounts");
    const independent = mode === "independent-screening";
    if (tradesTarget) renderTradePanel(tradesTarget, result, mode);
    if (positionsTarget) positionsTarget.innerHTML = `${independent ? '<div class="report-inline-note">各账户独立，此表仅为信号分布参考；不展示汇总总资产。</div>' : ""}${dataTable(result.positions || [], [
      { key: "snapshot_time", label: "时间" }, { key: "account_id", label: "账户 ID" }, { key: "order_book_id", label: "股票" },
      { key: "quantity", label: "数量" }, { key: "avg_price", label: "成本价" }, { key: "price", label: "现价" },
      { key: "unrealized_pnl", label: "浮动盈亏" }, { key: "weight", label: "权重" },
    ])}`;
    if (accountsTarget) accountsTarget.innerHTML = `${independent ? independentWarning() : ""}${dataTable(result.accounts || [], [
      { key: "snapshot_time", label: "时间" }, { key: "account_id", label: "账户 ID" }, { key: "total_value", label: "总资产" },
      { key: "cash", label: "现金" }, { key: "market_value", label: "持仓市值" }, { key: "daily_return", label: "当日收益率" },
      { key: "unit_net_value", label: "累计净值" },
    ])}`;
    bindTables(document.querySelector(".report-workspace"));
  }


  function renderTradePanel(target, result, mode) {
    const trades = result.trades || [];
    const symbols = [...new Set(trades.map((row) => pick(row, ["order_book_id", "symbol"], "")).filter(Boolean))];
    const selected = target.dataset.selectedSymbol && symbols.includes(target.dataset.selectedSymbol) ? target.dataset.selectedSymbol : symbols[0] || "";
    const selectedTrades = selected ? trades.filter((row) => pick(row, ["order_book_id", "symbol"], "") === selected) : trades;
    const selector = symbols.length > 1 ? `<label class="report-symbol-picker"><span>标的</span><select data-report-trade-symbol>${symbols.map((symbol) => `<option value="${escapeHtml(symbol)}" ${symbol === selected ? "selected" : ""}>${escapeHtml(symbol)}</option>`).join("")}</select></label>` : "";
    const priceRows = (result.price_bars || result.daily_prices || result.ohlc || []).filter((row) => {
      const symbol = pick(row, ["order_book_id", "symbol"], selected);
      return !selected || !symbol || symbol === selected;
    });
    target.innerHTML = `${selector}${chart("K线与买卖点", tradePriceChart(priceRows, selectedTrades), priceRows.length ? "买入红色、卖出绿色" : "当前结果未返回 OHLC 行情，不使用成交价伪造 K 线")}
      ${dataTable(selectedTrades, [
        { key: "trade_time", label: "时间" }, { key: "account_id", label: "账户 ID" }, { key: "order_book_id", label: "股票" },
        { key: "side", label: "方向" }, { key: "price", label: "价格" }, { key: "quantity", label: "数量" },
        { key: "amount", label: "成交额" }, { key: "commission", label: "手续费" }, { key: "pnl", label: "盈亏" },
      ])}`;
    target.querySelector("[data-report-trade-symbol]")?.addEventListener("change", (event) => {
      target.dataset.selectedSymbol = event.target.value;
      renderTradePanel(target, result, mode);
      bindTables(target);
    });
  }

  function tradePriceChart(rows, trades) {
    const bars = rows.map((row) => ({
      date: String(pick(row, ["trade_date", "date", "datetime"], "")).slice(0, 10), open: finite(pick(row, ["open"], null)),
      high: finite(pick(row, ["high"], null)), low: finite(pick(row, ["low"], null)), close: finite(pick(row, ["close"], null)),
    })).filter((row) => [row.open, row.high, row.low, row.close].every((value) => value !== null));
    if (!bars.length) return emptyState("暂无可用 K 线数据；下方成交明细仍可查看");
    const width = 920, height = 230, pad = 34;
    const max = Math.max(...bars.map((row) => row.high)), min = Math.min(...bars.map((row) => row.low)), span = max - min || 1;
    const step = (width - pad * 2) / Math.max(bars.length, 1), y = (value) => pad + (max - value) / span * (height - pad * 2);
    const candles = bars.map((row, index) => {
      const x = pad + index * step + step / 2, color = row.close >= row.open ? COLORS.rise : COLORS.fall;
      return `<line x1="${x}" x2="${x}" y1="${y(row.high)}" y2="${y(row.low)}" stroke="${color}"/><rect x="${x - Math.max(1, step * .25)}" y="${Math.min(y(row.open), y(row.close))}" width="${Math.max(2, step * .5)}" height="${Math.max(2, Math.abs(y(row.open) - y(row.close)))}" fill="${color}"><title>${escapeHtml(row.date)} O:${row.open} H:${row.high} L:${row.low} C:${row.close}</title></rect>`;
    }).join("");
    const byDate = new Map(bars.map((row, index) => [row.date, index]));
    const markers = trades.map((trade) => {
      const date = String(pick(trade, ["trade_time", "datetime", "date"], "")).slice(0, 10), index = byDate.get(date), price = finite(pick(trade, ["price"], null));
      if (index === undefined || price === null) return "";
      const x = pad + index * step + step / 2, side = String(pick(trade, ["side", "direction"], "")).toUpperCase(), buy = side.includes("BUY") || side.includes("买"), color = buy ? COLORS.rise : COLORS.fall, py = y(price);
      return `<path d="M ${x} ${py + (buy ? 10 : -10)} l -5 ${buy ? 8 : -8} h 10 z" fill="${color}"><title>${escapeHtml(date)} ${buy ? "买入" : "卖出"} ${price}</title></path>`;
    }).join("");
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="K线与买卖点">${candles}${markers}</svg>`;
  }
  function handleInput(event) {
    if (event.target.id === "report-window-size") {
      const percent = Number(event.target.value);
      const output = document.querySelector("#report-window-value");
      if (output) output.textContent = `${percent}%`;
      document.querySelectorAll(".report-core-grid svg, .report-panorama svg").forEach((svg) => {
        const base = (svg.dataset.baseViewBox || svg.getAttribute("viewBox") || "0 0 920 240").split(/\s+/).map(Number);
        svg.dataset.baseViewBox = base.join(" ");
        const visibleWidth = base[2] * percent / 100;
        svg.setAttribute("viewBox", `${base[0] + base[2] - visibleWidth} ${base[1]} ${visibleWidth} ${base[3]}`);
      });
    }
    if (event.target.id === "report-cost-multiplier") {
      const output = document.querySelector("#report-cost-value");
      if (output) output.textContent = `${Number(event.target.value).toFixed(2)}×`;
    }
  }

  function handleAction(event) {
    if (event.target.closest("#report-export-pdf")) {
      window.print();
      return;
    }
    const button = event.target.closest("[data-report-download]");
    if (!button) return;
    const card = button.closest(".report-chart-card");
    const svg = card?.querySelector("svg");
    if (!svg) return;
    downloadChart(svg, button.dataset.reportDownload, card.querySelector("h4")?.textContent || "chart");
  }

  function downloadChart(svg, format, name) {
    const source = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
    if (format === "svg") return downloadBlob(blob, `${name}.svg`);
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 1200; canvas.height = 360;
      const context = canvas.getContext("2d");
      context.fillStyle = "#ffffff"; context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob((png) => png && downloadBlob(png, `${name}.png`), "image/png");
    };
    image.src = url;
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = filename; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function handleTableAction(event) {
    const sort = event.target.closest("[data-table-sort]");
    if (sort) {
      const table = sort.closest("table");
      const index = Array.from(sort.closest("tr").children).indexOf(sort.closest("th"));
      const body = table.querySelector("tbody");
      const rows = Array.from(body.rows);
      const ascending = sort.dataset.direction !== "asc";
      rows.sort((a, b) => {
        const av = a.cells[index]?.dataset.value || "";
        const bv = b.cells[index]?.dataset.value || "";
        const an = finite(av), bn = finite(bv);
        const result = an !== null && bn !== null ? an - bn : av.localeCompare(bv, "zh-CN");
        return ascending ? result : -result;
      }).forEach((row) => body.append(row));
      sort.dataset.direction = ascending ? "asc" : "desc";
      return;
    }
    const exportButton = event.target.closest("[data-table-export]");
    if (exportButton) {
      const table = document.querySelector(`[data-report-table="${CSS.escape(exportButton.dataset.tableExport)}"] table`);
      if (!table) return;
      const csv = Array.from(table.rows).filter((row) => !row.hidden).map((row) => Array.from(row.cells).map((cell) => `"${cell.textContent.trim().replaceAll('"', '""')}"`).join(",")).join("\n");
      downloadBlob(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }), "backtest-data.csv");
    }
  }

  function bindTables(root) {
    root?.querySelectorAll("[data-table-filter]").forEach((input) => {
      if (input.dataset.bound === "true") return;
      input.dataset.bound = "true";
      input.addEventListener("input", () => {
        const query = input.value.trim().toLowerCase();
        const table = root.querySelector(`[data-report-table="${CSS.escape(input.dataset.tableFilter)}"]`);
        table?.querySelectorAll("tbody tr").forEach((row) => { row.hidden = Boolean(query && !row.textContent.toLowerCase().includes(query)); });
      });
    });
  }

  window.ReportUI = {
    COLORS,
    mount,
    updateHeader,
    renderResult,
    renderRawTables,
    renderSingleAnalysis,
    renderBatchAnalysis,
    renderPortfolioAnalysis,
    metricCard,
    dataTable,
    independentWarning,
    bindTables,
  };
})();
