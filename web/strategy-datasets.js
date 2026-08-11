(() => {
  "use strict";

  const state = { categories: [], products: [], layerId: "", selected: null, tab: "about" };
  const initialParams = new URLSearchParams(location.search);
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
  const fmt = (value, fallback = "—") => value === null || value === undefined || value === "" ? fallback : String(value);

  async function api(path, options = {}) {
    const response = await fetch(path, {
      method: options.method || "GET",
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `请求失败 (${response.status})`);
    return payload;
  }

  function ensureShell() {
    if (!$("link[href^='/strategy-datasets.css']")) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/strategy-datasets.css?v=2";
      document.head.append(link);
    }
    if (!$(".nav-tab[data-page='strategy-datasets']")) {
      const button = document.createElement("button");
      button.className = "nav-tab";
      button.type = "button";
      button.dataset.page = "strategy-datasets";
      button.textContent = "策略数据集";
      const factor = $(".nav-tab[data-page='factor']");
      factor?.before(button);
    }
    if (!$("#page-strategy-datasets")) {
      const section = document.createElement("section");
      section.id = "page-strategy-datasets";
      section.className = "page-section strategy-datasets-page";
      section.innerHTML = `
        <div class="sd-shell">
          <aside class="sd-sidebar">
            <h3>数据集分类</h3>
            <p>目录来自数据中心。这里提供研究说明、调用契约和策略示例。</p>
            <nav id="sd-categories" class="sd-categories" aria-label="策略数据集分类"><div class="sd-empty">读取中…</div></nav>
          </aside>
          <main class="sd-main">
            <div id="sd-catalog-view">
              <header class="sd-hero"><div><span class="sd-kicker">STRATEGY DATASETS · PUBLISHED INPUTS</span><h3>策略数据集</h3><p>浏览已治理的数据产品，复制调用代码，将完整示例导入策略工作台。</p></div></header>
              <div class="sd-toolbar">
                <input id="sd-search" type="search" placeholder="搜索名称、Dataset ID 或数据源" aria-label="搜索策略数据集">
                <select id="sd-status" aria-label="数据集状态"><option value="">全部状态</option><option value="connected">已连接</option><option value="unavailable">不可用</option><option value="disabled">已停用</option></select>
                <select id="sd-scope" aria-label="消费范围"><option value="">全部范围</option><option value="strategy">策略可用</option><option value="factor_research">因子研究</option><option value="governance">仅治理</option></select>
                <button id="sd-refresh" type="button">刷新</button>
              </div>
              <div id="sd-summary" class="sd-summary"></div>
              <div id="sd-cards" class="sd-card-grid"><div class="sd-empty">正在读取数据集…</div></div>
            </div>
            <div id="sd-detail-view" hidden>
              <header id="sd-detail-hero" class="sd-detail-hero"></header>
              <nav class="sd-tabs" aria-label="Dataset 详情页签">
                <button class="is-active" type="button" data-sd-tab="about">数据概览</button>
                <button type="button" data-sd-tab="documentation">使用文档</button>
                <button type="button" data-sd-tab="research">研究分析</button>
                <button type="button" data-sd-tab="examples">代码示例</button>
              </nav>
              <div id="sd-tab-panel" class="sd-tab-panel"></div>
            </div>
          </main>
        </div>`;
      $("#page-factor")?.before(section);
    }
    if (typeof pageTitles !== "undefined") pageTitles["strategy-datasets"] = "策略数据集";
  }

  async function loadCatalog() {
    const params = new URLSearchParams();
    if (state.layerId) params.set("layer_id", state.layerId);
    const search = $("#sd-search")?.value.trim();
    const status = $("#sd-status")?.value;
    const scope = $("#sd-scope")?.value;
    if (search) params.set("search", search);
    if (status) params.set("status", status);
    if (scope) params.set("consumer_scope", scope);
    const [categories, products] = await Promise.all([
      api("/api/strategy-datasets/categories"),
      api(`/api/strategy-datasets${params.size ? `?${params}` : ""}`),
    ]);
    const categoryPayload = categories.result || categories;
    const productPayload = products.result || products;
    state.categories = categoryPayload.items || [];
    state.products = productPayload.items || [];
    renderCategories();
    renderCards(productPayload.summary || {});
  }

  function renderCategories() {
    const host = $("#sd-categories");
    host.innerHTML = state.categories.map((item) => `<button type="button" class="sd-category${state.layerId === item.layer_id ? " is-active" : ""}" data-sd-layer="${esc(item.layer_id)}"><span>${esc(item.name)}</span><span>${esc(item.count)}</span></button>`).join("");
    $$('[data-sd-layer]', host).forEach((button) => button.addEventListener("click", async () => {
      state.layerId = button.dataset.sdLayer;
      await loadCatalog();
    }));
  }

  function accessBadge(item) {
    if (item.strategy_access === "executable") return '<span class="sd-badge is-ready">可直接回测</span>';
    if (item.strategy_access === "template_only") return '<span class="sd-badge is-template">仅研究 / 待适配</span>';
    if (item.status !== "connected") return '<span class="sd-badge is-off">数据不可用</span>';
    return '<span class="sd-badge is-off">仅治理 / 非策略输入</span>';
  }

  function renderCards(summary) {
    $("#sd-summary").innerHTML = `<span>${fmt(summary.total, 0)} 个产品</span><span>${fmt(summary.connected, 0)} 个已连接</span><span>${fmt(summary.strategy_ready, 0)} 个可直接回测</span><span>目录权威：数据中心</span>`;
    const host = $("#sd-cards");
    if (!state.products.length) {
      host.innerHTML = '<div class="sd-empty">当前分类或筛选条件下没有数据集。</div>';
      return;
    }
    host.innerHTML = state.products.map((item) => `<article class="sd-card" tabindex="0" role="button" data-sd-dataset="${esc(item.dataset_id)}">
      <div class="sd-card-head"><span class="sd-badge">${esc(item.category_name)}</span>${accessBadge(item)}</div>
      <h4>${esc(item.name)}</h4><code>${esc(item.dataset_id)}</code>
      <p>${esc(item.description)}</p>
      <div class="sd-card-meta"><span>${esc(item.source_name)}</span><span>${esc((item.frequencies || []).join(" / ") || "—")}</span><span>${esc(item.example_count)} 个示例</span></div>
    </article>`).join("");
    $$('[data-sd-dataset]', host).forEach((card) => {
      const open = () => openDetail(card.dataset.sdDataset).catch(showError);
      card.addEventListener("click", open);
      card.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") open(); });
    });
  }

  async function openDetail(datasetId) {
    const payload = await api(`/api/strategy-datasets/${encodeURIComponent(datasetId)}`);
    state.selected = payload.result;
    state.tab = "about";
    $("#sd-catalog-view").hidden = true;
    $("#sd-detail-view").hidden = false;
    renderDetailHero();
    activateTab("about");
    const url = new URL(location.href);
    url.searchParams.set("page", "strategy-datasets");
    url.searchParams.set("dataset", datasetId);
    history.replaceState({}, "", url);
  }

  function renderDetailHero() {
    const item = state.selected;
    const version = item.published_version || {};
    $("#sd-detail-hero").innerHTML = `<div><button type="button" id="sd-back">← 返回数据集</button><span class="sd-kicker">${esc(item.category_name)} · ${esc(item.dataset_id)}</span><h3>${esc(item.name)}</h3><p>${esc(item.description)}</p><div class="sd-summary"><span>${esc(item.source_name)}</span><span>${esc(version.version_id || "无 Published 版本")}</span><span>截止 ${esc(version.coverage_end || version.as_of_trade_date || "—")}</span>${accessBadge(item)}</div></div><div class="sd-detail-actions"><button type="button" id="sd-open-strategy">查看策略示例</button></div>`;
    $("#sd-back").addEventListener("click", showCatalog);
    $("#sd-open-strategy").addEventListener("click", () => activateTab("examples"));
  }

  function showCatalog() {
    state.selected = null;
    $("#sd-detail-view").hidden = true;
    $("#sd-catalog-view").hidden = false;
    const url = new URL(location.href);
    url.searchParams.delete("dataset");
    history.replaceState({}, "", url);
  }

  function activateTab(tab) {
    state.tab = tab;
    $$('[data-sd-tab]').forEach((button) => button.classList.toggle("is-active", button.dataset.sdTab === tab));
    const renderers = { about: renderAbout, documentation: renderDocumentation, research: renderResearch, examples: renderExamples };
    renderers[tab]();
  }

  function facts(items) {
    return `<div class="sd-facts">${items.map(([label, value]) => `<div class="sd-fact"><span>${esc(label)}</span><strong>${esc(fmt(value))}</strong></div>`).join("")}</div>`;
  }

  function renderAbout() {
    const item = state.selected;
    const about = item.about || {};
    const summary = about.data_summary || {};
    const fields = item.fields || [];
    $("#sd-tab-panel").innerHTML = `<div class="sd-section-grid">
      <section class="sd-block"><h4>About ${esc(item.name)}</h4><p>${esc(about.introduction || item.description)}</p></section>
      <section class="sd-block"><h4>数据提供与边界</h4>${facts([["数据源", about.provider?.name], ["上游", about.provider?.upstream_name], ["使用范围", about.provider?.license_scope]])}</section>
      <section class="sd-block is-wide"><h4>Data Summary</h4>${facts([["市场", (summary.market_scope || []).join(" / ")], ["资产类型", (summary.asset_types || []).join(" / ")], ["频率", (summary.frequencies || []).join(" / ")], ["复权", (summary.adjustments || []).join(" / ")], ["点时策略", summary.point_in_time_policy]])}</section>
      <section class="sd-block is-wide"><h4>Data Point Attributes</h4><div class="table-wrap"><table data-vtable-mode="detail"><thead><tr><th>字段</th><th>类型</th><th>说明</th><th>可空</th></tr></thead><tbody>${fields.map((field) => `<tr><td><code>${esc(field.name)}</code></td><td>${esc(field.data_type)}</td><td>${esc(field.description)}</td><td>${field.nullable ? "是" : "否"}</td></tr>`).join("")}</tbody></table></div></section>
      <section class="sd-block is-wide"><h4>Example Applications</h4><ul>${(about.applications || []).map((value) => `<li>${esc(value)}</li>`).join("")}</ul></section>
    </div>`;
    window.AppVTable?.enhanceAll($("#sd-tab-panel"));
  }

  function codeBlock(source, id) {
    return `<div class="sd-code"><div class="sd-code-actions"><button type="button" data-sd-copy="${esc(id)}">复制代码</button></div><pre><code id="${esc(id)}">${esc(source || "# 暂无代码")}</code></pre></div>`;
  }

  function documentationCodeBlock(source, id) {
    const value = source || "# 暂无代码";
    const lines = Array.from({ length: Math.max(1, value.split("\n").length) }, (_, index) => String(index + 1)).join("\n");
    const highlighted = typeof highlightStage76Python === "function" ? highlightStage76Python(value) : esc(value);
    let theme = "light";
    try { theme = localStorage.getItem("sleepercloudquant-code-theme") === "dark" ? "dark" : "light"; } catch (_) {}
    return `<div class="sd-code sd-documentation-code"><div class="sd-code-actions"><button type="button" data-sd-copy="${esc(id)}">复制代码</button></div><div class="sd-workbench-code" data-theme="${theme}"><pre class="sd-workbench-gutter" aria-hidden="true">${lines}</pre><pre class="sd-workbench-source"><code id="${esc(id)}">${highlighted}</code></pre></div></div>`;
  }
  function renderDocumentation() {
    const item = state.selected;
    const doc = item.documentation || {};
    const request = doc.request_contract || {};
    $("#sd-tab-panel").innerHTML = `<div class="sd-section-grid">
      <section class="sd-block is-wide"><h4>Getting Started</h4><p>声明数据依赖后，回测只解析 Published 数据版本；缺少字段或覆盖不足时显式失败。</p>${documentationCodeBlock(doc.getting_started?.source_code, "sd-doc-code")}</section>
      <section class="sd-block"><h4>Request Contract</h4>${facts([["Dataset ID", request.dataset_id], ["版本策略", request.version_policy], ["缺失策略", request.missing_data_policy], ["执行契约", doc.execution_contract]])}</section>
      <section class="sd-block"><h4>字段与复权</h4><p><strong>字段：</strong>${esc((request.fields || []).join(", ") || "Schema 待补齐")}</p><p><strong>复权：</strong>${esc((request.supported_adjustments || []).join(" / ") || "不适用")}</p><p><strong>安全边界：</strong>${esc(doc.security_boundary)}</p></section>
    </div>`;
    bindCopyButtons();
  }

  function renderResearch() {
    const research = state.selected.research || {};
    const profile = research.profile || {};
    $("#sd-tab-panel").innerHTML = `<div class="sd-section-grid">
      <section class="sd-block is-wide"><h4>Published Snapshot Profile</h4>${facts([["\u6570\u636e\u7248\u672c", research.version?.version_id], ["\u8986\u76d6\u5f00\u59cb", profile.coverage_start], ["\u8986\u76d6\u7ed3\u675f", profile.coverage_end], ["\u6807\u7684\u6570\u91cf", profile.symbol_count], ["\u6570\u636e\u884c\u6570", profile.row_count], ["\u8d28\u91cf\u72b6\u6001", profile.quality_status]])}</section>
      <section class="sd-block is-wide"><h4>Research Recipe</h4><p>\u6b64\u5904\u53ea\u63d0\u4f9b\u53d7\u63a7\u7814\u7a76\u914d\u65b9\uff0c\u4e0d\u5f00\u653e\u6d4f\u89c8\u5668\u4efb\u610f Python \u6267\u884c\u3002</p>${codeBlock(research.recipe?.source_code, "sd-research-code")}</section>
      <section class="sd-block is-wide"><h4>\u53d7\u63a7\u6570\u636e\u9884\u89c8</h4><p>\u9884\u89c8\u53ea\u8bfb\u53d6\u5df2\u6709 M4 \u7269\u7406\u9002\u914d\u5668\uff0c\u4e0d\u6267\u884c\u4efb\u610f SQL\u3002</p><button type="button" id="sd-preview-load">\u8bfb\u53d6\u9884\u89c8</button><div id="sd-preview-result" class="sd-preview-result"></div></section>
    </div>`;
    bindCopyButtons();
    $("#sd-preview-load")?.addEventListener("click", () => loadResearchPreview().catch(showError));
  }

  async function loadResearchPreview() {
    const datasetId = state.selected.dataset_id;
    const symbol = datasetId === "index_daily" ? "000300.XSHG" : "000001.XSHE";
    const payload = await api(`/api/strategy-datasets/${encodeURIComponent(datasetId)}/preview`, {
      method: "POST",
      body: { symbol, limit: 50 },
    });
    const result = payload.result || {};
    const rows = result.rows || [];
    const host = $("#sd-preview-result");
    if (!rows.length) { host.innerHTML = '<div class="sd-empty">No preview rows.</div>'; return; }
    const columns = Object.keys(rows[0]).slice(0, 8);
    host.innerHTML = `<div class="table-wrap"><table data-vtable-mode="detail"><thead><tr>${columns.map((key) => `<th>${esc(key)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((key) => `<td>${esc(fmt(row[key]))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    window.AppVTable?.enhanceAll(host);
  }

  function renderExamples() {
    const examples = state.selected.examples || [];
    $("#sd-tab-panel").innerHTML = `<div class="sd-example-list">${examples.map((item, index) => `<article class="sd-example"><header><div><span class="sd-badge">${esc(item.kind)}</span><h4>${esc(item.title)}</h4><p>${esc(item.description)}</p></div><div class="sd-detail-actions"><button type="button" data-sd-copy="sd-example-${index}">复制代码</button>${item.kind === "strategy" ? `<button type="button" data-sd-instantiate="${esc(item.example_id)}">导入策略工作台</button>` : ""}</div></header><div class="sd-code"><pre><code id="sd-example-${index}">${esc(item.source_code)}</code></pre></div><div class="sd-summary"><span>${esc(item.execution_contract)}</span><span>${item.runtime_status === "executable" ? "当前可执行" : "研究模板"}</span><span>${esc(item.example_version)}</span></div></article>`).join("")}</div>`;
    bindCopyButtons();
    $$('[data-sd-instantiate]').forEach((button) => button.addEventListener("click", () => importStrategyExample(button.dataset.sdInstantiate).catch(showError)));
  }

  function bindCopyButtons() {
    $$('[data-sd-copy]', $("#sd-tab-panel")).forEach((button) => button.addEventListener("click", async () => {
      const source = $(`#${CSS.escape(button.dataset.sdCopy)}`)?.textContent || "";
      await navigator.clipboard.writeText(source);
      button.textContent = "已复制";
      setTimeout(() => { button.textContent = "复制代码"; }, 1200);
    }));
  }

  async function importStrategyExample(exampleId) {
    const datasetId = state.selected.dataset_id;
    const payload = await api(`/api/strategy-datasets/${encodeURIComponent(datasetId)}/examples/${encodeURIComponent(exampleId)}/instantiate`, { method: "POST" });
    const result = payload.result || {};
    const draft = result.strategy_draft || {};
    if (!result.validation?.ok) throw new Error("示例策略校验未通过");
    if (typeof activatePage === "function") activatePage("backtest");
    if (typeof activateStage76Workspace === "function") activateStage76Workspace("strategy");
    const importedDraft = {
      ...draft,
      description: `${draft.description}｜Dataset: ${datasetId}｜Example: ${draft.example_id}@${draft.example_version}`,
    };
    if (typeof startNewStrategy === "function") startNewStrategy(importedDraft);
    if (typeof setFeedback === "function") setFeedback(draft.runtime_status === "executable" ? "示例已导入策略工作台，可校验并保存版本" : "研究模板已导入；辅助数据运行时接入前请勿视为可直接回测", draft.runtime_status === "executable" ? "success" : "error");
  }

  function showError(error) {
    const message = error?.message || String(error);
    if (typeof setFeedback === "function") setFeedback(message, "error");
    const cards = $("#sd-cards");
    if (cards && !state.products.length) cards.innerHTML = `<div class="sd-empty"><strong>策略数据集读取失败</strong><p>${esc(message)}</p><p>请确认本地服务与 /api/strategy-datasets 接口可用。</p><button type="button" id="sd-error-retry">重试读取 M4 目录</button></div>`;
    $("#sd-error-retry")?.addEventListener("click", () => loadCatalog().catch(showError));
  }

  function bind() {
    ensureShell();
    $(".nav-tab[data-page='strategy-datasets']")?.addEventListener("click", () => openCatalog());
    $("#sd-search")?.addEventListener("input", debounce(() => loadCatalog().catch(showError), 220));
    $("#sd-status")?.addEventListener("change", () => loadCatalog().catch(showError));
    $("#sd-scope")?.addEventListener("change", () => loadCatalog().catch(showError));
    $("#sd-refresh")?.addEventListener("click", () => loadCatalog().catch(showError));
    $$('[data-sd-tab]').forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.sdTab)));
    if (initialParams.get("page") === "strategy-datasets") {
      openCatalog().then(() => initialParams.get("dataset") ? openDetail(initialParams.get("dataset")) : null).catch(showError);
    }
  }

  async function openCatalog() {
    if (typeof activatePage === "function") activatePage("strategy-datasets");
    await loadCatalog();
  }

  function debounce(fn, wait) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); };
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})();
