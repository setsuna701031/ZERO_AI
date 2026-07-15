"use strict";

const state = {
  overview: null, health: null, approvals: null, status: null,
  actionToken: null, action: null, timer: null, controller: null,
  failures: 0, refreshPromise: null, refreshQueued: false, polling: false,
  lastOverviewFingerprint: null, lastHealthFingerprint: null,
  lastGoalsFingerprint: null, lastPendingApprovalsFingerprint: null, lastStatusFingerprint: null,
  currentSelectedGoalId: null, currentFilter: "all"
};
const byId = (id) => document.getElementById(id);
const node = (tag, className, value) => { const el = document.createElement(tag); if (className) el.className = className; if (value !== undefined) el.textContent = String(value); return el; };
const append = (parent, ...children) => { children.filter(Boolean).forEach((child) => parent.appendChild(child)); return parent; };
const fmt = (value) => value === null || value === undefined || value === "" ? "—" : String(value).replaceAll("_", " ");
const short = (value, length = 12) => value ? String(value).slice(0, length) : "—";
const projectionFingerprint = (value) => value && (value.projection_fingerprint || value.snapshot_fingerprint || value.status_fingerprint);
const displayFingerprint = (value) => JSON.stringify(value);

async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", credentials: "same-origin", ...options });
  const data = await response.json().catch(() => ({ error_code: "invalid_server_response" }));
  if (!response.ok) throw new Error(data.message || data.error_code || "Dashboard request failed");
  return data;
}

function scheduleNext() {
  clearTimeout(state.timer); state.timer = null;
  if (!state.polling || document.hidden) return;
  const delay = Math.min(60000, 5000 * (2 ** Math.min(state.failures, 3)));
  state.timer = setTimeout(() => { state.timer = null; refreshOnce(); }, delay);
}

function refreshOnce() {
  if (state.refreshPromise) { state.refreshQueued = true; return state.refreshPromise.then(() => state.refreshPromise || true); }
  if (document.hidden) return Promise.resolve(false);
  clearTimeout(state.timer); state.timer = null;
  const controller = new AbortController(); state.controller = controller;
  byId("refreshButton").disabled = true;
  state.refreshPromise = Promise.all([
    api("/api/v1/overview", { signal: controller.signal }),
    api("/api/v1/health", { signal: controller.signal }),
    api("/api/v1/pending-approvals", { signal: controller.signal }),
    api("/api/v1/dashboard-status", { signal: controller.signal })
  ]).then(([overview, health, approvals, status]) => {
    state.failures = 0;
    renderCycle({ overview, health, approvals, status });
    return true;
  }).catch((error) => {
    if (error.name !== "AbortError") { state.failures += 1; showToast(error.message); }
    return false;
  }).finally(() => {
    if (state.controller === controller) state.controller = null;
    state.refreshPromise = null; byId("refreshButton").disabled = false;
    if (state.refreshQueued && state.polling && !document.hidden) { state.refreshQueued = false; refreshOnce(); } else { state.refreshQueued = false; scheduleNext(); }
  });
  return state.refreshPromise;
}

function startPolling(refreshImmediately = true) {
  if (state.polling) {
    if (refreshImmediately && !state.refreshPromise && !state.timer) return refreshOnce();
    return state.refreshPromise || Promise.resolve(false);
  }
  state.polling = true;
  return refreshImmediately ? refreshOnce() : (scheduleNext(), Promise.resolve(false));
}

function stopPolling() {
  state.polling = false; state.refreshQueued = false; clearTimeout(state.timer); state.timer = null;
  if (state.controller) state.controller.abort();
}

