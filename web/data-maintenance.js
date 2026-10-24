/* 日常维护入口：无需理解发布版本及默认指针。 */
(() => {
  "use strict";
  const form = document.getElementById("dc-maintenance-form");
  if (!form) return;
  const output = document.getElementById("dc-maintenance-feedback");
  const list = document.getElementById("dc-maintenance-list");
  const labels = {queued: "等待更新", running: "更新中", failed: "需要处理",
    interrupted: "已中断，可恢复", expired: "缓存已过期，请新建更新", completed: "已更新并生效", completed_noop: "已是最新"};
  const phases = {queued: "等待执行", references: "更新参考数据", prices: "更新行情",
    activating: "检查通过，等待生效", needs_attention: "查看原因后重试", done: "完成"};
  const esc = value => String(value ?? "").replace(/[&<>"']/g,
    c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const yesterday = new Date(new Date().toLocaleString("en-US", {timeZone: "Asia/Shanghai"}));
  if (yesterday.getHours() < 18) yesterday.setDate(yesterday.getDate() - 1);
  const target = `${yesterday.getFullYear()}-${String(yesterday.getMonth()+1).padStart(2,"0")}-${String(yesterday.getDate()).padStart(2,"0")}`;
  form.elements.target_trade_date.value = target;
  form.elements.target_trade_date.max = target;
  async function request(path, body) {
    const response = await fetch(path, body === undefined ? {} : {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "操作失败，请查看任务详情");
    return payload;
  }
  let refreshing = false;
  let rendered = '';
  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      const {items = []} = await request("/api/data-center/updates");
      const signature = JSON.stringify(items);
      if (signature === rendered) return;
      rendered = signature;
      list.querySelectorAll('table').forEach(table => window.AppVTable?.release?.(table));
      list.innerHTML = items.length ? `<table><thead><tr><th>时间</th><th>目标日期</th><th>状态</th><th>进度 / 原因</th><th>操作</th></tr></thead><tbody>${items.map(item => `<tr><td>${esc(item.created_at)}</td><td>${esc(item.result?.target_trade_date || item.request?.target_trade_date)}</td><td>${esc(labels[item.status] || item.status)}</td><td>${esc(item.result?.error || phases[item.phase] || item.phase)}</td><td>${["failed","interrupted","queued"].includes(item.status) ? `<button type="button" data-maintenance-resume="${esc(item.batch_id)}">恢复更新</button>` : "—"}</td></tr>`).join("")}</tbody></table>` : "<p>尚无更新记录</p>";
      window.AppVTable?.enhanceAll(list);
      form.querySelector("button").disabled = items.some(item => ["queued","running"].includes(item.status));
      if (items[0]?.status === 'completed') output.textContent = '数据已检查通过并生效，可直接用于研究。';
      if (items[0]?.status === 'completed_noop') output.textContent = '该截止日期的数据已是最新，无需重复更新。';
    } finally { refreshing = false; }
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    form.querySelector("button").disabled = true;
    try {
      await request("/api/data-center/updates", {target_trade_date: form.elements.target_trade_date.value});
      output.textContent = "更新已启动，可离开页面；检查通过后自动生效。";
      await refresh();
    } catch (error) { output.textContent = error.message; form.querySelector("button").disabled = false; }
  });
  list.addEventListener("click", async event => {
    const button = event.target.closest("[data-maintenance-resume]");
    if (!button) return;
    button.disabled = true;
    try { await request(`/api/data-center/updates/${encodeURIComponent(button.dataset.maintenanceResume)}/resume`, {}); await refresh(); }
    catch (error) { output.textContent = error.message; button.disabled = false; }
  });
  refresh().catch(error => { output.textContent = error.message; });
  setInterval(() => { if (!document.hidden && list.offsetParent) refresh().catch(error => { output.textContent = error.message; }); }, 3000);
})();
