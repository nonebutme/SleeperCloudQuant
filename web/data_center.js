(function () {
  "use strict";

  const select = (selector) => document.querySelector(selector);
  const selectAll = (selector) => [...document.querySelectorAll(selector)];
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  const json = async (path, options = {}) => {
    const response = await fetch(path, {
      method: options.method || "GET",
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `请求失败 (${response.status})`);
    return payload;
  };
  const feedback = (message, kind = "") => {
    const target = select("#global-feedback");
    if (!target) return;
    target.textContent = message;
    target.className = kind ? `feedback is-${kind}` : "feedback";
  };
  const pretty = (target, value) => {
    if (target) target.textContent = JSON.stringify(value, null, 2);
  };

  let loaded = false;
  let selectedRouteId = "";
  let latestPreview = null;
  const viewLabels = { overview: "M0 总览指挥舱", routes: "M1 源路由配置", sync: "M2 同步执行器", quality: "M3 质量纠错", assets: "M4 资产浏览", versions: "M5 快照管理" };
  const datasetLabels = {
    a_share_catalog: "A股证券目录",
    a_share_daily: "A股日线行情",
    trade_calendar: "A股交易日历",
    index_daily: "指数日线行情",
    corporate_actions: "公司行动与分红送转",
    index_components: "指数成分",
    industry_classification: "行业分类",
    financial_statements: "财务报表",
    global_index_daily: "全球指数日线",
    industry_board: "行业板块历史",
    concept_board: "概念板块历史",
    industry_flow: "行业历史资金流",
    concept_flow: "概念历史资金流",
    events: "个股公告与新闻",
    panorama_all: "全景板块与资金流",
    industry_classification_repair: "行业分类失败修复",
  };
  const providerLabels = { akshare: "AKShare 免费数据接口" };
  const upstreamLabels = {
    eastmoney: "东方财富",
    sina: "新浪财经",
    csindex: "中证指数",
    "public-finance-sites": "公开财经站点",
  };
  const stageLabels = {
    P0: "核心数据",
    P1: "扩展数据",
    P2: "可选数据",
    stage87: "阶段 87 待启用",
  };
  const localized = (mapping, value) => mapping[value] || value || "未配置";
  const statusLabels = {
    queued: "等待执行", running: "正在同步", validating: "质量校验", published: "已发布",
    completed_noop: "无需更新", partial_failure: "部分完成", failed: "执行失败",
    interrupted: "意外中断", stopping: "正在停止", stopped: "已停止",
    open: "待处理", quarantined: "已隔离", corrected: "已修正", accepted: "已确认",
    superseded: "历史版本",
  };
  const statusLabel = (value) => statusLabels[value] || value || "未知";
  const statusTone = (value) => ({ published: "good", completed_noop: "good", accepted: "good", corrected: "good", running: "info", validating: "info", queued: "muted", partial_failure: "warn", quarantined: "warn", interrupted: "warn", failed: "bad", open: "bad" }[value] || "muted");
  const formatBytes = (value) => {
    const bytes = Number(value || 0);
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
    if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    return `${Math.round(bytes / 1024).toLocaleString()} KB`;
  };
  const formatCount = (value) => Number(value || 0).toLocaleString("zh-CN");
  const progressPercent = (task) => task.total_items ? Math.min(100, Math.round(Number(task.completed_items || 0) / Number(task.total_items) * 100)) : 0;
const shortTaskId = (value) => String(value || "").replace("a-share-sync-", "同步-").replace("panorama-sync-", "全景-");
  const taskDatasetText = (task) => (task.adjustments || task.datasets || []).map((item) => ({ raw: "不复权", qfq: "前复权", hfq: "后复权" }[item] || localized(datasetLabels, item))).join(" / ");
  let syncPollTimer = null;

  function activateView(view) {
    selectAll("[data-dc-view]").forEach((button) => button.classList.toggle("is-active", button.dataset.dcView === view));
    selectAll(".dc-view").forEach((panel) => panel.classList.toggle("is-active", panel.id === `dc-view-${view}`));
  }

  async function loadOverview() {
    const { result } = await json("/api/data-center/overview");
    const defaultVersion = result.default_version;
    const issueTotal = Number(result.issue_counts?.open || 0) + Number(result.issue_counts?.quarantined || 0);
    const unfinished = Number(result.scheduler?.job_counts?.queued || 0) + Number(result.scheduler?.job_counts?.running || 0) + Number(result.scheduler?.job_counts?.partial_failure || 0) + Number(result.scheduler?.job_counts?.interrupted || 0);
    select("#dc-default-version").textContent = `基座版本：${defaultVersion?.data_version_id || "尚未发布"}`;
    select("#dc-health").textContent = `状态：${result.health === "healthy" ? "健康" : "需关注"}`;
    select("#dc-unpublished").textContent = `未发布观察：${result.has_unpublished_observations ? "存在" : "无"}`;
    select("#dc-footer-storage").textContent = `规范库占用：${formatBytes(result.database_size_bytes)}`;
    select("#dc-footer-latest").textContent = `最新行情：${result.latest_observation_date || "—"}`;
    select("#dc-footer-issues").textContent = `待处理：${formatCount(issueTotal + Number(result.scheduler?.job_counts?.partial_failure || 0))} 项`;
    const cards = [
      { icon: "◷", label: "数据新鲜度", value: result.latest_observation_date || "—", meta: `正式基座截止 ${result.published_cutoff || "—"}`, tone: result.has_unpublished_observations ? "warn" : "good", jump: "sync" },
      { icon: "▣", label: "本地存储", value: formatBytes(result.database_size_bytes), meta: "规范库当前占用", tone: "info" },
      { icon: "▥", label: "数据规模", value: formatCount(defaultVersion?.row_count), meta: `${formatCount(result.governance?.counts?.security_lifecycle_events)} 个证券生命周期`, tone: "info", jump: "assets" },
      { icon: "!", label: "待人工处理", value: formatCount(issueTotal + Number(result.scheduler?.job_counts?.partial_failure || 0)), meta: `${unfinished} 个未闭环同步任务`, tone: issueTotal || unfinished ? "warn" : "good", jump: issueTotal ? "quality" : "sync" },
    ];
    select("#dc-overview-metrics").innerHTML = cards.map((card) => `<button type="button" class="dc-status-card is-${card.tone}" ${card.jump ? `data-dc-jump="${card.jump}"` : ""}><span class="dc-card-icon">${card.icon}</span><span class="dc-card-label">${escapeHtml(card.label)}</span><strong>${escapeHtml(card.value)}</strong><small>${escapeHtml(card.meta)}</small></button>`).join("");
    const summary = [
      ["行情观察", result.latest_observation_date || "—", result.has_unpublished_observations ? "有未发布增量" : "与基座一致"],
      ["交易日历", formatCount(result.governance?.counts?.market_trade_calendar), "个日历事实"],
      ["公司行动", formatCount(result.governance?.counts?.corporate_action_events), "条治理记录"],
      ["复权因子", formatCount(result.governance?.counts?.price_adjustment_factors), "条因子记录"],
      ["自动调度", result.scheduler?.background_running ? "正在运行" : "当前未运行", `计划 ${result.scheduler?.run_time || "—"}`],
      ["最新快照", defaultVersion?.as_of_trade_date || "—", defaultVersion?.status === "published" ? "质量已通过" : statusLabel(defaultVersion?.status)],
    ];
    select("#dc-system-summary").innerHTML = summary.map(([label, value, meta]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(meta)}</small></div>`).join("");
    pretty(select("#dc-overview-output"), result);
    bindDynamicNavigation();
  }

  async function loadRoutes() {
    const { items } = await json("/api/data-center/routes");
    if (!selectedRouteId && items[0]) selectedRouteId = items[0].route_id;
    const selectedRoute = items.find((route) => route.route_id === selectedRouteId) || items[0];
    const groups = [
      ["行情数据", ["a_share_daily", "index_daily", "global_index_daily"]],
      ["证券与交易元数据", ["a_share_catalog", "trade_calendar", "index_components", "industry_classification"]],
      ["公司与财务数据", ["corporate_actions", "financial_statements"]],
    ];
    select("#dc-route-list").innerHTML = groups.map(([title, datasets]) => {
      const routes = items.filter((route) => datasets.includes(route.dataset));
      if (!routes.length) return "";
      return `<section class="dc-route-group"><h5>${escapeHtml(title)}</h5>${routes.map((route) => `<button type="button" class="dc-route-node ${route.route_id === selectedRoute?.route_id ? "is-active" : ""}" data-route-id="${escapeHtml(route.route_id)}"><span class="dc-route-check ${route.enabled ? "is-on" : ""}">${route.enabled ? "✓" : "—"}</span><span><strong>${escapeHtml(localized(datasetLabels, route.dataset))}</strong><small>${escapeHtml(localized(upstreamLabels, route.upstream))}</small></span><em class="dc-status-dot is-${route.last_error ? "bad" : "good"}"></em></button>`).join("")}</section>`;
    }).join("");
    select("#dc-route-detail").innerHTML = selectedRoute ? `<article class="dc-route-card" data-route-id="${escapeHtml(selectedRoute.route_id)}"><div class="dc-editor-heading"><div><span>${escapeHtml(localized(stageLabels, selectedRoute.lifecycle_stage))}</span><h4>${escapeHtml(localized(datasetLabels, selectedRoute.dataset))}</h4><p>${escapeHtml(localized(providerLabels, selectedRoute.provider))} · ${escapeHtml(localized(upstreamLabels, selectedRoute.upstream))}</p></div><span class="dc-route-health is-${selectedRoute.last_error ? "bad" : "good"}">${selectedRoute.last_error ? "连接异常" : "配置可用"}</span></div><div class="dc-form-grid"><label><span>参与全选同步</span><select data-route-field="enabled"><option value="true" ${selectedRoute.enabled ? "selected" : ""}>启用</option><option value="false" ${!selectedRoute.enabled ? "selected" : ""}>停用</option></select></label><label><span>Provider</span><input value="${escapeHtml(localized(providerLabels, selectedRoute.provider))}" disabled></label><label class="is-wide"><span>接口端点</span><input value="${escapeHtml(selectedRoute.endpoint)}" disabled></label><label><span>每分钟请求</span><input data-route-field="requests_per_minute" type="number" min="1" value="${selectedRoute.requests_per_minute}"></label><label><span>并发任务</span><input data-route-field="concurrency" type="number" min="1" max="16" value="${selectedRoute.concurrency}"></label><label><span>超时</span><input value="${selectedRoute.timeout_seconds} 秒" disabled></label><label><span>最大重试</span><input value="${selectedRoute.retry_count} 次" disabled></label></div><div class="dc-route-foot"><span>最近成功：${escapeHtml(selectedRoute.last_success_at || "尚未探测")}</span><span>最近延迟：${selectedRoute.last_latency_ms ? `${selectedRoute.last_latency_ms} ms` : "—"}</span></div></article>` : '<div class="empty-cell">请选择数据类型</div>';
    selectAll("[data-route-id].dc-route-node").forEach((button) => button.addEventListener("click", () => { selectedRouteId = button.dataset.routeId; loadRoutes().catch(showError); }));
  }

  async function saveRoutes() {
    const routes = selectAll(".dc-route-card").map((card) => ({
      route_id: card.dataset.routeId,
      enabled: card.querySelector("[data-route-field=enabled]").value === "true",
      requests_per_minute: Number(card.querySelector("[data-route-field=requests_per_minute]").value),
      concurrency: Number(card.querySelector("[data-route-field=concurrency]").value),
    }));
    if (!routes.length) throw new Error("请先选择数据类型");
    await json("/api/data-center/routes", { method: "PUT", body: { routes } });
    await loadRoutes();
    feedback("当前路由配置已应用，将影响之后创建的同步任务", "success");
  }

  async function testRoute() {
    if (!selectedRouteId) throw new Error("请先选择路由");
    const payload = await json("/api/data-center/routes/test", {
      method: "POST",
      body: { route_id: selectedRouteId, live: Boolean(select("#dc-route-live")?.checked) },
    });
    pretty(select("#dc-route-output"), payload.result);
    feedback(payload.result.status === "failed" ? "路由测试失败" : "路由测试完成（零写入）", payload.result.status === "failed" ? "error" : "success");
  }

  function syncRequest() {
    const form = new FormData(select("#dc-sync-form"));
    const allCurrent = form.get("scope") === "all_current";
    return {
      dataset: form.get("dataset") || "a_share_daily",
      target_trade_date: form.get("target_trade_date"),
      symbols: allCurrent ? [] : String(form.get("symbols") || "").split(",").map((item) => item.trim()).filter(Boolean),
      all_current: allCurrent,
      adjustments: [form.get("adjustments")],
      mode: "incremental",
      run_now: false,
    };
  }

  async function previewSync(event) {
    event.preventDefault();
    const { result } = await json("/api/data-center/sync/preview", { method: "POST", body: syncRequest() });
    latestPreview = result;
    const tasks = Array.isArray(result.tasks) ? result.tasks : [];
    const first = tasks[0];
    const panorama = Array.isArray(result.datasets) && result.dataset === "market_panorama";
    const scopeText = panorama
      ? (result.symbols?.length ? `${formatCount(result.symbols.length)} 个指定标的` : "全部板块")
      : (result.symbol_scope === "all_current" ? "全部当前股票" : `${formatCount(result.symbol_scope?.length)} 个指定标的`);
    const datasetText = panorama
      ? result.datasets.map((item) => localized(datasetLabels, item)).join("、")
      : (result.adjustments || []).map((item) => ({ raw: "不复权", qfq: "前复权", hfq: "后复权" }[item] || item)).join("、");
    select("#dc-sync-preview-output").innerHTML = `<div class="dc-preview-hero"><span>预计请求</span><strong>${formatCount(result.request_count)}</strong><small>预计耗时约 ${Math.max(1, Math.ceil(Number(result.estimated_seconds || 0) / 60))} 分钟</small></div><div class="dc-preview-lines"><div><span>任务模式</span><strong>增量补缺</strong></div><div><span>同步范围</span><strong>${escapeHtml(scopeText)}</strong></div><div><span>${panorama ? "数据集" : "价格口径"}</span><strong>${escapeHtml(datasetText)}</strong></div><div><span>目标交易日</span><strong>${escapeHtml(result.target_trade_date)}</strong></div></div>${first ? `<div class="dc-preview-range">分片示例：${escapeHtml(first.symbol)} ${escapeHtml(first.start_date)} → ${escapeHtml(result.target_trade_date)}${result.tasks_truncated ? "，其余分片已折叠" : ""}</div>` : `<div class="dc-preview-range ${Number(result.request_count || 0) ? "" : "is-good"}">${Number(result.request_count || 0) ? "将按所选数据集建立可恢复工作项" : "当前没有需要补齐的工作项"}</div>`}`;
    select("#dc-sync-create").disabled = false;
    feedback("同步预览已生成，确认后才会创建任务", "success");
  }

  async function createSync() {
    if (!latestPreview) throw new Error("请先生成分片预览");
    if (!window.confirm(`确认创建 ${latestPreview.request_count || 0} 个工作项的增量任务？`)) return;
    await json("/api/data-center/sync/tasks", { method: "POST", body: syncRequest() });
    latestPreview = null;
    select("#dc-sync-create").disabled = true;
    await loadTasks();
    feedback("同步任务已创建，可在任务记录中启动", "success");
  }

  async function loadTasks() {
    const { items } = await json("/api/data-center/sync/tasks");
    const active = items.find((task) => ["running", "validating", "stopping"].includes(task.status)) || items.find((task) => ["queued", "partial_failure", "interrupted"].includes(task.status));
    const activeTarget = select("#dc-sync-active");
    if (activeTarget) activeTarget.innerHTML = active ? `<div class="dc-live-heading"><div><span class="dc-status-pill is-${statusTone(active.status)}">${escapeHtml(statusLabel(active.status))}</span><strong>${escapeHtml(shortTaskId(active.job_id))}</strong></div><span>${progressPercent(active)}%</span></div><div class="dc-progress"><i style="width:${progressPercent(active)}%"></i></div><div class="dc-live-stats"><div><span>完成</span><strong>${formatCount(active.completed_items)} / ${formatCount(active.total_items)}</strong></div><div><span>写入</span><strong>${formatCount(active.rows_written)} 行</strong></div><div><span>隔离</span><strong>${formatCount(active.quarantined_items)}</strong></div><div><span>目标日</span><strong>${escapeHtml(active.target_trade_date)}</strong></div></div>${active.last_error ? `<div class="dc-inline-alert">${escapeHtml(active.last_error)}</div>` : ""}` : '<div class="empty-cell">当前没有运行中或待处理的任务</div>';
    select("#dc-sync-task-list").innerHTML = items.length ? items.slice(0, 30).map((task) => `<article class="dc-task-card"><div class="dc-task-main"><span class="dc-status-pill is-${statusTone(task.status)}">${escapeHtml(statusLabel(task.status))}</span><div><h4>${escapeHtml(shortTaskId(task.job_id))}</h4><p>${escapeHtml(task.target_trade_date)} · ${escapeHtml(taskDatasetText(task))} · ${task.symbol_scope === "all_current" ? "全市场" : escapeHtml(task.symbol_scope)}</p></div></div><div class="dc-task-progress"><div><i style="width:${progressPercent(task)}%"></i></div><strong>${progressPercent(task)}%</strong><span>${formatCount(task.completed_items)} / ${formatCount(task.total_items)}</span></div><div class="dc-task-meta"><span>写入 ${formatCount(task.rows_written)} 行</span><span>隔离 ${formatCount(task.quarantined_items)}</span><span>${escapeHtml(task.updated_at || task.created_at || "")}</span></div>${task.last_error ? `<div class="dc-task-error">${escapeHtml(task.last_error)}</div>` : ""}<div class="dc-inline-actions">${["queued", "running", "validating", "interrupted"].includes(task.status) ? `<button data-dc-stop="${escapeHtml(task.job_id)}" type="button" class="secondary-button">优雅停止</button>` : ""}${task.status === "queued" ? `<button data-dc-run="${escapeHtml(task.job_id)}" type="button">运行任务</button>` : ""}${["partial_failure", "failed", "interrupted"].includes(task.status) ? `<button data-dc-retry="${escapeHtml(task.job_id)}" type="button">仅重试失败项</button>` : ""}</div></article>`).join("") : '<div class="empty-cell">暂无同步任务</div>';
    selectAll("[data-dc-run]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("运行任务将调用免费上游并写入对应本地数据集，确认继续？")) return; try { button.disabled = true; feedback("同步任务已提交到独立后台进程，页面可以继续使用", "success"); await json(`/api/data-center/sync/tasks/${encodeURIComponent(button.dataset.dcRun)}/run`, { method: "POST", body: {} }); await Promise.all([loadTasks(), loadOverview(), loadVersions()]); } catch (error) { showViewError("sync", error); } finally { button.disabled = false; } }));
    selectAll("[data-dc-stop]").forEach((button) => button.addEventListener("click", async () => { try { await json(`/api/data-center/sync/tasks/${encodeURIComponent(button.dataset.dcStop)}/stop`, { method: "POST", body: {} }); await loadTasks(); } catch (error) { showViewError("sync", error); } }));
    selectAll("[data-dc-retry]").forEach((button) => button.addEventListener("click", async () => { try { await json(`/api/data-center/sync/tasks/${encodeURIComponent(button.dataset.dcRetry)}/retry-failed`, { method: "POST", body: { run_now: false } }); await loadTasks(); } catch (error) { showViewError("sync", error); } }));
    const recent = select("#dc-recent-tasks");
    if (recent) recent.innerHTML = items.slice(0, 5).map((task) => `<article class="dc-timeline-item is-${statusTone(task.status)}"><span class="dc-timeline-dot"></span><div><div><strong>${escapeHtml(statusLabel(task.status))}</strong><time>${escapeHtml(task.target_trade_date)}</time></div><p>${task.symbol_scope === "all_current" ? "全市场" : escapeHtml(task.symbol_scope)} · 完成 ${formatCount(task.completed_items)}/${formatCount(task.total_items)} · 隔离 ${formatCount(task.quarantined_items)}</p>${task.quarantined_items ? `<button type="button" data-dc-jump="sync">查看任务</button>` : ""}</div></article>`).join("") || '<div class="empty-cell">暂无近期同步</div>';
    bindDynamicNavigation();
    clearTimeout(syncPollTimer);
    if (items.some((task) => ["running", "validating", "stopping"].includes(task.status)) && select("#dc-view-sync")?.classList.contains("is-active")) syncPollTimer = setTimeout(() => loadTasks().catch((error) => showViewError("sync", error)), 3000);
  }

  async function loadQuality(event) {
    event?.preventDefault();
    const form = new FormData(select("#dc-quality-filter"));
    const query = new URLSearchParams([...form.entries()].filter(([, value]) => value)).toString();
    const { items } = await json(`/api/data-center/quality/issues${query ? `?${query}` : ""}`);
    const counts = items.reduce((summary, item) => ({ ...summary, [item.status]: Number(summary[item.status] || 0) + 1 }), {});
    select("#dc-quality-summary").innerHTML = [["待处理", counts.open || 0, "bad"], ["隔离中", counts.quarantined || 0, "warn"], ["已修正", counts.corrected || 0, "good"], ["当前结果", items.length, "info"]].map(([label, value, tone]) => `<div class="is-${tone}"><span>${label}</span><strong>${formatCount(value)}</strong><small>条记录</small></div>`).join("");
    select("#dc-quality-list").innerHTML = items.length ? `<div class="table-wrap"><table><thead><tr><th>代码 / 日期</th><th>数据类型</th><th>异常规则</th><th>严重度</th><th>状态</th><th>处置</th></tr></thead><tbody>${items.map((issue) => `<tr><td><strong>${escapeHtml(issue.symbol || "全局")}</strong><small>${escapeHtml(issue.observation_at || "—")}</small></td><td>${escapeHtml(localized(datasetLabels, issue.dataset))}</td><td><strong>${escapeHtml(issue.rule_id)}</strong><small>${escapeHtml(issue.source || "—")}</small></td><td><span class="dc-status-pill is-${issue.severity === "error" ? "bad" : "warn"}">${issue.severity === "error" ? "阻断" : "警告"}</span></td><td><span class="dc-status-pill is-${statusTone(issue.status)}">${escapeHtml(statusLabel(issue.status))}</span></td><td>${["open", "quarantined"].includes(issue.status) ? `<div class="dc-table-actions"><button data-dc-disposition="${escapeHtml(issue.issue_id)}" data-action="accept" type="button">确认</button><button data-dc-disposition="${escapeHtml(issue.issue_id)}" data-action="quarantine" type="button" class="secondary-button">隔离</button><button data-dc-disposition="${escapeHtml(issue.issue_id)}" data-action="correct" type="button">修正</button></div>` : "已留痕"}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty-cell">当前筛选条件下没有质量异常</div>';
    selectAll("[data-dc-disposition]").forEach((button) => button.addEventListener("click", () => disposition(button).catch(showError)));
  }

  async function disposition(button) {
    const action = button.dataset.action;
    const reason = window.prompt("请输入处置原因（必填）");
    if (!reason) return;
    const body = { action, reason, operator: "local-user" };
    if (action === "correct") {
      const before = window.prompt("原始值（JSON）", "{}");
      const after = window.prompt("修正值（JSON）", "{}");
      body.before = JSON.parse(before || "{}");
      body.after = JSON.parse(after || "{}");
    }
    const { result } = await json(`/api/data-center/quality/issues/${encodeURIComponent(button.dataset.dcDisposition)}/disposition`, { method: "POST", body });
    select("#dc-quality-output").innerHTML = `<div class="dc-disposition-result"><span class="dc-status-pill is-good">处置已记录</span><h4>${escapeHtml(result.issue_id || button.dataset.dcDisposition)}</h4><p>操作：${escapeHtml(action)} · 执行人：local-user</p><small>${escapeHtml(reason)}</small></div>`;
    await loadQuality();
  }

  async function loadVersions() {
    const { result } = await json("/api/data-center/versions");
    const active = result.items.find((version) => version.is_default) || result.items[0];
    select("#dc-version-active").innerHTML = active ? `<div class="dc-active-version-main"><span>当前活跃基座</span><h4>${escapeHtml(active.data_version_id)}</h4><p>数据截止 ${escapeHtml(active.as_of_trade_date)} · ${formatCount(active.row_count)} 行 · ${formatCount(active.member_count)} 类资产</p></div><div class="dc-active-version-state"><span class="dc-status-pill is-good">质量通过</span><small>质量报告 ${escapeHtml(active.quality_report_id)}</small></div>` : '<div class="empty-cell">尚无已发布数据版本</div>';
    select("#dc-version-list").innerHTML = result.items.length ? `<div class="table-wrap"><table><thead><tr><th>版本号</th><th>数据截止</th><th>规模</th><th>校验状态</th><th>发布时间</th><th>操作</th></tr></thead><tbody>${result.items.map((version) => `<tr class="${version.is_default ? "is-selected" : ""}"><td><strong>${escapeHtml(version.data_version_id)}</strong>${version.is_default ? '<small>当前默认</small>' : ""}</td><td>${escapeHtml(version.as_of_trade_date)}</td><td><strong>${formatCount(version.row_count)}</strong><small>${formatCount(version.member_count)} 类资产</small></td><td><span class="dc-status-pill is-${version.quality_report_id ? "good" : "warn"}">${version.quality_report_id ? "已通过" : "待校验"}</span></td><td>${escapeHtml(version.published_at || version.created_at || "—")}</td><td>${!version.is_default && ["published", "superseded"].includes(version.status) ? `<button data-dc-default="${escapeHtml(version.data_version_id)}" type="button">设为活跃</button>` : "—"}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty-cell">尚无正式数据版本</div>';
    selectAll("[data-dc-default]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("只切换默认指针；历史 Run 保持原版本。确认继续？")) return; await json(`/api/data-center/versions/${encodeURIComponent(button.dataset.dcDefault)}/set-default`, { method: "POST", body: {} }); await Promise.all([loadVersions(), loadOverview()]); }));
    pretty(select("#dc-version-output"), result);
  }

  function bindDynamicNavigation() {
    selectAll("[data-dc-jump]").forEach((button) => {
      if (button.dataset.dcBound) return;
      button.dataset.dcBound = "true";
      button.addEventListener("click", () => openDataCenterView(button.dataset.dcJump));
    });
    selectAll("[data-dc-asset-focus]").forEach((button) => {
      if (button.dataset.dcBound) return;
      button.dataset.dcBound = "true";
      button.addEventListener("click", () => {
        const targets = { overview: "#a-share-overview", symbols: "#a-share-symbol-form", daily: "#a-share-daily-form" };
        select(targets[button.dataset.dcAssetFocus])?.closest(".panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function showError(error) {
    feedback(error.message || String(error), "error");
  }

  function showViewError(view, error) {
    const message = `${viewLabels[view] || view} 加载失败：${error.message || String(error)}`;
    const targets = {
      overview: ["#dc-overview-metrics", "#dc-overview-output"],
      routes: ["#dc-route-list", "#dc-route-output"],
      sync: ["#dc-sync-task-list", "#dc-sync-preview-output"],
      quality: ["#dc-quality-list", "#dc-quality-output"],
      versions: ["#dc-version-list", "#dc-version-output"],
    };
    const [listSelector, outputSelector] = targets[view] || [];
    const list = select(listSelector);
    if (list) list.innerHTML = `<div class="empty-cell dc-load-error">${escapeHtml(message)}<br><small>请重启本地 Web 服务后重试。</small></div>`;
    const output = select(outputSelector);
    if (output) output.textContent = message;
    feedback(message, "error");
  }

  async function loadView(view) {
    try {
      if (view === "overview") {
        const loaders = [loadOverview(), loadTasks()];
        if (typeof loadAShareOverview === "function") loaders.push(loadAShareOverview());
        await Promise.all(loaders);
      }
      else if (view === "routes") await loadRoutes();
      else if (view === "sync") await loadTasks();
      else if (view === "quality") await loadQuality();
      else if (view === "versions") await loadVersions();
      loaded = true;
    } catch (error) {
      showViewError(view, error);
    }
  }

  async function loadAll() {
    const views = ["overview", "routes", "sync", "quality", "versions"];
    await Promise.allSettled(views.map((view) => loadView(view)));
    loaded = true;
  }

  function openDataCenterView(view) {
    if (typeof activatePage === "function") activatePage("market");
    else select('.nav-tab[data-page="market"]')?.click();
    activateView(view);
    const url = new URL(window.location.href);
    url.searchParams.set("page", "market");
    url.searchParams.set("dc_view", view);
    window.history.replaceState({}, "", url);
    loadView(view);
  }

  function bind() {
    bindDynamicNavigation();
    selectAll("[data-dc-view]").forEach((button) => button.addEventListener("click", () => openDataCenterView(button.dataset.dcView)));
    select("#dc-overview-refresh")?.addEventListener("click", () => loadView("overview"));
    select("#dc-routes-save")?.addEventListener("click", () => saveRoutes().catch((error) => showViewError("routes", error)));
    select("#dc-route-test")?.addEventListener("click", () => testRoute().catch((error) => showViewError("routes", error)));
    select("#dc-sync-form")?.addEventListener("submit", (event) => previewSync(event).catch((error) => showViewError("sync", error)));
    select("#dc-sync-create")?.addEventListener("click", () => createSync().catch((error) => showViewError("sync", error)));
    select("#dc-quality-filter")?.addEventListener("submit", (event) => loadQuality(event).catch((error) => showViewError("quality", error)));
    select("#dc-versions-refresh")?.addEventListener("click", () => loadView("versions"));
    selectAll('.nav-tab[data-page="market"]').forEach((button) => button.addEventListener("click", () => {
      activateView("overview");
      loadView("overview");
    }));
    const params = new URLSearchParams(window.location.search);
    const requestedView = viewLabels[params.get("dc_view")] ? params.get("dc_view") : "overview";
    if (params.get("page") === "market" || select("#page-market")?.classList.contains("is-active")) {
      activateView(requestedView);
      loadView(requestedView);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
}());