function renderCycle(next) {
  const overviewFingerprint = displayFingerprint([
    next.overview.snapshot_fingerprint, next.overview.active_goal_count, next.overview.total_goal_count,
    next.overview.completed_goal_count, next.overview.waiting_approval_goal_count,
    next.overview.blocked_goal_count, next.overview.failed_goal_count, next.overview.active_mission_count,
    next.overview.runtime_mission_budget, next.overview.remaining_mission_capacity,
    next.overview.daemon_status, next.overview.daemon_cycle_count
  ]);
  const goalsFingerprint = displayFingerprint(next.overview.goal_summaries || []);
  const healthFingerprint = displayFingerprint([next.health.critical, next.health.degraded, next.health.checks, next.health.warnings, next.health.issues, next.health.recommended_operator_actions]);
  const approvalsFingerprint = displayFingerprint(next.approvals.pending_approvals || []);
  const statusFingerprint = `${next.status.read_only_mode}:${next.status.write_actions_enabled}`;
  state.overview = next.overview; state.health = next.health; state.approvals = next.approvals; state.status = next.status;
  if (statusFingerprint !== state.lastStatusFingerprint) renderStatus(next.status);
  if (overviewFingerprint !== state.lastOverviewFingerprint) renderOverview(next.overview);
  if (goalsFingerprint !== state.lastGoalsFingerprint) renderGoals();
  if (healthFingerprint !== state.lastHealthFingerprint) renderHealth(next.health);
  if (approvalsFingerprint !== state.lastPendingApprovalsFingerprint) renderApprovals(next.approvals);
  state.lastStatusFingerprint = statusFingerprint;
  state.lastOverviewFingerprint = overviewFingerprint;
  state.lastGoalsFingerprint = goalsFingerprint;
  state.lastHealthFingerprint = healthFingerprint;
  state.lastPendingApprovalsFingerprint = approvalsFingerprint;
  byId("lastUpdated").textContent = `Persisted snapshot ${short(next.overview.snapshot_identity, 34)} · refreshed ${new Date().toLocaleTimeString()}`;
}

function renderStatus(status) {
  const badge = byId("modeBadge"); badge.textContent = status.read_only_mode ? "Read only" : "Actions enabled";
  badge.classList.toggle("enabled", !status.read_only_mode);
}

function renderOverview(value) {
  const badge = byId("snapshotBadge"); badge.textContent = "snapshot " + short(value.snapshot_fingerprint); badge.title = value.snapshot_fingerprint;
  renderMetrics(value);
}

function renderMetrics(value) {
  const metrics = [
    ["active", "Active goals", value.active_goal_count, `${value.total_goal_count} total`],
    ["completed", "Completed", value.completed_goal_count, "persisted"],
    ["approval", "Waiting approval", value.waiting_approval_goal_count, "operator queue"],
    ["blocked", "Blocked / failed", `${value.blocked_goal_count} / ${value.failed_goal_count}`, "requires review"],
    ["missions", "Active Missions", `${value.active_mission_count} / ${value.runtime_mission_budget}`, `${value.remaining_mission_capacity} capacity`],
    ["daemon", "Daemon", fmt(value.daemon_status), `${value.daemon_cycle_count} cycles`]
  ];
  const root = byId("metricGrid");
  metrics.forEach(([key, label, amount, note]) => {
    let card = root.querySelector(`[data-metric="${key}"]`);
    if (!card) { card = append(node("article", "metric"), node("span"), node("strong"), node("em")); card.dataset.metric = key; root.appendChild(card); }
    card.children[0].textContent = label; card.children[1].textContent = amount; card.children[2].textContent = note;
  });
}

function filteredGoals() {
  const terminal = ["completed", "cancelled", "stopped", "blocked", "failed", "paused"];
  return (state.overview.goal_summaries || []).filter((goal) => state.currentFilter === "all" || (state.currentFilter === "active" ? !terminal.includes(goal.status) : state.currentFilter === "stalled" ? goal.stalled : goal.status === state.currentFilter));
}

function renderGoals() {
  if (!state.overview || !state.status) return;
  const root = byId("goalList"); const scrollTop = root.scrollTop;
  const focusedGoal = document.activeElement && document.activeElement.closest ? document.activeElement.closest("[data-goal-id]")?.dataset.goalId : null;
  const goals = filteredGoals(); const wanted = new Set(goals.map((goal) => goal.goal_id));
  root.querySelectorAll("[data-goal-id]").forEach((card) => { if (!wanted.has(card.dataset.goalId)) card.remove(); });
  root.querySelector("[data-empty]")?.remove();
  if (!goals.length) { const empty = node("div", "empty", "No goals match this operational view."); empty.dataset.empty = "goals"; root.appendChild(empty); }
  goals.forEach((goal) => {
    let card = root.querySelector(`[data-goal-id="${CSS.escape(goal.goal_id)}"]`);
    if (!card) { card = goalCard(goal); root.appendChild(card); }
    updateGoalCard(card, goal); root.appendChild(card);
  });
  root.scrollTop = scrollTop;
  if (focusedGoal) root.querySelector(`[data-goal-id="${CSS.escape(focusedGoal)}"]`)?.focus({ preventScroll: true });
}

