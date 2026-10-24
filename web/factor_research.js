(function () {
  "use strict";

  const q = (selector) => document.querySelector(selector);
  const state = {
    definitions: [],
    dashboardRows: [],
    r3Studies: [],
    r3StudyMeta: {},
    tasks: [],
    artifacts: [],
    optimizationTasks: [],
    currentTaskId: "",
    currentReportId: "",
    currentArtifactId: "",
    currentOptimizationTaskId: "",
    currentDeclaration: null,
    lastPreflight: null,
    pollTimer: null,
    optimizationPollTimer: null,
    currentProfileFactorId: "",
    currentProfileDefinition: null,
    currentView: "dashboard",
    reportReturnView: "tasks",
  };
  const INDEX_UNAVAILABLE_REASON = "index_component_facts_unavailable";
  const FACTOR_VIEW_LABELS = Object.freeze({
    dashboard: "因子库",
    development: "因子开发",
    detail: "因子研究",
    tasks: "研究任务",
    report: "研究报告",
    multi: "多因子研究",
    artifacts: "因子发布与应用",
  });

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function metric(value, digits) {
    const number = Number(value);
    return value == null || !Number.isFinite(number)
      ? "—"
      : number.toFixed(digits == null ? 4 : digits);
  }

  function percent(value) {
    const number = Number(value);
    return value == null || !Number.isFinite(number)
      ? "—"
      : (number * 100).toFixed(2) + "%";
  }

  function syncFactorPageTitle(view = state.currentView) {
    if (!q("#page-factor")?.classList.contains("is-active")) return;
    const target = q("#page-title");
    if (target) target.textContent = "因子分析 / " + (FACTOR_VIEW_LABELS[view] || "因子分析");
  }
  window.syncFactorPageTitle = syncFactorPageTitle;

  function activateView(view, syncRoute = true) {
    const previousView = state.currentView;
    if (view === "report" && previousView !== "report") state.reportReturnView = previousView;
    state.currentView = view;
    document.querySelectorAll("[data-factor-view]").forEach((panel) => {
      const active = panel.dataset.factorView === view;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    document.querySelectorAll("[data-factor-view-target]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.factorViewTarget === view);
    });
    if (syncRoute) {
      const url = new URL(window.location.href);
      url.searchParams.set("page", "factor");
      url.searchParams.set("factor_view", view);
      window.history.replaceState({}, "", url);
    }
    if (view === "artifacts" && !state.artifacts.length) {
      Promise.all([loadArtifacts(), loadOptimizationTasks()])
        .catch((error) => setFeedback(error.message, "error"));
    }
    syncFactorPageTitle(view);
    window.AppVTable?.enhanceAll(document);
  }
  window.activateFactorView = activateView;

  function configPayload() {
    const form = q("#factor-research-form");
    const data = Object.fromEntries(new FormData(form).entries());
    return {
      factor_id: data.factor_id,
      start_date: data.start_date,
      end_date: data.end_date,
      pool_type: data.pool_type,
      pool_code: data.pool_type === "index" ? data.pool_code : null,
      pool_as_of_date: data.end_date,
      symbols: String(data.symbols || "").split(",").map((item) => item.trim()).filter(Boolean),
      symbol_limit: Number(data.symbol_limit || 0),
      research_mode: data.research_mode,
      acceptance_policy_id: data.acceptance_policy_id,
      sample_split: {
        training: Number(data.split_training || 0.6),
        validation: Number(data.split_validation || 0.2),
        out_of_sample: Number(data.split_out_of_sample || 0.2),
      },
      factor_adjustment: data.factor_adjustment,
      outcome_adjustment: data.outcome_adjustment,
      forward_horizons: [Number(data.forward_horizon || 5)],
      preprocessing: {
        winsor_mad: Number(data.winsor_mad || 0),
        standardize: form.elements.standardize.checked,
        industry_neutral: form.elements.industry_neutral.checked,
      },
      group_count: Number(data.group_count || 5),
      cost_assumption: { one_side_rate: Number(data.one_side_rate || 0) },
    };
  }

  function definitionPayload() {
    return Object.fromEntries(new FormData(q("#factor-definition-form")).entries());
  }

  async function validateDefinition() {
    const payload = await requestJson("/api/factor-research/definitions/validate", {
      method: "POST",
      body: JSON.stringify(definitionPayload()),
    });
    const output = q("#factor-definition-output");
    output.hidden = false;
    output.textContent = "校验通过：输入字段 " + payload.validation.input_fields.join(", ") +
      "；最少历史 " + payload.validation.minimum_history + " 个交易日";
    setFeedback("自定义因子表达式校验通过", "success");
    return payload;
  }

  async function publishDefinition(event) {
    event.preventDefault();
    const payload = await requestJson("/api/factor-research/definitions", {
      method: "POST",
      body: JSON.stringify(definitionPayload()),
    });
    const factorId = payload.definition.factor_id;
    const output = q("#factor-definition-output");
    output.hidden = false;
    output.textContent = "已冻结 " + factorId + " " + payload.definition.factor_version +
      "；任务将冻结该版本与表达式哈希。";
    await window.loadFactors({ factor_id: factorId });
    const select = q("#factor-research-form select[name=factor_id]");
    if (select) select.value = factorId;
    renderDefinition(factorId);
    activateView("detail");
    setFeedback("因子版本已冻结，可继续预检并创建分析任务", "success");
  }

  function populateSelectors(definitions) {
    const options = definitions.map((item) =>
      '<option value="' + escapeHtml(item.factor_id) + '">' +
      escapeHtml(item.name) + " · " + escapeHtml(item.factor_id) + "</option>"
    ).join("");
    const configSelect = q('#factor-research-form select[name="factor_id"]');
    const dashboardSelect = q('#factor-dashboard-form select[name="factor_id"]');
    const configValue = configSelect?.value;
    const dashboardValue = dashboardSelect?.value;
    if (configSelect) {
      configSelect.innerHTML = options;
      if (definitions.some((item) => item.factor_id === configValue)) configSelect.value = configValue;
    }
    if (dashboardSelect) {
      dashboardSelect.innerHTML = '<option value="">全部因子</option>' + options;
      if (definitions.some((item) => item.factor_id === dashboardValue)) dashboardSelect.value = dashboardValue;
    }
    renderDefinition(configSelect?.value || definitions[0]?.factor_id);
  }

  function renderDefinition(factorId) {
    const item = state.definitions.find((definition) => definition.factor_id === factorId);
    const target = q("#factor-definition-detail");
    if (!target) return;
    target.innerHTML = item
      ? "<div><strong>" + escapeHtml(item.name) + "</strong><span>" +
        escapeHtml(item.category) + " · " + escapeHtml(item.factor_version) +
        "</span></div><p>" + escapeHtml(item.description) + "</p><code>" +
        escapeHtml(item.formula) + "</code><small>输入：" +
        escapeHtml((item.input_fields || []).join(", ")) + "；最少历史：" +
        escapeHtml(item.minimum_history) + "；方向：" + escapeHtml(item.direction) + "</small>"
      : '<div class="empty-cell">暂无因子定义</div>';
  }

  function renderDashboard(payload) {
    const rows = payload.items || [];
    state.dashboardRows = rows;
    const contextSelect = q('#factor-dashboard-form select[name="context_id"]');
    if (contextSelect) {
      const selected = payload.filters?.context_id || "";
      contextSelect.innerHTML = (payload.filters?.contexts || []).map((item) =>
        '<option value="' + escapeHtml(item.context_id) + '">' +
        escapeHtml(item.label) + "</option>"
      ).join("") || '<option value="">尚无可比较的研究口径</option>';
      contextSelect.value = selected;
    }
    renderSummaryGrid(q("#factor-dashboard-summary"), [
      { label: "登记因子", value: rows.length },
      { label: "已有报告", value: rows.filter((row) => row.latest_report_id).length },
      { label: "当前对比口径", value: String(payload.filters?.context_id || "尚无报告").slice(0, 12) },
      { label: "可选口径", value: (payload.filters?.contexts || []).length },
    ]);
    q("#factor-dashboard-body").innerHTML = rows.map((row) =>
      "<tr><td>" + escapeHtml(row.name) + "<br><small>" + escapeHtml(row.factor_id) +
      "</small></td><td>" + escapeHtml(row.category) + "</td><td>" +
      escapeHtml(row.factor_version) + "</td><td>" + escapeHtml(row.latest_status) +
      "</td><td>" + metric(row.rank_ic_mean) + "</td><td>" +
      metric(row.direction_aligned_rank_ic_mean) + "</td><td>" + metric(row.icir) +
      "</td><td>" + percent(row.factor_coverage) + "</td><td>" +
      percent(row.max_drawdown) + "</td><td>" + percent(row.turnover) +
      '</td><td><button type="button" data-factor-open-profile="' +
      escapeHtml(row.factor_id) + '">详情</button></td><td><button type="button" data-factor-open-definition="' +
      escapeHtml(row.factor_id) + '">开始研究</button></td><td>' +
      (row.latest_report_id ? '<button type="button" data-factor-open-report="' +
      escapeHtml(row.latest_report_id) + '">查看报告</button>' : "暂无报告") + "</td></tr>"
    ).join("") || '<tr><td colspan="13" class="empty-cell">暂无因子</td></tr>';
    window.AppVTable?.enhanceAll(document);
  }

  function activateFactorProfileTab(tab) {
    document.querySelectorAll("[data-factor-profile-tab]").forEach((button) => {
      const active = button.dataset.factorProfileTab === tab;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll("[data-factor-profile-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.factorProfilePanel !== tab;
    });
    window.AppVTable?.enhanceAll(q("#factor-profile-dialog") || document);
  }

  function renderFactorProfileOverview(item) {
    const target = q("#factor-profile-content");
    target.innerHTML = "<div><strong>" + escapeHtml(item.name) + "</strong><span>" +
      escapeHtml(item.category) + " · " + escapeHtml(item.factor_version) + " · " +
      escapeHtml(item.status || "published") + "</span></div><p>" +
      escapeHtml(item.description || "尚未填写因子说明") + "</p><code>" +
      escapeHtml(item.formula || item.expression || "—") + "</code><small>输入字段：" +
      escapeHtml((item.input_fields || []).join(", ") || "—") + "；最少历史：" +
      escapeHtml(item.minimum_history ?? "—") + "；方向：" +
      escapeHtml(item.direction || "—") + "；定义类型：" +
      escapeHtml(item.definition_type || "—") + "</small>";
    q("#factor-profile-title").textContent = item.name + " · 因子详情";
  }

  function renderFactorProfileEvidence(factorId) {
    const report = state.dashboardRows.find((item) => item.factor_id === factorId) || {};
    const studies = state.r3Studies.filter((item) => item.factor_id === factorId);
    const acceptedCount = studies.filter((item) => item.accepted).length;
    renderSummaryGrid(q("#factor-profile-evidence-summary"), [
      { label: "最近研究", value: report.latest_status || "尚无报告" },
      { label: "报告编号", value: report.latest_report_id || "—" },
      { label: "R3 封存证据", value: studies.length ? studies.length + " 项" : "暂无匹配证据" },
      { label: "R3 已验收", value: studies.length ? acceptedCount + " / " + studies.length : "—" },
    ]);
    q("#r3-study-body").innerHTML = studies.map((row) => {
      const h = row.holdout || {};
      return "<tr><td>R3 封存研究<br><small>" + escapeHtml(row.data_version_id || row.source || "—") +
        "</small></td><td>" + escapeHtml(row.status) + "</td><td>" + escapeHtml(h.periods) +
        "</td><td>" + escapeHtml(h.known_periods) + "</td><td>" + metric(h.rank_ic) +
        "</td><td>" + percent(h.mean_net_excess) + "</td><td>" + percent(h.mean_stress_excess) +
        "</td><td>" + escapeHtml(h.unknown_exits) + "</td><td>" +
        (h.holm_p == null ? "未计算" : metric(h.holm_p)) + "</td></tr>";
    }).join("") || '<tr><td colspan="9" class="empty-cell">该因子暂无独立 R3 封存证据；可先开始标准研究生成报告。</td></tr>';
    q("#factor-profile-report-action").innerHTML = report.latest_report_id
      ? '<button type="button" data-factor-open-report="' + escapeHtml(report.latest_report_id) +
        '">打开最近研究报告</button>'
      : '<span class="empty-cell">尚无标准研究报告</span>';
    window.AppVTable?.enhanceAll(q("#factor-profile-dialog") || document);
  }

  function renderFactorProfileVersions(versions) {
    q("#factor-profile-version-body").innerHTML = versions.map((item) =>
      "<tr><td>" + escapeHtml(item.factor_version || "—") + "</td><td>" +
      escapeHtml(item.status || "—") + "</td><td>" + escapeHtml(item.definition_type || "builtin") +
      "</td><td>" + escapeHtml(item.formula || item.expression || "—") + "</td><td>" +
      escapeHtml(item.registered_at || "—") + "</td><td>" +
      escapeHtml(String(item.metadata_hash || item.expression_hash || "—").slice(0, 12)) + "</td></tr>"
    ).join("") || '<tr><td colspan="6" class="empty-cell">暂无版本记录</td></tr>';
    window.AppVTable?.enhanceAll(q("#factor-profile-dialog") || document);
  }

  async function openFactorProfile(factorId) {
    const fallback = state.definitions.find((definition) => definition.factor_id === factorId);
    if (!fallback) throw new Error("未找到因子定义");
    state.currentProfileFactorId = factorId;
    state.currentProfileDefinition = fallback;
    renderFactorProfileOverview(fallback);
    renderFactorProfileEvidence(factorId);
    renderFactorProfileVersions([fallback]);
    const createButton = q("#factor-profile-create-version");
    const editable = fallback.definition_type === "expression";
    createButton.disabled = !editable;
    createButton.textContent = editable ? "基于当前版本创建新版" : "内置因子不可编辑";
    activateFactorProfileTab("overview");
    const dialog = q("#factor-profile-dialog");
    if (dialog?.showModal) dialog.showModal();
    else if (dialog) dialog.setAttribute("open", "");
    const payload = await requestJson("/api/factor-research/definitions/" + encodeURIComponent(factorId));
    const item = payload.definition || fallback;
    state.currentProfileDefinition = item;
    renderFactorProfileOverview(item);
    renderFactorProfileVersions(payload.versions || [item]);
  }

  function renderR3Studies(payload) {
    state.r3Studies = payload.items || [];
    state.r3StudyMeta = payload;
    if (state.currentProfileFactorId) renderFactorProfileEvidence(state.currentProfileFactorId);
  }

  async function loadR3Studies() {
    const payload = await requestJson("/api/factor-research/r3-studies");
    renderR3Studies(payload);
    return payload;
  }

  function startResearchForFactor(factorId) {
    const select = q('#factor-research-form select[name="factor_id"]');
    if (select) select.value = factorId;
    renderDefinition(factorId);
    q("#factor-profile-dialog")?.close();
    activateView("detail");
  }

  function resetDefinitionForm() {
    const form = q("#factor-definition-form");
    if (!form) return;
    form.reset();
    form.elements.factor_id.readOnly = false;
    q("#factor-definition-output").hidden = true;
    activateView("development");
  }

  function createVersionFromProfile() {
    const item = state.currentProfileDefinition;
    if (!item || item.definition_type !== "expression") return;
    const form = q("#factor-definition-form");
    form.elements.factor_id.value = item.factor_id || "";
    form.elements.factor_id.readOnly = true;
    form.elements.name.value = item.name || "";
    form.elements.category.value = item.category || "自定义";
    form.elements.direction.value = item.direction || "positive";
    form.elements.expression.value = item.expression || item.formula || "";
    form.elements.description.value = item.description || "";
    q("#factor-definition-output").hidden = true;
    q("#factor-profile-dialog")?.close();
    activateView("development");
    form.elements.expression.focus();
  }

  function renderCurrentTask() {
    const selected = q("#factor-task-select")?.value || state.currentTaskId;
    const task = state.tasks.find((item) => item.task_id === selected);
    if (!task) {
      renderSummaryGrid(q("#factor-task-progress"), [{ label: "任务", value: "尚未选择" }]);
      q("#factor-task-output").textContent = "请选择任务";
      return;
    }
    state.currentTaskId = task.task_id;
    const progress = task.progress || {};
    renderSummaryGrid(q("#factor-task-progress"), [
      { label: "状态", value: task.status },
      { label: "阶段", value: progress.phase || "—" },
      { label: "进度", value: percent(Number(progress.percent || 0) / 100) },
      { label: "标的", value: (progress.processed_symbols || 0) + " / " + (progress.total_symbols || 0) },
      { label: "观测", value: progress.observation_count || 0 },
      { label: "上下文", value: String(task.context_hash || "").slice(0, 12) || "—" },
    ]);
    q("#factor-task-output").textContent = JSON.stringify(task, null, 2);
  }

  function renderTasks(payload) {
    state.tasks = payload.items || [];
    const select = q("#factor-task-select");
    if (select) {
      const selected = state.currentTaskId || select.value;
      select.innerHTML = '<option value="">请选择任务</option>' + state.tasks.map((task) =>
        '<option value="' + escapeHtml(task.task_id) + '">' +
        escapeHtml(task.task_id) + " · " + escapeHtml(task.status) + "</option>"
      ).join("");
      if (state.tasks.some((task) => task.task_id === selected)) select.value = selected;
    }
    q("#factor-task-body").innerHTML = state.tasks.map((task) => {
      const progress = task.progress || {};
      const config = task.config || {};
      return "<tr><td>" + escapeHtml(task.task_id) + "</td><td>" +
        escapeHtml(config.factor_id) + "</td><td>" +
        escapeHtml(config.pool_code || config.pool_type) + "</td><td>" +
        escapeHtml(task.status) + "</td><td>" + escapeHtml(progress.phase || "—") +
        "</td><td>" + escapeHtml(progress.processed_symbols || 0) + " / " +
        escapeHtml(progress.total_symbols || 0) + "</td><td>" +
        escapeHtml(task.data_version_id) + "</td><td>" +
        (task.report_id ? '<button type="button" data-factor-open-report="' +
        escapeHtml(task.report_id) + '">打开报告</button>' : "—") + "</td></tr>";
    }).join("") || '<tr><td colspan="8" class="empty-cell">暂无研究任务</td></tr>';
    renderCurrentTask();
    window.AppVTable?.enhanceAll(document);
  }

  function renderPreflight(payload) {
    state.lastPreflight = payload;
    const version = payload.data_version || {};
    const pool = payload.pool_snapshot || {};
    renderSummaryGrid(q("#factor-preflight-summary"), [
      { label: "状态", value: payload.status },
      { label: "数据版本", value: version.data_version_id || "—" },
      { label: "选择策略", value: version.selection_policy || "—" },
      { label: "有效区间", value: payload.effective_range
        ? payload.effective_range.start_date + " 至 " + payload.effective_range.end_date : "—" },
      { label: "标的数", value: pool.symbols?.length ?? 0 },
      { label: "上下文", value: String(payload.context_hash || "").slice(0, 12) || "—" },
    ]);
    const reasons = payload.reasons || [];
    const reasonTarget = q("#factor-preflight-reasons");
    reasonTarget.hidden = !reasons.length;
    reasonTarget.textContent = reasons.join("；");
    q("#factor-preflight-output").textContent = JSON.stringify(payload, null, 2);
    q("#factor-config-state").textContent = payload.status === "ready" ? "预检通过" : "预检不可用";
  }

  async function loadTasks() {
    const payload = await requestJson("/api/factor-research/tasks?limit=50");
    renderTasks(payload);
    const current = state.tasks.find((item) => item.task_id === state.currentTaskId);
    if (current && ["running", "stop_requested"].includes(current.status)) schedulePoll();
    return payload;
  }

  window.loadFactors = async function loadFactors(params) {
    params = params || {};
    const query = buildQuery({
      factor_id: params.factor_id || "",
      pool_type: params.pool_type || "",
      context_id: params.context_id || "",
    });
    const [definitions, dashboard, tasks, r3Studies] = await Promise.all([
      requestJson("/api/factor-research/definitions"),
      requestJson("/api/factor-research/dashboard?" + query),
      requestJson("/api/factor-research/tasks?limit=50"),
      requestJson("/api/factor-research/r3-studies"),
    ]);
    state.definitions = definitions.items || [];
    populateSelectors(state.definitions);
    renderDashboard(dashboard);
    renderTasks(tasks);
    renderR3Studies(r3Studies);
    return { definitions: { definitions: state.definitions }, dashboard: dashboard, tasks: tasks };
  };

  async function runPreflight() {
    const payload = await requestJson("/api/factor-research/preflight", {
      method: "POST",
      body: JSON.stringify(configPayload()),
    });
    renderPreflight(payload);
    setFeedback(payload.status === "ready" ? "因子研究预检通过" : "因子研究预检不可用",
      payload.status === "ready" ? "success" : "error");
    return payload;
  }

  async function createTask(event) {
    event.preventDefault();
    const preflight = await runPreflight();
    if (preflight.status !== "ready") return;
    const task = await requestJson("/api/factor-research/tasks", {
      method: "POST",
      body: JSON.stringify(configPayload()),
    });
    state.currentTaskId = task.task_id;
    await loadTasks();
    activateView("tasks");
    setFeedback("已创建因子研究任务：" + task.task_id, "success");
  }

  async function controlTask(action) {
    const taskId = q("#factor-task-select")?.value || state.currentTaskId;
    if (!taskId) throw new Error("请先选择研究任务");
    const suffix = action === "retry" ? "retry-failed" : action;
    const task = await requestJson("/api/factor-research/tasks/" +
      encodeURIComponent(taskId) + "/" + suffix, { method: "POST" });
    state.currentTaskId = task.task_id;
    await loadTasks();
    if (action === "start" || action === "retry") schedulePoll();
    setFeedback("任务状态：" + task.status, "success");
  }

  function schedulePoll() {
    if (state.pollTimer) return;
    state.pollTimer = window.setInterval(async () => {
      try {
        await loadTasks();
        const task = state.tasks.find((item) => item.task_id === state.currentTaskId);
        if (!task || !["running", "stop_requested"].includes(task.status)) {
          window.clearInterval(state.pollTimer);
          state.pollTimer = null;
          if (task?.report_id) await loadReport(task.report_id);
        }
      } catch (error) {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
        setFeedback(error.message, "error");
      }
    }, 1500);
  }

  function renderReportNavigation(reportId, payload) {
    const sourceTask = state.tasks.find((item) => item.report_id === reportId);
    const returnView = state.reportReturnView && state.reportReturnView !== "report"
      ? state.reportReturnView : "tasks";
    const backButton = q("#factor-report-back");
    if (backButton) {
      backButton.dataset.factorReturnView = returnView;
      backButton.textContent = "返回" + (FACTOR_VIEW_LABELS[returnView] || "研究任务");
    }
    const context = q("#factor-report-context");
    if (context) {
      const parts = [
        sourceTask ? "来源任务：" + sourceTask.task_id : "来源：因子库或历史报告",
        "因子：" + (payload.definition?.name || payload.config?.factor_id || "—"),
        "报告：" + reportId,
      ];
      context.textContent = parts.join(" · ");
    }
  }

  async function loadReport(reportId) {
    if (!reportId) throw new Error("当前任务还没有可用报告");
    const report = await requestJson("/api/factor-research/reports/" + encodeURIComponent(reportId));
    if (report.status !== "ready") throw new Error("报告尚未就绪");
    state.currentReportId = reportId;
    const payload = report.payload || {};
    const analysis = payload.analysis || {};
    const horizon = String((payload.config?.forward_horizons || [5])[0]);
    const primary = analysis.ic?.[horizon] || {};
    const persistenceValues = (analysis.signal_persistence || []).map((row) =>
      Number(row.rank_correlation)).filter(Number.isFinite);
    const averagePersistence = persistenceValues.length
      ? persistenceValues.reduce((sum, value) => sum + value, 0) / persistenceValues.length : null;
    const credibility = payload.credibility || {};
    const artifact = payload.artifact || {};
    const acceptance = payload.acceptance || {};
    const revealToolbar = q("#factor-oos-reveal-toolbar");
    if (revealToolbar) revealToolbar.hidden = payload.oos_reveal?.status !== "sealed";
    const credibilityTarget = q("#factor-report-credibility");
    if (credibilityTarget) credibilityTarget.innerHTML =
      "<strong>历史研究证据</strong> · 制品 " + escapeHtml(artifact.artifact_id || "未发布") +
      " · 数据版本 " + escapeHtml(credibility.data_version_id || "-") +
      " · 未建模市场冲击，未做模拟盘/实盘验证；不构成投资建议。";    renderSummaryGrid(q("#factor-report-summary"), [
      { label: "因子", value: payload.definition?.name || "—" },
      { label: "股票池", value: payload.config?.pool_code || payload.config?.pool_type || "—" },
      { label: "有效区间", value: payload.effective_range
        ? payload.effective_range.start_date + " 至 " + payload.effective_range.end_date : "—" },
      { label: "因子覆盖率", value: percent(analysis.coverage?.average_factor_coverage) },
      { label: "Rank IC", value: metric(primary.rank_ic_mean) },
      { label: "方向 Rank IC", value: metric(primary.direction_aligned_rank_ic_mean) },
      { label: "ICIR", value: metric(primary.icir) },
      { label: "HAC t", value: metric(primary.rank_ic_hac_t_value) },
      { label: "正 IC 比例", value: percent(primary.positive_aligned_rank_ic_ratio) },
      { label: "因子秩自相关", value: metric(averagePersistence) },
      { label: "最大回撤", value: percent(analysis.group_analysis?.max_drawdown) },
      { label: "最终净值", value: metric(analysis.group_analysis?.final_nav) },
      { label: "估算成本", value: percent(analysis.execution_estimate?.estimated_cost) },
    ]);
    renderSummaryGrid(q("#factor-acceptance-summary"), [
      { label: "研究级别", value: payload.config?.research_mode || "legacy" },
      { label: "验收政策", value: acceptance.policy_id || "—" },
      { label: "研究结论", value: acceptance.decision || acceptance.status || "—" },
      { label: "策略可用", value: acceptance.strategy_eligible ? "是" : "否，待审批登记" },
    ]);
    q("#factor-acceptance-body").innerHTML = (acceptance.checks || []).map((row) =>
      "<tr><td>" + escapeHtml(row.metric) + "</td><td>" + metric(row.actual) +
      "</td><td>" + escapeHtml(row.operator) + " " + metric(row.threshold) +
      "</td><td>" + escapeHtml(row.status) + "</td></tr>"
    ).join("") || '<tr><td colspan="4" class="empty-cell">探索研究不执行策略准入验收</td></tr>';
    const samples = analysis.sample_analysis || {};
    q("#factor-sample-body").innerHTML = Object.entries(samples).map(([name, item]) => {
      const samplePrimary = item.ic?.[horizon] || {};
      return "<tr><td>" + escapeHtml(name) + "</td><td>" +
        escapeHtml((samplePrimary.series || []).length) + "</td><td>" +
        metric(samplePrimary.direction_aligned_rank_ic_mean) + "</td><td>" +
        metric(samplePrimary.rank_ic_hac_t_value) + "</td><td>" +
        percent(samplePrimary.positive_aligned_rank_ic_ratio) + "</td><td>" +
        metric(item.execution_estimate?.net_return_estimate) + "</td></tr>";
    }).join("") || '<tr><td colspan="6" class="empty-cell">旧报告未冻结样本切分</td></tr>';
    const distribution = analysis.distribution || {};
    q("#factor-distribution-body").innerHTML = distribution.status === "ready"
      ? "<tr><td>" + escapeHtml(distribution.count) + "</td><td>" + metric(distribution.mean) +
        "</td><td>" + metric(distribution.std) + "</td><td>" + metric(distribution.p01) +
        "</td><td>" + metric(distribution.median) + "</td><td>" + metric(distribution.p99) + "</td></tr>"
      : '<tr><td colspan="6" class="empty-cell">分布数据不可用</td></tr>';
    q("#factor-group-body").innerHTML = (analysis.group_analysis?.series || []).slice(-100).map((row) =>
      "<tr><td>" + escapeHtml(row.trade_date) + "</td>" + [1, 2, 3, 4, 5].map((group) =>
        "<td>" + metric(row.returns?.[String(group)]) + "</td>"
      ).join("") + "<td>" + metric(row.top_bottom_gross_return) + "</td><td>" +
      metric(row.estimated_cost) + "</td><td>" + metric(row.top_bottom_net_return_estimate) + "</td></tr>"
    ).join("") || '<tr><td colspan="9" class="empty-cell">分组数据不可用</td></tr>';
    renderSeriesChart(q("#factor-ic-chart"), (primary.series || []).filter((row) =>
      Number.isFinite(Number(row.direction_aligned_rank_ic))).map((row) =>
      ({ trade_date: row.trade_date, value: row.direction_aligned_rank_ic })),
      "trade_date", "value");
    renderSeriesChart(q("#factor-nav-chart"), analysis.group_analysis?.nav || [],
      "trade_date", "nav");
    q("#factor-decay-body").innerHTML = (analysis.decay || []).map((row) =>
      "<tr><td>" + escapeHtml(row.horizon) + " 日</td><td>" +
      metric(row.rank_ic_mean) + "</td><td>" +
      metric(row.direction_aligned_rank_ic_mean) + "</td></tr>"
    ).join("") || '<tr><td colspan="3" class="empty-cell">暂无衰减数据</td></tr>';
    q("#factor-industry-body").innerHTML = (analysis.industry_ic || []).map((row) =>
      "<tr><td>" + escapeHtml(row.industry) + "</td><td>" +
      escapeHtml(row.sample_count) + "</td><td>" + metric(row.rank_ic) + "</td></tr>"
    ).join("") || '<tr><td colspan="3" class="empty-cell">行业 IC 暂不可用或样本不足</td></tr>';
    q("#factor-annual-body").innerHTML = (analysis.annual_stability || []).map((row) =>
      "<tr><td>" + escapeHtml(row.year) + "</td><td>" + escapeHtml(row.horizon) +
      " 日</td><td>" + escapeHtml(row.period_count) + "</td><td>" +
      metric(row.direction_aligned_rank_ic_mean) + "</td><td>" +
      percent(row.positive_ratio) + "</td><td>" + metric(row.hac_t_value) + "</td></tr>"
    ).join("") || '<tr><td colspan="6" class="empty-cell">年度稳定性数据不可用</td></tr>';
    q("#factor-cost-stress-body").innerHTML = (analysis.execution_estimate?.cost_stress || []).map((row) =>
      "<tr><td>" + percent(row.one_side_cost_rate) + "</td><td>" +
      metric(row.estimated_cost) + "</td><td>" + metric(row.net_return_estimate) + "</td></tr>"
    ).join("") || '<tr><td colspan="3" class="empty-cell">成本压力数据不可用</td></tr>';
    const top = (analysis.latest_stocks?.top || []).map((row) => Object.assign({}, row, { side: "Top" }));
    const bottom = (analysis.latest_stocks?.bottom || []).map((row) => Object.assign({}, row, { side: "Bottom" }));
    q("#factor-stock-body").innerHTML = top.concat(bottom).map((row) =>
      "<tr><td>" + row.side + "</td><td>" + escapeHtml(row.symbol) +
      "</td><td>" + escapeHtml(row.trade_date) + "</td><td>" +
      metric(row.factor_value, 6) + "</td><td>" + metric(row.processed_value) +
      "</td><td>" + escapeHtml(row.industry || "—") + "</td><td>" +
      escapeHtml(row.group_no || "—") + "</td></tr>"
    ).join("") || '<tr><td colspan="7" class="empty-cell">最新截面没有可展示记录</td></tr>';
    q("#factor-report-state").textContent = reportId;
    q("#factor-report-output").textContent = JSON.stringify(report, null, 2);
    activateView("report");
    renderReportNavigation(reportId, payload);
    window.AppVTable?.enhanceAll(document);
    return report;
  }

  async function loadComparison() {
    if (!state.currentReportId) throw new Error("请先打开基准报告");
    const reportIds = String(q("#factor-compare-report-ids")?.value || "").trim();
    if (!reportIds) throw new Error("请输入至少一份对比报告 ID");
    const payload = await requestJson("/api/factor-research/reports/" +
      encodeURIComponent(state.currentReportId) + "/compare?" +
      buildQuery({ report_ids: reportIds }));
    const compatible = (payload.items || []).map((row) => Object.assign({}, row, { compatible: true }));
    const incompatible = (payload.incompatible || []).map((row) => Object.assign({}, row, { compatible: false }));
    q("#factor-compare-body").innerHTML = compatible.concat(incompatible).map((row) =>
      "<tr><td>" + escapeHtml(row.report_id) + "</td><td>" +
      escapeHtml(row.pool_code || row.pool_type) + "</td><td>" +
      metric(row.rank_ic_mean) + "</td><td>" + metric(row.icir) +
      "</td><td>" + percent(row.factor_coverage) + "</td><td>" +
      metric(row.final_nav) + "</td><td>" +
      (row.compatible ? "可比" : "不可比：" + escapeHtml((row.mismatches || []).join(", "))) +
      "</td></tr>"
    ).join("") || '<tr><td colspan="7" class="empty-cell">没有找到可用报告</td></tr>';
    const output = q("#factor-compare-output");
    output.hidden = false;
    output.textContent = JSON.stringify(payload, null, 2);
    window.AppVTable?.enhanceAll(document);
  }

  async function revealOutOfSample() {
    if (!state.currentReportId) throw new Error("请先打开受控研究报告");
    const reason = String(q("#factor-oos-reason")?.value || "").trim();
    const actor = String(q("#factor-oos-actor")?.value || "").trim();
    if (!reason) throw new Error("请填写样本外解封原因");
    await requestJson("/api/factor-research/reports/" +
      encodeURIComponent(state.currentReportId) + "/reveal-out-of-sample", {
      method: "POST", body: JSON.stringify({ reason: reason, actor: actor }),
    });
    await loadReport(state.currentReportId);
    setFeedback("样本外证据已解封并记录审计；后续调参应创建新研究编号", "success");
  }

  function parseNumberList(value, parser) {
    return String(value || "").split(",").map((item) => item.trim()).filter(Boolean).map(parser)
      .filter((item) => Number.isFinite(item));
  }

  function optimizationPayload() {
    const form = q("#factor-optimization-form");
    const data = Object.fromEntries(new FormData(form).entries());
    if (!data.artifact_id) throw new Error("请先从制品目录选择精确 artifact_id");
    return {
      artifact_id: data.artifact_id,
      value_field: "aligned_value",
      forward_horizons: parseNumberList(data.forward_horizons, Number),
      group_counts: parseNumberList(data.group_counts, Number),
      one_side_rates: parseNumberList(data.one_side_rates, Number),
      min_cross_section_size: Number(data.min_cross_section_size || 5),
    };
  }

  function renderArtifactDetail(artifact) {
    const target = q("#factor-artifact-detail");
    if (!target) return;
    target.innerHTML = artifact
      ? "<div><strong>" + escapeHtml(artifact.artifact_id) + "</strong><span>" +
        escapeHtml(artifact.status) + " · " + escapeHtml(artifact.factor_id) + "</span></div>" +
        "<p>固定制品：" + escapeHtml(artifact.content_hash || "-") + "</p>" +
        "<small>来源任务 " + escapeHtml(artifact.source_task_id || "-") +
        "；数据版本 " + escapeHtml(artifact.data_version_id || "-") +
        "；审核 " + escapeHtml(artifact.governance?.review_status || "pending") +
        "；登记 " + escapeHtml(artifact.governance?.registration_status || "unregistered") +
        "；字段 aligned_value</small>"
      : '<div class="empty-cell">请选择制品；系统不会自动回退到最新版本</div>';
  }

  async function loadArtifactGovernance(artifactId) {
    const payload = await requestJson("/api/factor-research/artifacts/" +
      encodeURIComponent(artifactId) + "/governance");
    q("#factor-governance-output").textContent = JSON.stringify(payload.governance || payload, null, 2);
    return payload;
  }

  async function loadArtifactMonitoring(artifactId) {
    const payload = await requestJson("/api/factor-research/artifacts/" +
      encodeURIComponent(artifactId) + "/monitoring");
    q("#factor-monitoring-output").textContent = JSON.stringify(payload.items || [], null, 2);
    return payload;
  }

  function selectArtifact(artifactId) {
    const artifact = state.artifacts.find((item) => item.artifact_id === artifactId);
    if (!artifact) throw new Error("未找到指定 artifact_id");
    state.currentArtifactId = artifactId;
    state.currentDeclaration = null;
    q('#factor-optimization-form input[name="artifact_id"]').value = artifactId;
    const registered = artifact.governance?.review_status === "approved" &&
      artifact.governance?.registration_status === "registered" && artifact.status === "ready";
    q("#factor-artifact-export").disabled = !registered;
    q("#factor-artifact-monitor").disabled = artifact.governance?.review_status !== "approved" ||
      !["registered", "suspended"].includes(artifact.governance?.registration_status);
    q("#factor-artifact-import").disabled = true;
    renderArtifactDetail(artifact);
    loadArtifactGovernance(artifactId).catch((error) => setFeedback(error.message, "error"));
    loadArtifactMonitoring(artifactId).catch((error) => setFeedback(error.message, "error"));
    const url = new URL(window.location.href);
    url.searchParams.set("artifact_id", artifactId);
    window.history.replaceState({}, "", url);
  }

  async function reviewSelectedArtifact(decision) {
    if (!state.currentArtifactId) throw new Error("请先选择研究制品");
    const note = String(q("#factor-review-note")?.value || "").trim();
    const reviewer = String(q("#factor-reviewer")?.value || "").trim();
    if (!note) throw new Error("请填写审核依据");
    await requestJson("/api/factor-research/artifacts/" +
      encodeURIComponent(state.currentArtifactId) + "/review", {
      method: "POST", body: JSON.stringify({ decision: decision, note: note, reviewer: reviewer }),
    });
    await loadArtifacts();
    selectArtifact(state.currentArtifactId);
    setFeedback(decision === "approved" ? "制品审核通过，下一步可登记" : "制品已审核拒绝", "success");
  }

  async function registerSelectedArtifact() {
    if (!state.currentArtifactId) throw new Error("请先选择研究制品");
    await requestJson("/api/factor-research/artifacts/" +
      encodeURIComponent(state.currentArtifactId) + "/register", { method: "POST" });
    await loadArtifacts();
    selectArtifact(state.currentArtifactId);
    setFeedback("制品已登记，可生成策略声明", "success");
  }

  async function suspendSelectedArtifact() {
    if (!state.currentArtifactId) throw new Error("请先选择研究制品");
    const note = String(q("#factor-review-note")?.value || "").trim();
    if (!note) throw new Error("请填写暂停新增使用的原因");
    await requestJson("/api/factor-research/artifacts/" +
      encodeURIComponent(state.currentArtifactId) + "/suspend", {
      method: "POST", body: JSON.stringify({ note: note }),
    });
    await loadArtifacts();
    selectArtifact(state.currentArtifactId);
    setFeedback("制品已暂停新增使用，历史记录保留", "success");
  }

  async function monitorSelectedArtifact() {
    if (!state.currentArtifactId) throw new Error("请先选择已登记制品");
    const result = await requestJson("/api/factor-research/artifacts/" +
      encodeURIComponent(state.currentArtifactId) + "/monitor", {
      method: "POST", body: JSON.stringify({ lookback_periods: 22 }),
    });
    await loadArtifactMonitoring(state.currentArtifactId);
    setFeedback("监控结论：" + result.status, result.status === "healthy" ? "success" : "error");
  }

  function renderArtifacts(payload) {
    state.artifacts = payload.items || [];
    renderSummaryGrid(q("#factor-artifact-summary"), [
      { label: "制品数量", value: state.artifacts.length },
      { label: "绑定策略", value: "exact artifact_id" },
      { label: "优化字段", value: "aligned_value" },
      { label: "启动策略", value: "explicit_start" },
    ]);
    q("#factor-artifact-body").innerHTML = state.artifacts.map((artifact) =>
      "<tr><td><code>" + escapeHtml(artifact.artifact_id) + "</code></td><td>" +
      escapeHtml(artifact.factor_id) + "</td><td>" + escapeHtml(artifact.factor_version) +
      "</td><td>" + escapeHtml(artifact.start_date) + " 至 " + escapeHtml(artifact.end_date) +
      "</td><td>" + escapeHtml(artifact.row_count) + "</td><td>" +
      escapeHtml(artifact.data_version_id) + "</td><td>" + escapeHtml(artifact.status) +
      '</td><td><button type="button" data-factor-artifact-id="' +
      escapeHtml(artifact.artifact_id) + '">选择</button></td></tr>'
    ).join("") || '<tr><td colspan="8" class="empty-cell">暂无可用因子制品</td></tr>';
    const requested = new URLSearchParams(window.location.search).get("artifact_id");
    if (requested && state.artifacts.some((item) => item.artifact_id === requested)) selectArtifact(requested);
    window.AppVTable?.enhanceAll(document);
  }

  async function loadArtifacts() {
    const payload = await requestJson("/api/factor-research/artifacts?limit=100");
    renderArtifacts(payload);
    return payload;
  }

  async function exportStrategyDeclaration() {
    if (!state.currentArtifactId) throw new Error("请先选择精确 artifact_id");
    const payload = await requestJson("/api/factor-research/artifacts/" +
      encodeURIComponent(state.currentArtifactId) + "/strategy-declaration");
    state.currentDeclaration = payload;
    renderSummaryGrid(q("#factor-strategy-declaration-summary"), [
      { label: "Artifact ID", value: payload.artifact_id || state.currentArtifactId },
      { label: "字段", value: payload.value_field || "aligned_value" },
      { label: "制品绑定", value: payload.artifact_binding || "immutable_exact_id" },
      { label: "任务启动", value: payload.execution_policy || "explicit_start_required" },
    ]);
    q("#factor-strategy-declaration-output").textContent = JSON.stringify(payload, null, 2);
    q("#factor-artifact-import").disabled = false;
    setFeedback("已生成精确制品策略声明，未创建或启动任务", "success");
  }

  function importFactorStrategyDraft() {
    const declaration = state.currentDeclaration;
    if (!declaration || !state.currentArtifactId) throw new Error("请先生成当前制品的策略声明");
    activatePage("backtest", false);
    activateStage76Workspace("strategy", "", false);
    startNewStrategy({
      strategy_id: declaration.declaration_id || ("factor_" + state.currentArtifactId),
      name: (declaration.factor_id || "因子") + " 精确制品策略",
      category: "因子策略",
      description: "固定 artifact_id=" + state.currentArtifactId + "；value_field=aligned_value；任务须显式启动。",
      source_code: declaration.source_code,
      parameters: declaration.parameters,
    });
    setFeedback("已导入策略草稿；未保存、未创建任务、未启动执行", "success");
  }

  function renderOptimizationTasks(payload) {
    state.optimizationTasks = payload.items || [];
    const select = q("#factor-optimization-task-select");
    const selected = state.currentOptimizationTaskId || select?.value || "";
    if (select) {
      select.innerHTML = '<option value="">请选择任务</option>' + state.optimizationTasks.map((task) =>
        '<option value="' + escapeHtml(task.task_id) + '">' + escapeHtml(task.task_id) +
        " · " + escapeHtml(task.status) + "</option>"
      ).join("");
      if (state.optimizationTasks.some((task) => task.task_id === selected)) select.value = selected;
    }
    q("#factor-optimization-task-body").innerHTML = state.optimizationTasks.map((task) => {
      const progress = task.progress || {};
      return "<tr><td>" + escapeHtml(task.task_id) + "</td><td>" +
        escapeHtml(task.artifact_id) + "</td><td>" + escapeHtml(task.value_field || "aligned_value") +
        "</td><td>" + escapeHtml(task.status) + "</td><td>" + escapeHtml(progress.phase || "-") +
        "</td><td>" + escapeHtml(progress.percent || 0) + "%</td><td>" +
        (task.report_id ? '<button type="button" data-factor-optimization-report="' +
          escapeHtml(task.report_id) + '">查看</button>' : "-") + "</td></tr>";
    }).join("") || '<tr><td colspan="7" class="empty-cell">暂无优化任务</td></tr>';
    window.AppVTable?.enhanceAll(document);
  }

  async function loadOptimizationTasks() {
    const payload = await requestJson("/api/factor-research/optimization/tasks?limit=50");
    renderOptimizationTasks(payload);
    const active = state.optimizationTasks.find((task) =>
      task.task_id === state.currentOptimizationTaskId && task.status === "running");
    if (active) scheduleOptimizationPoll();
    return payload;
  }

  async function preflightOptimization() {
    const payload = await requestJson("/api/factor-research/optimization/preflight", {
      method: "POST", body: JSON.stringify(optimizationPayload()),
    });
    q("#factor-optimization-preflight-output").textContent = JSON.stringify(payload, null, 2);
    setFeedback(payload.status === "ready" ? "优化预检通过，可创建待启动任务" : "优化预检未通过",
      payload.status === "ready" ? "success" : "error");
    return payload;
  }

  async function createOptimizationTask(event) {
    event.preventDefault();
    const preflight = await preflightOptimization();
    if (preflight.status !== "ready") return;
    const task = await requestJson("/api/factor-research/optimization/tasks", {
      method: "POST", body: JSON.stringify(optimizationPayload()),
    });
    state.currentOptimizationTaskId = task.task_id;
    await loadOptimizationTasks();
    if (q("#factor-optimization-task-select")) q("#factor-optimization-task-select").value = task.task_id;
    setFeedback("已创建待启动优化任务 " + task.task_id + "；尚未启动", "success");
  }

  async function controlOptimizationTask(action) {
    const taskId = q("#factor-optimization-task-select")?.value || state.currentOptimizationTaskId;
    if (!taskId) throw new Error("请先选择优化任务");
    const task = await requestJson("/api/factor-research/optimization/tasks/" +
      encodeURIComponent(taskId) + "/" + action, { method: "POST" });
    state.currentOptimizationTaskId = task.task_id;
    await loadOptimizationTasks();
    if (action === "start" || action === "retry") scheduleOptimizationPoll();
    setFeedback("优化任务状态：" + task.status, "success");
  }

  function scheduleOptimizationPoll() {
    if (state.optimizationPollTimer) return;
    state.optimizationPollTimer = window.setInterval(async () => {
      try {
        await loadOptimizationTasks();
        const task = state.optimizationTasks.find((item) => item.task_id === state.currentOptimizationTaskId);
        if (!task || task.status !== "running") {
          window.clearInterval(state.optimizationPollTimer);
          state.optimizationPollTimer = null;
          if (task?.report_id) await loadOptimizationReport(task.report_id);
        }
      } catch (error) {
        window.clearInterval(state.optimizationPollTimer);
        state.optimizationPollTimer = null;
        setFeedback(error.message, "error");
      }
    }, 1500);
  }

  async function loadOptimizationReport(reportId) {
    const selected = state.optimizationTasks.find((item) =>
      item.task_id === (q("#factor-optimization-task-select")?.value || state.currentOptimizationTaskId));
    const id = reportId || selected?.report_id;
    if (!id) throw new Error("当前优化任务尚无可用报告");
    const report = await requestJson("/api/factor-research/optimization/reports/" + encodeURIComponent(id));
    renderSummaryGrid(q("#factor-optimization-report-summary"), [
      { label: "报告", value: report.report_id },
      { label: "任务", value: report.task_id },
      { label: "Artifact ID", value: report.artifact_id },
      { label: "状态", value: report.status },
    ]);
    q("#factor-optimization-report-output").textContent = JSON.stringify(report, null, 2);
    return report;
  }

  async function createMultiFactorResearch(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    const payload = {
      factor_id: data.factor_id,
      name: data.name,
      method: data.method,
      artifact_ids: String(data.artifact_ids || "").split(",").map((item) => item.trim()).filter(Boolean),
      weights: parseNumberList(data.weights, Number),
      description: data.description || "",
    };
    const result = await requestJson("/api/factor-research/multi-factor/research", {
      method: "POST", body: JSON.stringify(payload),
    });
    const report = result.report || {};
    const research = report.payload || {};
    const evidence = research.analysis?.multi_factor || {};
    const acceptance = research.acceptance || {};
    renderSummaryGrid(q("#multi-factor-summary"), [
      { label: "研究任务", value: result.task?.task_id || "—" },
      { label: "组件数量", value: evidence.component_count || 0 },
      { label: "共同观测", value: evidence.common_observation_count || 0 },
      { label: "验收结论", value: acceptance.decision || "—" },
    ]);
    const correlations = Array.isArray(evidence.correlations) ? evidence.correlations : [];
    const ablations = Array.isArray(evidence.ablations) ? evidence.ablations : [];
    q("#multi-factor-correlation-body").innerHTML = correlations.map((row) => {
      const redundant = Math.abs(Number(row.rank_correlation)) >= 0.8;
      return "<tr><td>" + escapeHtml(row.left_factor_id) + "</td><td>" +
        escapeHtml(row.right_factor_id) + "</td><td>" + metric(row.rank_correlation) +
        "</td><td>" + escapeHtml(row.sample_count) + "</td><td>" +
        (redundant ? "高冗余" : "可保留") + "</td></tr>";
    }).join("") || '<tr><td colspan="5" class="empty-cell">暂无相关性证据</td></tr>';
    q("#multi-factor-ablation-body").innerHTML = ablations.map((row) =>
      "<tr><td>" + escapeHtml(row.omitted_factor_id) + "</td><td>" +
      metric(row.direction_aligned_rank_ic_mean) + "</td><td>" +
      metric(row.full_minus_ablation_rank_ic) + "</td><td>" +
      metric(row.net_return_estimate) + "</td></tr>"
    ).join("") || '<tr><td colspan="4" class="empty-cell">暂无消融证据</td></tr>';
    q("#multi-factor-output").textContent = JSON.stringify(result, null, 2);
    await Promise.all([loadTasks(), loadArtifacts()]);
    setFeedback("多因子研究完成；研究制品仍需独立审核与登记", "success");
    window.AppVTable?.enhanceAll(document);
  }
  function bind() {
    document.querySelectorAll("[data-factor-view-target]").forEach((button) =>
      button.addEventListener("click", () => activateView(button.dataset.factorViewTarget)));
    q("#factor-definition-validate")?.addEventListener("click", () =>
      validateDefinition().catch((error) => setFeedback(error.message, "error")));
    q("#factor-definition-form")?.addEventListener("submit", (event) =>
      publishDefinition(event).catch((error) => setFeedback(error.message, "error")));
    q("#factor-dashboard-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      window.loadFactors(Object.fromEntries(new FormData(event.currentTarget).entries()))
        .catch((error) => setFeedback(error.message, "error"));
    });
    q("#factor-dashboard-refresh")?.addEventListener("click", () =>
      window.loadFactors(Object.fromEntries(new FormData(q("#factor-dashboard-form")).entries()))
        .catch((error) => setFeedback(error.message, "error")));
    q("#factor-profile-close")?.addEventListener("click", () => q("#factor-profile-dialog")?.close());
    document.querySelectorAll("[data-factor-profile-tab]").forEach((button) =>
      button.addEventListener("click", () => activateFactorProfileTab(button.dataset.factorProfileTab)));
    q("#factor-profile-evidence-refresh")?.addEventListener("click", () =>
      loadR3Studies().catch((error) => setFeedback(error.message, "error")));
    q("#factor-profile-create-version")?.addEventListener("click", createVersionFromProfile);
    q("#factor-profile-start-research")?.addEventListener("click", () => {
      if (state.currentProfileFactorId) startResearchForFactor(state.currentProfileFactorId);
    });
    q("#factor-report-back")?.addEventListener("click", (event) => {
      const returnView = event.currentTarget.dataset.factorReturnView || state.reportReturnView || "tasks";
      activateView(returnView === "report" ? "tasks" : returnView);
    });
    q("#factor-profile-dialog")?.addEventListener("click", (event) => {
      const reportButton = event.target.closest("[data-factor-open-report]");
      if (reportButton) {
        q("#factor-profile-dialog")?.close();
        loadReport(reportButton.dataset.factorOpenReport)
          .catch((error) => setFeedback(error.message, "error"));
      }
    });
    q("#factor-definition-new")?.addEventListener("click", resetDefinitionForm);
    q('#factor-research-form select[name="factor_id"]')?.addEventListener("change",
      (event) => renderDefinition(event.currentTarget.value));
    q('#factor-research-form select[name="pool_type"]')?.addEventListener("change", (event) => {
      document.querySelector("[data-factor-index-field]").hidden = event.currentTarget.value !== "index";
    });
    q('#factor-research-form select[name="research_mode"]')?.addEventListener("change", (event) => {
      const governed = event.currentTarget.value === "governed";
      const limit = q('#factor-research-form input[name="symbol_limit"]');
      const symbols = q('#factor-research-form input[name="symbols"]');
      if (governed && limit) limit.value = "0";
      if (governed && symbols) symbols.value = "";
      if (limit) limit.disabled = governed;
      if (symbols) symbols.disabled = governed;
      setFeedback(governed
        ? "受控研究使用完整点时股票池，并冻结训练、验证和样本外区间"
        : "探索研究可抽样试算，但不能进入因子准入", "success");
    });
    q("#factor-preflight")?.addEventListener("click", () =>
      runPreflight().catch((error) => setFeedback(error.message, "error")));
    q("#factor-research-form")?.addEventListener("submit", (event) =>
      createTask(event).catch((error) => setFeedback(error.message, "error")));
    q("#factor-task-refresh")?.addEventListener("click", () =>
      loadTasks().catch((error) => setFeedback(error.message, "error")));
    q("#factor-task-select")?.addEventListener("change", (event) => {
      state.currentTaskId = event.currentTarget.value;
      renderCurrentTask();
    });
    q("#factor-task-start")?.addEventListener("click", () =>
      controlTask("start").catch((error) => setFeedback(error.message, "error")));
    q("#factor-task-stop")?.addEventListener("click", () =>
      controlTask("stop").catch((error) => setFeedback(error.message, "error")));
    q("#factor-task-retry")?.addEventListener("click", () =>
      controlTask("retry").catch((error) => setFeedback(error.message, "error")));
    q("#factor-task-open-report")?.addEventListener("click", () => {
      const task = state.tasks.find((item) =>
        item.task_id === (q("#factor-task-select")?.value || state.currentTaskId));
      loadReport(task?.report_id).catch((error) => setFeedback(error.message, "error"));
    });
    q("#factor-compare-run")?.addEventListener("click", () =>
      loadComparison().catch((error) => setFeedback(error.message, "error")));
    q("#factor-oos-reveal")?.addEventListener("click", () =>
      revealOutOfSample().catch((error) => setFeedback(error.message, "error")));
    q("#factor-artifact-refresh")?.addEventListener("click", () =>
      loadArtifacts().catch((error) => setFeedback(error.message, "error")));
    q("#factor-artifact-body")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-factor-artifact-id]");
      if (button) {
        try { selectArtifact(button.dataset.factorArtifactId); }
        catch (error) { setFeedback(error.message, "error"); }
      }
    });
    q("#factor-artifact-export")?.addEventListener("click", () =>
      exportStrategyDeclaration().catch((error) => setFeedback(error.message, "error")));
    q("#factor-artifact-approve")?.addEventListener("click", () =>
      reviewSelectedArtifact("approved").catch((error) => setFeedback(error.message, "error")));
    q("#factor-artifact-reject")?.addEventListener("click", () =>
      reviewSelectedArtifact("rejected").catch((error) => setFeedback(error.message, "error")));
    q("#factor-artifact-register")?.addEventListener("click", () =>
      registerSelectedArtifact().catch((error) => setFeedback(error.message, "error")));
    q("#factor-artifact-suspend")?.addEventListener("click", () =>
      suspendSelectedArtifact().catch((error) => setFeedback(error.message, "error")));
    q("#factor-artifact-monitor")?.addEventListener("click", () =>
      monitorSelectedArtifact().catch((error) => setFeedback(error.message, "error")));
    q("#factor-artifact-import")?.addEventListener("click", () => {
      try { importFactorStrategyDraft(); }
      catch (error) { setFeedback(error.message, "error"); }
    });
    q("#factor-optimization-preflight")?.addEventListener("click", () =>
      preflightOptimization().catch((error) => setFeedback(error.message, "error")));
    q("#factor-optimization-form")?.addEventListener("submit", (event) =>
      createOptimizationTask(event).catch((error) => setFeedback(error.message, "error")));
    q("#factor-optimization-refresh")?.addEventListener("click", () =>
      loadOptimizationTasks().catch((error) => setFeedback(error.message, "error")));
    q("#factor-optimization-task-select")?.addEventListener("change", (event) => {
      state.currentOptimizationTaskId = event.currentTarget.value;
    });
    q("#factor-optimization-start")?.addEventListener("click", () =>
      controlOptimizationTask("start").catch((error) => setFeedback(error.message, "error")));
    q("#factor-optimization-retry")?.addEventListener("click", () =>
      controlOptimizationTask("retry").catch((error) => setFeedback(error.message, "error")));
    q("#factor-optimization-open-report")?.addEventListener("click", () =>
      loadOptimizationReport().catch((error) => setFeedback(error.message, "error")));
    q("#multi-factor-form")?.addEventListener("submit", (event) =>
      createMultiFactorResearch(event).catch((error) => setFeedback(error.message, "error")));
    q("#factor-optimization-task-body")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-factor-optimization-report]");
      if (button) loadOptimizationReport(button.dataset.factorOptimizationReport)
        .catch((error) => setFeedback(error.message, "error"));
    });
    q("#factor-dashboard-body")?.addEventListener("click", (event) => {
      const definitionButton = event.target.closest("[data-factor-open-definition]");
      const profileButton = event.target.closest("[data-factor-open-profile]");
      const reportButton = event.target.closest("[data-factor-open-report]");
      if (profileButton) {
        openFactorProfile(profileButton.dataset.factorOpenProfile)
          .catch((error) => setFeedback(error.message, "error"));
      }
      if (definitionButton) {
        startResearchForFactor(definitionButton.dataset.factorOpenDefinition);
      }
      if (reportButton) loadReport(reportButton.dataset.factorOpenReport)
        .catch((error) => setFeedback(error.message, "error"));
    });
    q("#factor-task-body")?.addEventListener("click", (event) => {
      const reportButton = event.target.closest("[data-factor-open-report]");
      if (reportButton) loadReport(reportButton.dataset.factorOpenReport)
        .catch((error) => setFeedback(error.message, "error"));
    });
    const initialView = new URLSearchParams(window.location.search).get("factor_view") || "dashboard";
    if (q('[data-factor-view="' + initialView + '"]')) activateView(initialView, false);
  }

  bind();
})();
