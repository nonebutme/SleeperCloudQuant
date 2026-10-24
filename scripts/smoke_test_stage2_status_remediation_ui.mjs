import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(resolve(root, "web/index.html"), "utf8");
const script = readFileSync(resolve(root, "web/data_center_stage_c.js"), "utf8");
const styles = readFileSync(resolve(root, "web/data_center.css"), "utf8");

const includesAll = (source, values, label) => {
  values.forEach((value) => assert.ok(source.includes(value), `${label}: missing ${value}`));
};

includesAll(html, [
  'id="dc-status-remediation-form"',
  '<option value="all_symbols" selected>',
  'name="authorized_total_writes"',
  'max="1000000"',
  'name="commit_batch_size"',
  'max="1000"',
  'name="authorization_reference"',
  'id="dc-status-remediation-task-list"',
  'id="dc-status-remediation-refresh"',
  "运行中每 3 秒刷新",
  'id="dc-status-remediation-closure-steps"',
  'id="dc-correction-release-card"',
  "复检通过后自动生效",
], "HTML contract");

includesAll(script, [
  'body:{scope}',
  'STATUS_REMEDIATION_START_PATH',
  '`${STATUS_REMEDIATION_BASE}/tasks`',
  'api(STATUS_REMEDIATION_BASE)',
  '/tasks/${encodeURIComponent(runId)}',
  '/pause`,{method:"POST"',
  '/resume`,{method:"POST",body:{confirmation}',
  'authorized_total_writes>1000000',
  'commit_batch_size>1000',
  'authorization_consumed',
  'historicalStatusRemediationThroughput',
  '历史任务中位数',
  'rerenderStatusRemediationPreview',
  'if(task.read_only)',
  '["paused_by_user","paused_max_writes","failed"].includes(status)',
  'setTimeout(()=>loadStatusRemediationTasks({quiet:true}).catch(()=>{}),3000)',
  '“质量与修复”页的检查、异常台账和逐问题修复不受影响',
  'CORRECTION_VERSION_PUBLISH_PATH',
  'data-vtable-mode="governance"',
  'window.AppVTable?.release(table)',
  'loadStatusRemediationTasks({quiet:true})',
], "JavaScript contract");

const closureStart = script.indexOf("/* Stage 2 trading-status correction closure.");
const closureEnd = script.indexOf("/* End Stage 2 trading-status correction closure. */", closureStart);
assert.ok(closureStart >= 0 && closureEnd > closureStart, "dedicated correction closure block missing");
const closureCode = script.slice(closureStart, closureEnd);
assert.ok(closureCode.includes("STATUS_REMEDIATION_CLOSURE_PATH"), "closure endpoint must be consumed");
assert.ok(closureCode.includes("/api/data-center/versions/corrections/complete"), "one-step correction endpoint must be consumed");
assert.ok(!closureCode.includes("/api/data-center/versions/publish"), "closure must not call sync publish");
assert.ok(!closureCode.includes("/publish-overlay"), "closure must not call single-issue overlay publish");

assert.ok(
  script.includes('scope:String(data.get("scope")||"all_symbols")'),
  "all_symbols must remain the request default",
);
assert.ok(
  !script.includes('max_writes:Number(data.get("max_writes")'),
  "the background form must not collapse total authorization into the legacy per-call cap",
);
assert.ok(
  !script.includes('STATUS_REMEDIATION_APPLY_PATH'),
  "the background form must not call the legacy public apply alias",
);
assert.ok(
  script.includes('if(!payload.authorization_reference)'),
  "every administrator task must carry an explicit authorization reference",
);
assert.ok(
  !script.includes('["paused_by_user","pause_requested"].includes(status)'),
  "pause_requested is not resumable until the current transaction reaches a safe boundary",
);

const statusCssStart = styles.indexOf(".dc-status-remediation-admin");
const statusCssEnd = styles.indexOf("/* Balance the quality-check editor", statusCssStart);
assert.ok(statusCssStart >= 0 && statusCssEnd > statusCssStart, "status-remediation CSS block missing");
const statusCss = styles.slice(statusCssStart, statusCssEnd);
includesAll(statusCss, [
  "var(--q-warning)",
  "var(--q-danger)",
  "var(--q-border)",
  "var(--q-bg-card)",
  "@media(max-width:741px)",
], "quant UI contract");
assert.equal(/#[0-9a-f]{3,8}\b/i.test(statusCss), false, "status UI must not introduce private colors");

console.log("stage2 trading-status remediation UI smoke passed");