function goalCard(goal) {
  const card = node("article", "goal-card"); card.tabIndex = 0; card.dataset.goalId = goal.goal_id;
  const title = node("h3"); title.dataset.role = "title";
  const status = tag(goal.status); status.dataset.role = "status";
  const identity = node("span"); identity.dataset.role = "identity";
  const progressFill = node("div", "progress-fill"); progressFill.dataset.role = "progress";
  const foot = node("span"); foot.dataset.role = "foot";
  const actions = node("div", "goal-actions"); actions.dataset.role = "actions";
  append(card, title, append(node("div", "goal-meta"), status, identity), append(node("div", "progress-track"), progressFill), append(node("div", "goal-foot"), foot, actions));
  card.addEventListener("keydown", (event) => { if (event.key === "Enter" && event.target === card) showGoal(card.dataset.goalId); }); return card;
}

function updateGoalCard(card, goal) {
  card.querySelector('[data-role="title"]').textContent = goal.title || goal.goal_id;
  const status = card.querySelector('[data-role="status"]'); status.textContent = fmt(goal.status); status.dataset.state = goal.status || "unknown";
  card.querySelector('[data-role="identity"]').textContent = `ID ${short(goal.goal_id)}`;
  card.querySelector('[data-role="progress"]').style.width = `${Math.max(0, Math.min(100, Number(goal.progress_percentage) || 0))}%`;
  const current = (goal.current_milestone_ids || [])[0] || (goal.ready_milestone_ids || [])[0] || "No current milestone";
  card.querySelector('[data-role="foot"]').textContent = `${fmt(current)} · ${goal.progress_percentage || 0}%`;
  const actions = card.querySelector('[data-role="actions"]'); const actionKey = `${state.status.read_only_mode}:${goal.status}`;
  if (actions.dataset.key !== actionKey) {
    actions.replaceChildren(button("Inspect", "mini-button", () => showGoal(goal.goal_id)));
    if (!state.status.read_only_mode) { const next = goal.status === "paused" ? "resume" : ["completed", "cancelled", "stopped", "blocked", "failed"].includes(goal.status) ? null : "pause"; if (next) actions.appendChild(button(next === "pause" ? "Pause" : "Resume", "mini-button", () => openGoalAction(next, goal))); }
    actions.dataset.key = actionKey;
  }
}

function tag(status) { const el = node("span", "status-chip", fmt(status)); el.dataset.state = status || "unknown"; return el; }
function button(label, className, handler) { const el = node("button", className, label); el.type = "button"; el.addEventListener("click", (event) => { event.stopPropagation(); handler(); }); return el; }

function renderApprovals(value) {
  const root = byId("approvalList"); const approvals = value.pending_approvals || []; const wanted = new Set(approvals.map((item) => item.approval_or_proposal_id));
  byId("approvalCount").textContent = approvals.length;
  root.querySelectorAll("[data-approval-id]").forEach((card) => { if (!wanted.has(card.dataset.approvalId)) card.remove(); }); root.querySelector("[data-empty]")?.remove();
  if (!approvals.length) { const empty = node("div", "empty", "No blocked approval gates."); empty.dataset.empty = "approvals"; root.appendChild(empty); }
  approvals.forEach((item) => {
    let card = root.querySelector(`[data-approval-id="${CSS.escape(item.approval_or_proposal_id)}"]`);
    if (!card) { card = node("article", "approval-card"); card.dataset.approvalId = item.approval_or_proposal_id; root.appendChild(card); }
    const scopes = (item.requested_scope || []).join(", ") || "No scope supplied"; card.replaceChildren(); const actions = node("div", "action-row"); actions.appendChild(button("Inspect goal", "mini-button", () => showGoal(item.goal_id)));
    if (!state.status.read_only_mode && item.current_status !== "expired") { actions.appendChild(button("Approve", "mini-button", () => openApprovalAction("approve", item))); actions.appendChild(button("Deny", "mini-button danger", () => openApprovalAction("deny", item))); }
    append(card, node("h3", "", `Milestone ${short(item.milestone_id, 18)}`), append(node("div", "approval-meta"), node("span", "", `Goal ${short(item.goal_id)}`), tag(item.current_status)), node("p", "", scopes), node("p", "", item.blocking_reason), actions); root.appendChild(card);
  });
}

