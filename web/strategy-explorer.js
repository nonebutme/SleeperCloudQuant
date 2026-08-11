(() => {
  "use strict";
  const state = { strategies: [], runs: [], panels: new Map(), ranked: [], versions: [], selected: null, view: "leaderboard", tab: "oos" };
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]);
  const num = (v, d = 0) => Number.isFinite(Number(v)) ? Number(v) : d;
  const pct = (v) => `${(num(v) * 100).toFixed(2)}%`;

  async function api(path) { const r = await fetch(path, { headers: { Accept: "application/json" } }); const p = await r.json().catch(() => ({})); if (!r.ok) throw new Error(p.detail || `请求失败 (${r.status})`); return p; }
  function ensureShell() {
    if (!$('link[href^="/strategy-explorer.css"]')) { const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "/strategy-explorer.css?v=1"; document.head.append(l); }
    const shell = $("#strategy-pc-workbench"); if (!shell || $("#strategy-explorer")) return Boolean(shell);
    const root = document.createElement("section"); root.id = "strategy-explorer"; root.className = "strategy-explorer";
    root.innerHTML = '<div id="se-directory"></div><div id="se-detail" hidden></div>';
    shell.prepend(root); bind(); return true;
  }
  function bind() {
    $("#strategy-explorer").addEventListener("click", (e) => {
      const view = e.target.closest("[data-se-view]"); if (view) { state.view = view.dataset.seView; renderDirectory(); return; }
      const card = e.target.closest("[data-se-strategy]"); if (card) openDetail(card.dataset.seStrategy).catch(showError);
      const tab = e.target.closest("[data-se-tab]"); if (tab) { state.tab = tab.dataset.seTab; renderDetail(); }
      if (e.target.closest("#se-back")) showDirectory();
    });
  }
  async function load() {
    const [strategies, runs] = await Promise.all([api("/api/backtest/strategies"), api("/api/backtest/runs")]);
    state.strategies = strategies.strategies || [];
    state.runs = (runs.runs || []).filter((r) => r.status === "completed");
    const latest = new Map(); state.runs.forEach((r) => { const id = r.strategy_id || r.strategy_name; if (id && !latest.has(id)) latest.set(id, r); });
    const entries = [...latest.entries()].slice(0, 30);
    await Promise.all(entries.map(async ([id, run]) => { try { const p = await api(`/api/backtest/results/${encodeURIComponent(run.run_id)}/panel`); state.panels.set(id, p.result || {}); } catch (_) {} }));
    state.ranked = state.strategies.map((s) => rankRow(s, latest.get(s.strategy_id), state.panels.get(s.strategy_id))).sort((a, b) => b.score - a.score);
    renderDirectory();
  }
  function rankRow(strategy, run, panel) {
    const curve = panel?.equity_curve || []; const metrics = panel?.metrics || {}; const end = curve.at(-1)?.value;
    const endDate = new Date(curve.at(-1)?.snapshot_time || curve.at(-1)?.date || run?.end_date || 0); const cutoff = new Date(endDate); cutoff.setMonth(cutoff.getMonth() - 3);
    const windowStart = curve.find((point) => new Date(point.snapshot_time || point.date || 0) >= cutoff) || curve[0];
    const ret = windowStart?.value ? end / windowStart.value - 1 : num(metrics.total_returns); const days = run?.start_date && run?.end_date ? Math.max(1, (new Date(run.end_date) - new Date(run.start_date)) / 86400000) : 0;
    const sharpe = num(metrics.sharpe); return { strategy, run, panel, return3m: ret, sharpe, score: sharpe * Math.min(days / 365, 1), curve };
  }
  function renderDirectory() {
    const root = $("#se-directory"); $("#se-detail").hidden = true; root.hidden = false; $("#strategy-pc-workbench").classList.remove("se-detail-mode", "se-code-mode");
    root.innerHTML = `<header class="se-hero"><div><span class="se-kicker">STRATEGY EXPLORER · LOCAL OOS CANDIDATES</span><h3>策略工作台</h3><p>按本地已完成回测聚合候选样本外表现；不是实盘排行榜或投资建议。</p></div><div class="se-switch"><button data-se-view="leaderboard" class="${state.view === "leaderboard" ? "is-active" : ""}">排行榜</button><button data-se-view="strategies" class="${state.view === "strategies" ? "is-active" : ""}">策略列表</button></div></header>${state.view === "leaderboard" ? leaderboardHtml() : strategyListHtml()}`;
    if (state.view === "leaderboard") { renderLeaderboardChart(); window.AppVTable?.enhanceAll(root); }
  }
  function leaderboardHtml() {
    const top = state.ranked.filter((x) => x.run).slice(0, 10);
    return `<div class="se-leaderboard"><section class="se-panel"><h4>前十策略净值曲线</h4><div id="se-leader-chart" class="se-chart"></div></section><section class="se-panel se-table"><h4>Top 10</h4><div class="table-wrap"><table data-vtable-mode="detail"><thead><tr><th>#</th><th>策略</th><th>3M收益</th><th>1Y Sharpe</th><th>Score</th></tr></thead><tbody>${top.map((x, i) => `<tr><td>${i + 1}</td><td><button type="button" class="se-link" data-se-strategy="${esc(x.strategy.strategy_id)}">${esc(x.strategy.name)}</button></td><td>${pct(x.return3m)}</td><td>${x.sharpe.toFixed(2)}</td><td>${x.score.toFixed(2)}</td></tr>`).join("")}</tbody></table></div></section></div>`;
  }
  function strategyListHtml() { return `<div class="se-strategy-grid">${state.ranked.map((x) => `<article class="se-card" tabindex="0" data-se-strategy="${esc(x.strategy.strategy_id)}"><span class="se-kicker">${esc(x.strategy.category)}</span><h4>${esc(x.strategy.name)}</h4><code>${esc(x.strategy.strategy_id)} · ${esc(x.strategy.latest_version)}</code><p>${esc(x.strategy.description || "暂无策略说明")}</p><div class="se-meta"><span>${x.run ? `收益 ${pct(x.return3m)}` : "暂无完成回测"}</span><span>版本 ${esc(x.strategy.version_count)}</span></div></article>`).join("")}</div>`; }
  function lineSvg(series, valueKey = "value") {
    const width = 800, height = 250, pad = 24; const all = series.flatMap((s) => s.rows.map((r) => num(r[valueKey]))); if (!all.length) return '<div class="se-empty">暂无图表数据</div>';
    const min = Math.min(...all), max = Math.max(...all), span = max - min || 1; const colors = ["#2563eb", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#64748b"];
    return `<svg viewBox="0 0 ${width} ${height}" role="img">${series.map((s, i) => { const pts = s.rows.map((r, j) => `${pad + j * (width - 2 * pad) / Math.max(1, s.rows.length - 1)},${height - pad - (num(r[valueKey]) - min) * (height - 2 * pad) / span}`).join(" "); return `<polyline fill="none" stroke="${colors[i % colors.length]}" stroke-width="2" points="${pts}"/><text x="${pad + (i % 2) * 350}" y="${16 + Math.floor(i / 2) * 15}" fill="${colors[i % colors.length]}" font-size="10">${esc(s.label)}</text>`; }).join("")}</svg>`;
  }
  function renderLeaderboardChart() { const top = state.ranked.filter((x) => x.curve.length).slice(0, 10); $("#se-leader-chart").innerHTML = lineSvg(top.map((x) => ({ label: x.strategy.name, rows: normalizeCurve(x.curve) }))); }
  function normalizeCurve(rows) { const base = num(rows[0]?.value, 1) || 1; return rows.map((r) => ({ ...r, value: num(r.value) / base })); }
  function rowsOf(value) { return Array.isArray(value) ? value : Array.isArray(value?.rows) ? value.rows : []; }
  async function openDetail(id) { const row = state.ranked.find((x) => x.strategy.strategy_id === id); if (!row) return; state.selected = row; state.tab = "oos"; const history = await api(`/api/backtest/strategies/${encodeURIComponent(id)}/versions`).catch(() => ({ versions: [] })); state.versions = history.versions || []; if (typeof selectStrategy === "function") await selectStrategy(row.strategy); renderDetail(); }
  function showDirectory() { state.selected = null; renderDirectory(); }
  function renderDetail() {
    const x = state.selected; if (!x) return; const root = $("#se-detail"), shell = $("#strategy-pc-workbench"); $("#se-directory").hidden = true; root.hidden = false; shell.classList.add("se-detail-mode"); shell.classList.toggle("se-code-mode", state.tab === "code");
    const m = x.panel?.metrics || {}; root.innerHTML = `<header class="se-detail-hero"><button id="se-back" type="button">← 返回策略列表</button><span class="se-kicker">${esc(x.strategy.category)} · ${esc(x.strategy.strategy_id)}</span><h3>${esc(x.strategy.name)}</h3><p>${esc(x.strategy.description || "暂无策略说明")}</p><div class="se-metrics">${metric("3M Return", pct(x.return3m))}${metric("1Y Sharpe", x.sharpe.toFixed(2))}${metric("Score", x.score.toFixed(2))}${metric("Max Drawdown", pct(m.max_drawdown))}${metric("Win Rate", pct(m.win_rate))}${metric("Trades", num(m.trade_count))}</div></header><nav class="se-tabs"><button data-se-tab="oos" class="${state.tab === "oos" ? "is-active" : ""}">Out Of Sample Return</button><button data-se-tab="code" class="${state.tab === "code" ? "is-active" : ""}">Code</button><button data-se-tab="notes" class="${state.tab === "notes" ? "is-active" : ""}">Version Notes</button></nav><div class="se-tab-panel">${state.tab === "oos" ? oosHtml(x) : state.tab === "notes" ? notesHtml(x) : ""}</div>`;
    if (state.tab === "oos") renderOosCharts(x); if (state.tab === "notes") window.AppVTable?.enhanceAll(root);
  }
  const metric = (label, value) => `<div class="se-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  function oosHtml() { const names = [["equity", "Strategy Equity"], ["drawdown", "Drawdown"], ["benchmark", "Benchmark / Excess Return"], ["exposure", "Exposure"], ["volume", "Asset Sales Volume"], ["turnover", "Portfolio Turnover"], ["monthly", "Monthly Returns"], ["annual", "Annual Returns"]]; return `<div class="se-chart-grid">${names.map(([id, n]) => `<section class="se-panel"><h4>${n}</h4><div id="se-chart-${id}" class="se-chart"></div></section>`).join("")}</div>`; }
  function renderOosCharts(x) {
    const p = x.panel || {}; $("#se-chart-equity").innerHTML = lineSvg([{ label: x.strategy.name, rows: normalizeCurve(p.equity_curve || []) }]); $("#se-chart-drawdown").innerHTML = lineSvg([{ label: "Drawdown", rows: p.drawdown_curve || [] }]);
    $("#se-chart-benchmark").innerHTML = barsSvg((p.yearly_returns || []).map((r) => ({ label: r.year, a: r.portfolio_return, b: r.benchmark_return })), "组合", "基准");
    const ex = p.exposure_summary || {}; $("#se-chart-exposure").innerHTML = barsSvg(Object.entries(ex).filter(([,v]) => typeof v === "number").map(([k,v]) => ({ label:k,a:v })), "Exposure", "");
    const volume = new Map(); (p.trades || []).forEach((t) => volume.set(t.order_book_id, (volume.get(t.order_book_id) || 0) + num(t.amount))); $("#se-chart-volume").innerHTML = barsSvg([...volume].map(([label,a]) => ({label,a})), "成交额", "");
    let cumulative = 0; const turnover = (p.trades || []).map((t, i) => ({ value: cumulative += num(t.amount), date: t.trade_time || i })); $("#se-chart-turnover").innerHTML = lineSvg([{ label:"Cumulative Turnover", rows:turnover }]);
    $("#se-chart-monthly").innerHTML = barsSvg(rowsOf(p.monthly_return_heatmap).map((r) => ({ label: r.month || r.period || "-", a: r.return ?? r.value })), "月收益", "");
    $("#se-chart-annual").innerHTML = barsSvg((p.yearly_returns || []).map((r) => ({ label:r.year,a:r.portfolio_return })), "年度收益", "");
  }
  function barsSvg(rows, aLabel, bLabel) { if (!rows.length) return '<div class="se-empty">暂无图表数据</div>'; const max = Math.max(...rows.flatMap((r) => [Math.abs(num(r.a)), Math.abs(num(r.b))]), .0001); return `<div>${rows.slice(-18).map((r) => `<div style="display:grid;grid-template-columns:90px 1fr 1fr;gap:8px;align-items:center;margin:8px 0"><span>${esc(r.label)}</span><i style="display:block;height:10px;background:#2563eb;width:${Math.abs(num(r.a))/max*100}%"></i><i style="display:block;height:10px;background:#f59e0b;width:${Math.abs(num(r.b))/max*100}%"></i></div>`).join("")}<small>${esc(aLabel)} ${bLabel ? `· ${esc(bLabel)}` : ""}</small></div>`; }
  function notesHtml(x) { const versions = state.versions.length ? [...state.versions].reverse() : [x.strategy]; return `<section class="se-panel se-table"><h4>Version Notes</h4><div class="table-wrap"><table data-vtable-mode="detail"><thead><tr><th>版本</th><th>保存时间</th><th>说明</th><th>Source SHA</th></tr></thead><tbody>${versions.map((version) => `<tr><td>${esc(version.version || version.latest_version)}</td><td>${esc(version.saved_at || version.created_at || "—")}</td><td>${esc(version.description || version.version_note || x.strategy.description || "未填写版本说明")}</td><td><code>${esc((version.source_sha256 || "").slice(0, 16))}</code></td></tr>`).join("")}</tbody></table></div></section>`; }
  function showError(e) { if (typeof setFeedback === "function") setFeedback(e.message, "error"); const root = $("#se-directory"); if (root) root.innerHTML = `<div class="se-empty">策略工作台加载失败：${esc(e.message)}</div>`; }
  function start() { let tries = 0; const timer = setInterval(() => { tries += 1; if (ensureShell()) { clearInterval(timer); load().catch(showError); } else if (tries > 30) clearInterval(timer); }, 100); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
