(function () {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const state = { selected: null, selectedDate: null, kind: "index", bars: [], payload: null };
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));

  async function json(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`);
    return payload;
  }

  function feedback(message, tone = "success") {
    if (typeof window.setFeedback === "function") window.setFeedback(message, tone);
  }

  function query(values) {
    const params = new URLSearchParams();
    Object.entries(values).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    });
    return params.toString();
  }

  function setView(view) {
    $$("[data-m4-view]").forEach((section) => { section.hidden = section.dataset.m4View !== view; });
    $$("[data-m4-view-tab]").forEach((button) => button.classList.toggle("is-active", button.dataset.m4ViewTab === view));
    window.VTableAdapter?.enhanceAll?.();
  }

  function updateHeading(button) {
    const title = button.dataset.m4Title || button.textContent.trim();
    const path = button.dataset.m4Path || "数据中心 / 资产浏览";
    const ready = button.dataset.m4Ready === "true";
    $("#dc-m4-title").textContent = title;
    $("#dc-m4-breadcrumb").textContent = path;
    const availability = $("#dc-m4-availability");
    availability.textContent = ready ? "数据可查询" : "数据待接入";
    availability.classList.toggle("is-pending", !ready);
  }

  function showUnavailable(button) {
    setView("unavailable");
    $("#dc-m4-unavailable-title").textContent = `${button.dataset.m4Title || button.textContent.trim()}尚无可用数据`;
    $("#dc-m4-unavailable-copy").textContent =
      "当前项目没有该资产的可验证接口或已同步数据。为避免产生误导，本页不展示模拟行情；可前往 M2 创建同步任务。";
  }

  function configureChart(kind, symbol) {
    state.kind = kind;
    const form = $("#a-share-daily-form");
    if (form?.elements.symbol) {
      form.elements.symbol.value = symbol || "";
      form.elements.symbol.readOnly = kind === "index";
    }
    const adjustment = $("#dc-m4-adjustment-field");
    if (adjustment) adjustment.hidden = kind === "index";
  }

  function renderSummary(items) {
    const target = $("#a-share-daily-summary");
    if (!target) return;
    target.innerHTML = items.map((item) =>
      `<article><span>${item.label}</span><strong>${item.value ?? "-"}</strong></article>`
    ).join("");
  }

  function periodKey(dateText, frequency) {
    if (frequency === "monthly") return String(dateText).slice(0, 7);
    if (frequency !== "weekly") return String(dateText);
    const value = new Date(`${dateText}T00:00:00Z`);
    const day = value.getUTCDay() || 7;
    value.setUTCDate(value.getUTCDate() - day + 1);
    return value.toISOString().slice(0, 10);
  }

  function aggregateBars(rows, frequency) {
    if (frequency === "daily") return rows;
    const groups = new Map();
    rows.forEach((row) => {
      const key = periodKey(row.date, frequency);
      const current = groups.get(key);
      if (!current) {
        groups.set(key, { ...row, volume: Number(row.volume || 0), amount: Number(row.amount || 0) });
        return;
      }
      current.date = row.date;
      current.high = Math.max(Number(current.high), Number(row.high));
      current.low = Math.min(Number(current.low), Number(row.low));
      current.close = Number(row.close);
      current.volume += Number(row.volume || 0);
      current.amount += Number(row.amount || 0);
    });
    return Array.from(groups.values());
  }

  function renderCurrentBars() {
    const frequency = $("#dc-m4-frequency")?.value || "daily";
    const rows = aggregateBars(state.bars, frequency);
    if (typeof window.renderCandlestick === "function") window.renderCandlestick($("#a-share-daily-chart"), rows);
    $("#dc-m4-chart-period").textContent = frequency === "daily" ? "日线" : frequency === "weekly" ? "周线（由日线聚合）" : "月线（由日线聚合）";
  }

  async function loadIndexCatalog() {
    const payload = await json("/api/market/index-symbols");
    const items = payload.catalog?.items || [];
    const coverage = new Map(items.map((item) => [String(item.index_symbol), item]));
    $$('[data-m4-mode="index"]').forEach((button) => {
      const code = String(button.dataset.m4Symbol || "").split(".")[0];
      const item = coverage.get(code);
      if (!item) return;
      const ready = item.status === "ready" && Number(item.row_count || 0) > 0;
      button.dataset.m4Ready = String(ready);
      const label = $(".dc-m4-node-state", button);
      if (label) {
        label.textContent = ready ? `${Number(item.row_count).toLocaleString("zh-CN")} 行` : "待同步";
        label.classList.toggle("is-ready", ready);
      }
    });
    return items;
  }

  async function loadIndexDaily(button = state.selected) {
    if (!button) return;
    const form = $("#a-share-daily-form");
    const values = Object.fromEntries(new FormData(form).entries());
    const indexSymbol = String(button.dataset.m4Symbol || "").split(".")[0];
    const payload = await json("/api/market/index-daily?" + query({
      index_symbol: indexSymbol,
      start_date: values.start_date,
      end_date: values.end_date,
      limit: values.limit || 120,
      offset: values.offset || 0,
    }));
    const daily = payload.daily || {};
    const descending = daily.rows || [];
    state.bars = [...descending].reverse();
    state.payload = daily;
    renderSummary([
      { label: "指数", value: `${button.dataset.m4Title} / ${button.dataset.m4Symbol}` },
      { label: "数据周期", value: "日线基座" },
      { label: "区间总行数", value: Number(daily.total || 0).toLocaleString("zh-CN") },
      { label: "本页", value: descending.length },
      { label: "来源", value: daily.source || "-" },
    ]);
    renderCurrentBars();
    $("#a-share-daily-body").innerHTML = descending.map((row) =>
      `<tr><td>${row.date}</td><td>${row.open ?? "-"}</td><td>${row.high ?? "-"}</td><td>${row.low ?? "-"}</td><td>${row.close ?? "-"}</td><td>${Number(row.volume || 0).toLocaleString("zh-CN")}</td><td>${Number(row.amount || 0).toLocaleString("zh-CN")}</td><td>${row.change_pct ?? "-"}</td><td>-</td></tr>`
    ).join("") || '<tr><td colspan="9" class="empty-cell">该区间没有指数行情</td></tr>';
    $("#a-share-daily-output").textContent = JSON.stringify(daily, null, 2);
    window.VTableAdapter?.enhanceAll?.();
  }

  function selectNode(button) {
    if (!button) return;
    state.selected = button;
    $$("[data-m4-node]").forEach((node) => node.classList.toggle("is-active", node === button));
    updateHeading(button);
    const mode = button.dataset.m4Mode;
    if (mode === "list") {
      state.kind = "stock";
      setView("list");
      const market = button.dataset.m4Market || "";
      const form = $("#a-share-symbol-form");
      if (form?.elements.market) form.elements.market.value = market;
      form?.requestSubmit();
    } else if (mode === "index" && button.dataset.m4Ready === "true") {
      configureChart("index", button.dataset.m4Symbol);
      setView("chart");
      loadIndexDaily(button).catch((error) => {
        feedback(error.message, "error");
        showUnavailable(button);
      });
    } else {
      showUnavailable(button);
    }
  }

  const marketCategoryTargets = {
    "个股行情": "沪深 A 股",
    "行业板块": "行业板块",
    "概念板块": "概念板块",
    "新闻公告": "新闻公告",
  };

  function openMarketDataCategory(category) {
    const targetTitle = marketCategoryTargets[category] || marketCategoryTargets["个股行情"];
    const target = $$('[data-m4-node]').find((button) => button.dataset.m4Title === targetTitle);
    if (!target) return false;
    selectNode(target);
    $$('[data-market-category]').forEach((button) => button.classList.toggle("is-active", button.dataset.marketCategory === category));
    const pageTitle = $("#page-title");
    if (pageTitle) pageTitle.textContent = `市场数据 · ${category}`;
    return true;
  }
  window.openMarketDataCategory = openMarketDataCategory;

  function filterTree(value) {
    const term = String(value || "").trim().toLowerCase();
    $$("[data-m4-node]").forEach((button) => {
      const haystack = `${button.dataset.m4Title || ""} ${button.dataset.m4Symbol || ""}`.toLowerCase();
      button.hidden = Boolean(term) && !haystack.includes(term);
    });
    $$(".dc-m4-tree details").reverse().forEach((details) => {
      const visible = $$("[data-m4-node]", details).some((node) => !node.hidden);
      details.hidden = Boolean(term) && !visible;
      if (term && visible) details.open = true;
    });
    $("#dc-m4-search-state").textContent = term
      ? `匹配 ${$$("[data-m4-node]:not([hidden])").length} 项`
      : "按代码或名称定位";
  }

  function panoramaStatus(section) {
    if (!section?.items?.length) return "未同步 · 可在 M2 补齐";
    const effective = section.effective_trade_date || "—";
    return section.status === "stale" ? `最近可用 ${effective}` : `交易日 ${effective}`;
  }

  function setPanoramaPanel(key, section, html) {
    const content = $(`#dc-m4-${key}`);
    const status = $(`#dc-m4-${key}-status`);
    if (status) {
      status.textContent = panoramaStatus(section);
      status.className = section?.items?.length ? (section.status === "stale" ? "is-stale" : "is-ready") : "is-empty";
    }
    if (!content) return;
    content.innerHTML = section?.items?.length ? html : '<div class="dc-m4-panorama-empty">该交易日暂无本地数据。请在 M2 选择对应数据集进行增量同步。</div>';
  }

  function boardTable(section) {
    const rows = (section?.items || []).slice(0, 40);
    return `<div class="table-wrap"><table data-vtable-mode="market" aria-label="板块涨跌排名"><thead><tr><th>板块</th><th>涨跌幅</th><th>成分数</th><th>上涨</th><th>下跌</th><th>成交额</th><th>领涨标的</th></tr></thead><tbody>${rows.map((row) => `<tr><td><strong>${escapeHtml(row.board_name)}</strong></td><td>${Number(row.change_pct || 0).toFixed(2)}%</td><td>${Number(row.member_count || 0).toLocaleString("zh-CN") || "—"}</td><td>${Number(row.up_count || 0).toLocaleString("zh-CN")}</td><td>${Number(row.down_count || 0).toLocaleString("zh-CN")}</td><td>${Number(row.amount || 0).toLocaleString("zh-CN")}</td><td>${escapeHtml(row.leader_name || row.leader_symbol || "—")}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function flowTable(section) {
    const rows = (section?.items || []).slice(0, 40);
    return `<div class="table-wrap"><table data-vtable-mode="market" aria-label="板块资金流排名"><thead><tr><th>板块</th><th>主力净流入</th><th>主力净占比</th><th>超大单净流入</th><th>大单净流入</th></tr></thead><tbody>${rows.map((row) => `<tr><td><strong>${escapeHtml(row.board_name)}</strong></td><td>${Number(row.main_net_inflow || 0).toLocaleString("zh-CN")}</td><td>${Number(row.main_net_ratio || 0).toFixed(2)}%</td><td>${Number(row.super_large_net_inflow || 0).toLocaleString("zh-CN")}</td><td>${Number(row.large_net_inflow || 0).toLocaleString("zh-CN")}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function eventTable(section) {
    const rows = (section?.items || []).slice(0, 100);
    return `<div class="table-wrap"><table data-vtable-mode="market" aria-label="当日新闻与公告"><thead><tr><th>时间</th><th>类型</th><th>代码</th><th>标题</th><th>来源</th><th>原文</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${escapeHtml(row.published_at || row.event_date)}</td><td>${escapeHtml(row.event_type === "announcement" ? "公告" : "新闻")}</td><td>${escapeHtml(row.symbol || "市场")}</td><td>${escapeHtml(row.title)}</td><td>${escapeHtml(row.source)}</td><td>${row.url ? `<a href="${escapeHtml(row.url)}" target="_blank" rel="noreferrer">查看</a>` : "—"}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function renderPanorama(payload) {
    const sections = payload.sections || {};
    setPanoramaPanel("industry-heatmap", sections.industry_heatmap, boardTable(sections.industry_heatmap));
    setPanoramaPanel("concept-heatmap", sections.concept_heatmap, boardTable(sections.concept_heatmap));
    setPanoramaPanel("industry-flow", sections.industry_fund_flow, flowTable(sections.industry_fund_flow));
    setPanoramaPanel("concept-flow", sections.concept_fund_flow, flowTable(sections.concept_fund_flow));
    setPanoramaPanel("events", sections.events, eventTable(sections.events));
    window.VTableAdapter?.enhanceAll?.();
  }

  async function openPanorama(date) {
    if (!date) return;
    state.selectedDate = date;
    $("#dc-m4-panorama-date").textContent = `${date} · 市场全景（读取中）`;
    const panel = $("#dc-m4-panorama");
    panel.open = true;
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    ["industry-heatmap", "concept-heatmap", "industry-flow", "concept-flow", "events"].forEach((key) => {
      const target = $(`#dc-m4-${key}`);
      if (target) target.innerHTML = '<div class="dc-m4-panorama-empty">正在读取本地数据…</div>';
    });
    const form = $("#a-share-daily-form");
    const symbol = state.kind === "stock" ? String(form?.elements?.symbol?.value || "") : "";
    try {
      const payload = await json(`/api/market/panorama?${query({ trade_date: date, symbol, asset_type: state.kind })}`);
      renderPanorama(payload.panorama || {});
      const ready = Number(payload.panorama?.ready_section_count || 0);
      $("#dc-m4-panorama-date").textContent = `${date} · 市场全景 · ${ready}/5 分区可用`;
    } catch (error) {
      $("#dc-m4-panorama-date").textContent = `${date} · 市场全景加载失败`;
      ["industry-heatmap", "concept-heatmap", "industry-flow", "concept-flow", "events"].forEach((key) => setPanoramaPanel(key, null, ""));
      feedback(`市场全景加载失败：${error.message}`, "error");
    }
  }

  function bindKlineDrilldown() {
    const chart = $("#a-share-daily-chart");
    if (!chart) return;
    chart.addEventListener("click", (event) => {
      const candle = event.target.closest("[data-kline-date]");
      if (candle) openPanorama(candle.dataset.klineDate);
    });
    chart.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      const candle = event.target.closest("[data-kline-date]");
      if (candle) {
        event.preventDefault();
        openPanorama(candle.dataset.klineDate);
      }
    });
  }

  function bindSymbolSelection() {
    const body = $("#a-share-symbol-body");
    if (!body) return;
    const openSymbol = (button) => {
      if (!button) return;
      const stockNode = $('[data-m4-mode="list"][data-m4-market=""]');
      state.selected = stockNode;
      configureChart("stock", button.dataset.aShareSymbol);
      setView("chart");
      $("#dc-m4-title").textContent = `${button.dataset.aShareSymbol} 个股行情`;
      $("#dc-m4-breadcrumb").textContent = "数据中心 / 资产浏览 / 行情数据 / 股票行情 / 沪深 A 股";
      $("#dc-m4-availability").textContent = "数据可查询";
      $("#dc-m4-availability").classList.remove("is-pending");
    };
    body.addEventListener("click", (event) => openSymbol(event.target.closest("[data-a-share-symbol]")));
    body.addEventListener("dblclick", (event) => {
      const button = event.target.closest("tr")?.querySelector("[data-a-share-symbol]");
      if (!button) return;
      if (event.target !== button) button.click();
      openSymbol(button);
    });
  }

  function jumpToSync() {
    $("[data-dc-view='sync']")?.click();
  }

  async function bind() {
    const root = $("#dc-view-assets");
    if (!root) return;
    $$("[data-m4-node]", root).forEach((button) => button.addEventListener("click", () => selectNode(button)));
    $$("[data-m4-view-tab]", root).forEach((button) => button.addEventListener("click", () => {
      if (button.dataset.m4ViewTab === "chart" && state.selected?.dataset.m4Ready !== "true") showUnavailable(state.selected);
      else setView(button.dataset.m4ViewTab);
    }));
    $("#dc-m4-search-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const first = $("[data-m4-node]:not([hidden])", root);
      if (first) selectNode(first);
      else feedback("没有匹配的资产", "error");
    });
    $("#dc-m4-search")?.addEventListener("input", (event) => filterTree(event.currentTarget.value));
    $$("[data-m4-jump-sync]", root).forEach((button) => button.addEventListener("click", jumpToSync));
    $("#a-share-daily-form")?.addEventListener("submit", (event) => {
      if (state.kind !== "index") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      loadIndexDaily().catch((error) => feedback(error.message, "error"));
    }, true);
    $("[data-m4-frequency]")?.addEventListener("change", renderCurrentBars);
    window.addEventListener("scq:market-bars-loaded", (event) => {
      if (event.detail?.kind !== "stock") return;
      state.kind = "stock";
      state.bars = event.detail.rows || [];
      state.payload = event.detail.payload || null;
      renderCurrentBars();
    });
    bindKlineDrilldown();
    bindSymbolSelection();
    const initialCategory = new URLSearchParams(window.location.search).get("market_tab");
    const categoryRestored = Boolean(initialCategory && openMarketDataCategory(initialCategory));
    try {
      await loadIndexCatalog();
    } catch (error) {
      feedback(`指数目录读取失败：${error.message}`, "error");
    }
    if (!categoryRestored) {
      selectNode($("[data-m4-node].is-active", root) || $("[data-m4-node]", root));
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
}());