function renderHealth(value) {
  const root = byId("healthList"); const items = [];
  const healthState = value.critical ? "critical" : value.degraded ? "degraded" : "healthy"; const hero = byId("healthHero"); hero.className = `health-orb ${healthState}`; hero.querySelector("strong").textContent = healthState;
  Object.entries(value.checks || {}).forEach(([name, ok]) => items.push([`check:${name}`, `health-item ${ok ? "" : "issue"}`, `${fmt(name)} · ${ok ? "passed" : "failed"}`]));
  (value.warnings || []).forEach((item, index) => items.push([`warning:${index}`, "health-item warning", item.reason || "Runtime warning"]));
  (value.issues || []).slice(0, 5).forEach((item, index) => items.push([`issue:${index}`, "health-item issue", item.reason || item.error || "Integrity issue"]));
  (value.recommended_operator_actions || []).forEach((action, index) => items.push([`action:${index}`, "health-item warning", `Recommended · ${action}`]));
  const wanted = new Set(items.map(([key]) => key)); root.querySelectorAll("[data-health-key]").forEach((item) => { if (!wanted.has(item.dataset.healthKey)) item.remove(); });
  items.forEach(([key, className, text]) => { let item = root.querySelector(`[data-health-key="${CSS.escape(key)}"]`); if (!item) { item = append(node("div"), node("span", "check-dot"), node("span")); item.dataset.healthKey = key; root.appendChild(item); } item.className = className; item.lastChild.textContent = text; root.appendChild(item); });
}

async function showGoal(goalId) {
  state.currentSelectedGoalId = goalId;
  const dialog = byId("detailDialog"); const body = byId("detailBody"); body.replaceChildren(node("div", "empty", "Loading persisted goal projection…")); if (!dialog.open) dialog.showModal();
  try {
    const [goal, timeline] = await Promise.all([api(`/api/v1/goals/${encodeURIComponent(goalId)}`), api(`/api/v1/goals/${encodeURIComponent(goalId)}/timeline`)]);
    if (state.currentSelectedGoalId !== goalId || !dialog.open) return;
    byId("detailTitle").textContent = short(goal.goal_identity, 32); body.replaceChildren();
    body.appendChild(section("Runtime state", [["Status", fmt(goal.goal_status)], ["Progress", `${goal.goal_progress?.completion_percentage || 0}%`], ["Current milestone", fmt(goal.latest_controller_projection?.current_milestone_id)], ["Replans", `${goal.attempt_policy?.current_replan_count || 0} / ${goal.attempt_policy?.max_replans || 0}`]]));
    body.appendChild(section("References & recovery", [["Integrity", goal.reference_integrity_result?.integrity ? "verified" : "review required"], ["Recovery records", (goal.crash_recovery_history || []).length], ["Reflection", short(goal.reflection_reference, 20)], ["Experience", short(goal.experience_reference, 20)]]));
    if (!state.status.read_only_mode && !["completed", "cancelled", "stopped", "blocked", "failed"].includes(goal.goal_status)) {
      const operations = node("section", "detail-section"); operations.appendChild(node("h3", "", "Controller actions")); const row = node("div", "action-row"); const summary = { goal_id: goal.goal_identity, title: `Goal ${short(goal.goal_identity)}`, status: goal.goal_status };
      (goal.goal_status === "paused" ? ["resume", "stop", "cancel"] : ["pause", "replan", "stop", "cancel"]).forEach((action) => row.appendChild(button(fmt(action), `mini-button ${["stop", "cancel"].includes(action) ? "danger" : ""}`, () => { dialog.close(); openGoalAction(action, summary); }))); operations.appendChild(row); body.appendChild(operations);
    }
    const milestones = node("section", "detail-section"); milestones.appendChild(node("h3", "", "Milestones & reference integrity")); (goal.milestones || []).forEach((item) => milestones.appendChild(section(item.title || item.milestone_id, [["Status", fmt(item.status)], ["Dependencies", (item.dependencies || []).join(", ") || "root"], ["Reference chains", (item.reference_chains || []).length]]))); body.appendChild(milestones);
    const timelineSection = node("section", "detail-section"); timelineSection.appendChild(node("h3", "", `Timeline · ${timeline.event_count || 0} events`)); (timeline.events || []).forEach((event) => append(timelineSection, append(node("div", "timeline-event"), node("strong", "", fmt(event.event_category)), node("span", "", `${fmt(event.persisted_timestamp)} · ${fmt(event.milestone_id)}`)))); body.appendChild(timelineSection);
  } catch (error) { if (state.currentSelectedGoalId === goalId) body.replaceChildren(node("div", "empty", error.message)); }
}

