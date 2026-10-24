import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(resolve(root, "web/index.html"), "utf8");
const script = readFileSync(resolve(root, "web/data_center_stage_c.js"), "utf8");
const styles = readFileSync(resolve(root, "web/data_center.css"), "utf8");

const includesAll = (source, values, label) => {
  values.forEach((value) => assert.ok(source.includes(value), `${label}: missing ${value}`));
};

includesAll(html, [
  'id="dc-status-remediation-closure-steps"',
  'id="dc-status-remediation-quick-recheck"',
  'id="dc-status-remediation-open-versions"',
  'id="dc-status-issue-reconciliation-form"',
  'id="dc-status-issue-reconciliation-submit"',
  'id="dc-correction-release-card"',
  'id="dc-correction-release-steps"',
  'id="dc-correction-release-form"',
  'id="dc-correction-release-publish"',
  'name="authorization_reference"',
  'maxlength="500"',
  "物理修复",
  "快速复检",
  "独立修正版",
  "默认版本",
  "确认修复：复检并生效",
  "历史记录不支持整库回退",
], "closure HTML contract");

const m3Start = html.indexOf('id="dc-status-remediation-closure-title"');
const m3End = html.indexOf('class="dc-status-remediation-publish-boundary"', m3Start);
const m5Start = html.indexOf('id="dc-correction-release-card"');
const m5End = html.indexOf('id="dc-release-readiness"', m5Start);
assert.ok(m3Start >= 0 && m3End > m3Start, "M3 closure block missing");
assert.ok(m5Start >= 0 && m5End > m5Start, "M5 correction-release block missing");
assert.equal(/\bM[235]\b/.test(html.slice(m3Start, m3End)), false, "closure copy must use business page names");
assert.equal(/\bM[235]\b/.test(html.slice(m5Start, m5End)), false, "release copy must use business page names");
assert.equal(html.slice(m3Start, m3End).includes("<table"), false, "workflow cards are not row-column data tables");
assert.equal(html.slice(m5Start, m5End).includes("<table"), false, "release summary cards are not row-column data tables");

includesAll(script, [
  'const STATUS_REMEDIATION_CLOSURE_PATH="/api/data-center/quality/trading-status-remediation/closure"',
  'const CORRECTION_VERSION_PUBLISH_PATH="/api/data-center/versions/corrections/publish"',
  '`${STATUS_REMEDIATION_CLOSURE_PATH}/quick-recheck`',
  '`${STATUS_REMEDIATION_CLOSURE_PATH}/reconcile-issues`',
  "expected_issue_set_hash",
  "expected_base_version_id",
  "expected_base_manifest_hash",
  "expected_change_set_hash",
  "expected_quality_report_id",
  "expected_quality_report_hash",
  "authorization_reference:authorizationReference",
  "!authorizationReference",
  'completed:"物理修复完成，尚未复检"',
  'authorization_exhausted:"本次授权额度用尽，范围尚未完成"',
  "不运行完整工程回归",
  "未通过则保持当前数据",
  "loadStatusRemediationClosure({quiet:true})",
], "closure JavaScript contract");

const closureStart = script.indexOf("/* Stage 2 trading-status correction closure.");
const closureEnd = script.indexOf("/* End Stage 2 trading-status correction closure. */", closureStart);
assert.ok(closureStart >= 0 && closureEnd > closureStart, "isolated closure JavaScript block missing");
const closureCode = script.slice(closureStart, closureEnd);
assert.equal(closureCode.includes("/api/data-center/versions/publish"), false, "closure must not call sync publication");
assert.equal(closureCode.includes("/publish-overlay"), false, "closure must not call single-issue overlay publication");
assert.equal(closureCode.includes("/set-default"), false, "correction publication must not set the default version");

