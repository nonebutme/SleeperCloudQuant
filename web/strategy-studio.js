(() => {
  "use strict";

  const state = { datasets: [], selected: new Map() };
  const byId = (id) => document.getElementById(id);
  const splitList = (value) => String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
  const numberValue = (id) => Number(byId(id).value);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

  async function request(path, options = {}) {
    const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `请求失败（${response.status}）`);
    return payload;
  }

  function setApiStatus(text, kind = "") {
    const node = byId("api-status");
    node.textContent = text;
    node.className = `status-pill ${kind ? `is-${kind}` : ""}`;
  }

  function refreshTables() {
    window.AppVTable?.enhanceAll?.(document);
  }

  async function loadDatasets() {
    setApiStatus("正在读取数据中心");
    const params = new URLSearchParams();
    const search = byId("dataset-search").value.trim();
    const status = byId("dataset-status").value;
    if (search) params.set("search", search);
    if (status) params.set("status", status);
    try {
      const payload = await request(`/api/datasets${params.size ? `?${params}` : ""}`);
      state.datasets = payload.items || [];
      renderDatasets();
      const summary = payload.summary || {};
      byId("dataset-summary").textContent = `${summary.total ?? 0} 个产品 · 目录权威：数据中心 · 只读`;
      setApiStatus("数据中心已连接", "ok");
    } catch (error) {
      state.datasets = [];
      renderDatasets();
      byId("dataset-summary").textContent = "目录读取失败";
      setApiStatus(error.message, "error");
    }
  }

  function renderDatasets() {
    const body = byId("dataset-body");
    if (!state.datasets.length) {
      body.innerHTML = '<tr><td colspan="7" class="empty-state">没有匹配的数据集产品。</td></tr>';
      refreshTables();
      return;
    }
    body.innerHTML = state.datasets.map((item) => {
      const checked = state.selected.has(item.dataset_id) ? "checked" : "";
      const disabled = item.status !== "connected" ? "disabled" : "";
      return `<tr>
        <td><input class="dataset-choice" type="checkbox" data-dataset-id="${escapeHtml(item.dataset_id)}" ${checked} ${disabled}></td>
        <td><code>${escapeHtml(item.dataset_id)}</code></td><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.layer_id || "—")}</td>
        <td class="state-${escapeHtml(item.status)}">${escapeHtml(item.status)}</td><td>${escapeHtml(item.schema_status)}</td><td>${escapeHtml(item.producer_type)}</td>
      </tr>`;
    }).join("");
    body.querySelectorAll("[data-dataset-id]").forEach((input) => input.addEventListener("change", () => toggleDataset(input.dataset.datasetId, input.checked)));
    refreshTables();
  }

  function toggleDataset(datasetId, selected) {
    if (selected) {
      const product = state.datasets.find((item) => item.dataset_id === datasetId);
      state.selected.set(datasetId, { product, requiredFields: "", adjustment: "qfq", missingPolicy: "unavailable", minimumHistory: 252 });
    } else {
      state.selected.delete(datasetId);
    }
    renderSelectedDatasets();
  }

  function renderSelectedDatasets() {
    const host = byId("selected-datasets");
    if (!state.selected.size) {
      host.innerHTML = '<p class="empty-state">尚未选择数据集。</p>';
      return;
    }
    host.innerHTML = [...state.selected.entries()].map(([id, requirement]) => `<div class="requirement-row" data-requirement="${escapeHtml(id)}">
      <strong title="${escapeHtml(requirement.product?.name || id)}">${escapeHtml(id)}</strong>
      <label><span>必需字段</span><input data-field="requiredFields" value="${escapeHtml(requirement.requiredFields)}" placeholder="close,volume"></label>
      <label><span>复权</span><select data-field="adjustment"><option value="raw">不复权</option><option value="qfq" ${requirement.adjustment === "qfq" ? "selected" : ""}>前复权</option><option value="hfq">后复权</option><option value="none">不适用</option></select></label>
      <label><span>缺失值</span><select data-field="missingPolicy"><option value="unavailable">阻断</option><option value="drop">丢弃</option><option value="forward_fill">前值填充</option><option value="zero">填零</option></select></label>
      <label><span>最少历史期</span><input data-field="minimumHistory" type="number" min="0" value="${requirement.minimumHistory}"></label>
      <button type="button" class="secondary" data-remove="${escapeHtml(id)}">移除</button>
    </div>`).join("");
    host.querySelectorAll("[data-requirement]").forEach((row) => {
      const item = state.selected.get(row.dataset.requirement);
      row.querySelectorAll("[data-field]").forEach((input) => input.addEventListener("change", () => {
        item[input.dataset.field] = input.dataset.field === "minimumHistory" ? Number(input.value) : input.value;
      }));
    });
    host.querySelectorAll("[data-remove]").forEach((button) => button.addEventListener("click", () => {
      state.selected.delete(button.dataset.remove);
      renderSelectedDatasets();
      renderDatasets();
    }));
  }

  async function sourceHash() {
    const bytes = new TextEncoder().encode(byId("strategy-source").value);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function updateHash() {
    byId("source-hash").textContent = await sourceHash();
  }

  function datasetRequirements() {
    return [...state.selected.entries()].map(([datasetId, item]) => ({
      dataset_id: datasetId,
      required_fields: splitList(item.requiredFields),
      minimum_history: Number(item.minimumHistory || 0),
      adjustment: item.adjustment === "none" ? null : item.adjustment,
      point_in_time_required: true,
      missing_data_policy: item.missingPolicy,
      version_policy: "latest_published",
    }));
  }

  async function buildManifest() {
    return {
      strategy_id: byId("strategy-id").value.trim(), strategy_version: byId("strategy-version").value.trim(), name: byId("strategy-name").value.trim(),
      source_sha256: await sourceHash(), dataset_requirements: datasetRequirements(), factor_ids: splitList(byId("factor-ids").value),
      assets: { universe_type: byId("asset-universe").value, symbols: splitList(byId("asset-symbols").value) },
      signals: { direction: byId("signal-direction").value, ranking: byId("signal-ranking").value, frequency: byId("signal-frequency").value },
      portfolio: { weighting: byId("weighting").value, max_positions: numberValue("max-positions"), gross_exposure: numberValue("gross-exposure") },
      risk: { max_drawdown: numberValue("max-drawdown"), max_position_weight: numberValue("max-position-weight"), stop_loss: numberValue("stop-loss") },
      execution: { fill_timing: byId("fill-timing").value, commission_rate: numberValue("commission"), slippage_rate: numberValue("slippage") },
      code: { language: "python", entrypoint: "generate_targets", source: byId("strategy-source").value },
      validation: { point_in_time: byId("pit-check").checked, survivorship_bias: byId("survivorship-check").checked, out_of_sample: byId("oos-check").checked },
    };
  }

  async function saveManifest() {
    const output = byId("validation-output");
    output.className = "validation-output";
    const identity = ["strategy-id", "strategy-version", "strategy-name"].map((id) => byId(id).value.trim());
    if (identity.some((value) => !value)) {
      output.textContent = "策略 ID、版本和名称不能为空。";
      output.classList.add("is-error");
      return;
    }
    if (!state.selected.size) {
      output.textContent = "至少选择一个已连接数据集。";
      output.classList.add("is-error");
      return;
    }
    try {
      byId("save-manifest").disabled = true;
      output.textContent = "正在验证数据集并保存不可变版本…";
      const payload = await buildManifest();
      const result = await request("/api/strategy-studio/manifests", { method: "POST", body: JSON.stringify(payload) });
      const manifest = result.manifest || {};
      output.textContent = `保存成功：${manifest.strategy_id}@${manifest.strategy_version}\n验证：${manifest.validation?.status || "valid"}\nManifest SHA-256：${manifest.manifest_sha256 || "—"}`;
      output.classList.add("is-success");
      await loadManifests();
    } catch (error) {
      output.textContent = `保存失败：${error.message}`;
      output.classList.add("is-error");
    } finally {
      byId("save-manifest").disabled = false;
    }
  }

  async function loadManifests() {
    const body = byId("manifest-body");
    try {
      const payload = await request("/api/strategy-studio/manifests");
      const manifests = payload.manifests || [];
      body.innerHTML = manifests.length ? manifests.map((item) => `<tr><td><code>${escapeHtml(item.strategy_id)}</code></td><td>${escapeHtml(item.strategy_version)}</td><td>${escapeHtml(item.name)}</td><td>${item.dataset_requirements?.length || 0}</td><td>${escapeHtml(item.validation?.status || "—")}</td><td>${escapeHtml(item.created_at || "—")}</td></tr>`).join("") : '<tr><td colspan="6" class="empty-state">尚无已保存策略版本。</td></tr>';
      refreshTables();
    } catch (error) {
      body.innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  byId("section-nav").querySelectorAll("[data-target]").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll("#section-nav button").forEach((item) => item.classList.toggle("is-active", item === button));
    byId(button.dataset.target).scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  byId("theme-toggle").addEventListener("click", () => {
    document.documentElement.dataset.theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  });
  byId("dataset-refresh").addEventListener("click", loadDatasets);
  byId("dataset-search").addEventListener("search", loadDatasets);
  byId("dataset-status").addEventListener("change", loadDatasets);
  byId("strategy-source").addEventListener("input", updateHash);
  byId("save-manifest").addEventListener("click", saveManifest);

  Promise.all([loadDatasets(), loadManifests(), updateHash()]).catch((error) => setApiStatus(error.message, "error"));
})();