function section(title, values) { const el = node("section", "detail-section"); el.appendChild(node("h3", "", title)); const grid = node("div", "detail-grid"); values.forEach(([key, value]) => append(grid, append(node("div", "kv"), node("small", "", key), node("strong", "", value)))); el.appendChild(grid); return el; }
function openGoalAction(action, goal) { openAction({ action, resource: goal.goal_id, title: `${action[0].toUpperCase()}${action.slice(1)} goal`, context: `${goal.title} · ${goal.status}`, payload: {} }); }
function openApprovalAction(action, item) { openAction({ action, resource: item.approval_or_proposal_id, title: `${action === "approve" ? "Approve" : "Deny"} execution scope`, context: `Goal ${short(item.goal_id)} · Milestone ${short(item.milestone_id)} · Entry ${short(item.entry_id)} · Mission ${short(item.mission_id)} · Session ${short(item.session_id)} · Expires ${fmt(item.expiry_timestamp)} · Scope ${(item.requested_scope || []).join(", ")}`, payload: { goal_id: item.goal_id, milestone_id: item.milestone_id, entry_id: item.entry_id, expected_scope_fingerprint: item.fingerprint } }); }
function openAction(value) { state.action = value; byId("actionTitle").textContent = value.title; byId("actionContext").textContent = value.context; byId("actionError").textContent = ""; byId("actionForm").reset(); byId("reasonLabel").hidden = !["replan", "deny"].includes(value.action); byId("actionReason").required = ["replan", "deny"].includes(value.action); byId("actionDialog").showModal(); }

async function submitAction(event) {
  event.preventDefault(); if (!state.action) return; const form = byId("actionForm"); if (!form.reportValidity()) return;
  const confirm = byId("confirmButton"); confirm.disabled = true; byId("actionError").textContent = "";
  try {
    if (!state.actionToken) { const session = await api("/api/v1/session"); if (!session.write_actions_enabled) throw new Error("Write actions are disabled."); state.actionToken = session.action_token; }
    const payload = { ...state.action.payload, operator_identity: byId("operatorIdentity").value.trim(), confirmation: byId("confirmAction").checked, idempotency_key: crypto.randomUUID(), reason: byId("actionReason").value.trim() }; if (!payload.reason) delete payload.reason;
    const base = ["approve", "deny"].includes(state.action.action) ? `/api/v1/approvals/${encodeURIComponent(state.action.resource)}/${state.action.action}` : `/api/v1/goals/${encodeURIComponent(state.action.resource)}/${state.action.action}`;
    await api(base, { method: "POST", headers: { "Content-Type": "application/json", "X-Zero-Action-Token": state.actionToken }, body: JSON.stringify(payload) }); byId("actionDialog").close(); showToast("Runtime action completed and persisted."); await refreshOnce();
  } catch (error) { if (/token|session/i.test(error.message)) state.actionToken = null; byId("actionError").textContent = error.message; } finally { confirm.disabled = false; }
}

function showToast(message) { const toast = byId("toast"); toast.textContent = message; toast.classList.add("visible"); setTimeout(() => toast.classList.remove("visible"), 2800); }
document.querySelectorAll("[data-close]").forEach((item) => item.addEventListener("click", () => byId(item.dataset.close).close()));
byId("detailDialog").addEventListener("close", () => { state.currentSelectedGoalId = null; });
byId("refreshButton").addEventListener("click", refreshOnce);
byId("goalFilter").addEventListener("change", (event) => { state.currentFilter = event.target.value; renderGoals(); });
byId("actionForm").addEventListener("submit", submitAction);
document.addEventListener("visibilitychange", () => { if (document.hidden) stopPolling(); else startPolling(true); });
window.addEventListener("pagehide", stopPolling);
Object.assign(window, { startPolling, stopPolling, refreshOnce });
startPolling(true);