const sandbox = { state: { versions: null }, count: (value) => String(Number(value || 0)), esc: (value) => String(value ?? "") };
vm.runInNewContext(`${closureCode}\nglobalThis.__closureButtonState=closureButtonState;globalThis.__closureSummaryHtml=closureSummaryHtml;globalThis.__blockerLabels=statusClosureBlockerLabels;`, sandbox);
const matrix = sandbox.__closureButtonState;
assert.deepEqual(
  { ...matrix({ next_action: "quick_recheck", recheck: { status: "required" }, release: { status: "not_published" }, blockers: [] }) },
  { reconcileIssues: false, quickRecheck: true, publish: true, openVersions: true },
  "completed repair should allow one-step recheck and activation",
);
assert.equal(
  matrix({ next_action: "quick_recheck", recheck: { status: "required" }, release: { status: "not_published" }, blockers: [{ status: "blocked", check_id: "base_version_changed" }] }).quickRecheck,
  false,
  "a non-recheck blocker must disable quick recheck",
);
assert.deepEqual(
  { ...matrix({ next_action: "publish_correction", recheck: { status: "passed" }, release: { status: "ready" }, blockers: [] }) },
  { reconcileIssues: false, quickRecheck: false, publish: true, openVersions: true },
  "passed recheck should expose correction publication",
);
assert.equal(
  matrix({ next_action: "publish_correction", recheck: { status: "passed" }, release: { status: "ready" }, blockers: [{ status: "blocked", check_id: "change_set_drift" }] }).publish,
  false,
  "a blocker must disable correction publication",
);
assert.deepEqual(
  { ...matrix({ next_action: "set_default_version", recheck: { status: "passed" }, release: { status: "published" }, blockers: [] }) },
  { reconcileIssues: false, quickRecheck: false, publish: false, openVersions: true },
  "published correction permits history inspection without repeated publication",
);
assert.deepEqual(
  { ...matrix({ next_action: "resolve_blockers", recheck: { status: "blocked" }, release: { status: "not_published" }, blockers: [{ status: "blocked", check_id: "manual_evidence_required" }] }) },
  { reconcileIssues: false, quickRecheck: false, publish: false, openVersions: false },
  "blocked closure must expose no mutating action",
);
assert.equal(
  matrix({ issue_reconciliation: { status: "ready", closable_count: 61, blocking_count: 0 }, blockers: [{ status: "blocked", check_id: "release_readiness" }] }).reconcileIssues,
  true,
  "passed physical recheck should expose governed stale-issue closure",
);
const backendBlockerIds = [
  "published_base_version", "base_manifest_integrity", "base_trading_status_member",
  "admin_row_run_evidence", "published_admin_subset_integrity",
  "change_dates_within_base_coverage", "unfinished_remediation_tasks",
  "completed_remediation_task", "remediation_checkpoint_missing",
  "remediation_checkpoint_unreadable", "remediation_checkpoint_identity",
  "remediation_run_incomplete", "remediation_candidate_manifest_integrity",
  "remediation_written_key_hashes", "active_trading_status_writer",
  "base_version_drift", "base_manifest_drift", "all_symbols_auto_zero",
  "all_symbols_manual_zero", "all_symbols_candidate_zero",
  "trading_status_member_summary_consistent", "closure_evidence_stable_during_recheck",
  "quality_report_drift", "published_parent_drift",
];
backendBlockerIds.forEach((checkId) => {
  const label = sandbox.__blockerLabels[checkId];
  assert.ok(label && /[\u3400-\u9fff]/.test(label), `missing Chinese blocker label: ${checkId}`);
});
const zeroKeyBlockedSummary = sandbox.__closureSummaryHtml({
  status: "blocked",
  base_version: { data_version_id: "base-version", as_of_trade_date: "2026-08-10" },
  change_set: { key_count: 0 },
  blockers: [{ check_id: "base_manifest_integrity", status: "blocked" }],
  recheck: { status: "required", repairability_counts: {} },
  release: { status: "not_published" },
});
assert.ok(zeroKeyBlockedSummary.includes("基准版本"), "zero-key blockers must retain evidence summary");
assert.ok(!zeroKeyBlockedSummary.includes("当前没有待复检"), "zero-key blockers must not be rendered as no changes");

const cssStart = styles.indexOf(".dc-status-remediation-closure");
const cssEnd = styles.indexOf("/* Balance the quality-check editor", cssStart);
assert.ok(cssStart >= 0 && cssEnd > cssStart, "closure CSS block missing");
const closureCss = styles.slice(cssStart, cssEnd);
includesAll(closureCss, [
  "var(--q-primary)",
  "var(--q-warning)",
  "var(--q-danger)",
  "var(--q-border)",
  "var(--q-bg-card)",
  "@media(max-width:741px)",
], "Quant UI closure contract");
assert.equal(/#[0-9a-f]{3,8}\b/i.test(closureCss), false, "closure UI must not introduce private colors");

console.log("stage2 trading-status remediation closure UI smoke passed");
