"use strict";

const fs = require("fs");
const vm = require("vm");
let nextIdentity = 1;

class Element {
  constructor(tag = "div", fragment = false) {
    this.tagName = tag.toUpperCase(); this.nodeType = fragment ? 11 : 1; this.identity = nextIdentity++;
    this.children = []; this.parentNode = null; this.dataset = {}; this.style = {}; this.className = "";
    this.textContent = ""; this.disabled = false; this.scrollTop = 0; this.open = false;
    this.classList = { add: (...names) => names.forEach((name) => this._toggle(name, true)), remove: (...names) => names.forEach((name) => this._toggle(name, false)), toggle: (name, force) => this._toggle(name, force) };
  }
  _toggle(name, force) { const names = new Set(this.className.split(/\s+/).filter(Boolean)); const enabled = force === undefined ? !names.has(name) : force; if (enabled) names.add(name); else names.delete(name); this.className = [...names].join(" "); return enabled; }
  appendChild(child) { if (child.nodeType === 11) { [...child.children].forEach((item) => this.appendChild(item)); child.children = []; return child; } if (child.parentNode) child.remove(); child.parentNode = this; this.children.push(child); return child; }
  replaceChildren(...children) { this.children.forEach((child) => { child.parentNode = null; }); this.children = []; children.forEach((child) => this.appendChild(child)); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.parentNode = null; }
  addEventListener() {}
  focus() { document.activeElement = this; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  reset() {}
  reportValidity() { return true; }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  _matches(selector) {
    if (/^[a-z]+$/i.test(selector)) return this.tagName === selector.toUpperCase();
    const match = selector.match(/^\[data-([a-z-]+)(?:="([^"]*)")?\]$/); if (!match) return false;
    const key = match[1].replace(/-([a-z])/g, (_, char) => char.toUpperCase()); return match[2] === undefined ? key in this.dataset : this.dataset[key] === match[2];
  }
  querySelectorAll(selector) { const result = []; const visit = (item) => { item.children.forEach((child) => { if (child._matches(selector)) result.push(child); visit(child); }); }; visit(this); return result; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { let item = this; while (item) { if (item._matches(selector)) return item; item = item.parentNode; } return null; }
}

const ids = {};
const make = (id, tag = "div") => (ids[id] = new Element(tag));
["modeBadge", "snapshotBadge", "lastUpdated", "metricGrid", "goalList", "approvalList", "approvalCount", "healthList", "toast", "actionContext", "actionError", "reasonLabel", "actionReason", "operatorIdentity", "confirmAction", "confirmButton", "actionTitle", "detailTitle", "detailBody"].forEach((id) => make(id));
make("refreshButton", "button"); make("goalFilter", "select").value = "all"; make("actionForm", "form"); make("detailDialog", "dialog"); make("actionDialog", "dialog");
const header = make("testHeader", "header"); const title = make("pageTitle", "h1"); header.appendChild(title);
const healthHero = make("healthHero"); healthHero.appendChild(new Element("span")); healthHero.appendChild(new Element("strong"));

global.document = { hidden: true, activeElement: null, getElementById: (id) => ids[id], createElement: (tag) => new Element(tag), createDocumentFragment: () => new Element("fragment", true), querySelectorAll: () => [], addEventListener() {} };
global.window = { addEventListener() {} };
global.CSS = { escape: (value) => String(value) };
global.fetch = () => Promise.reject(new Error("fetch must remain idle in harness"));

const source = fs.readFileSync("operator_dashboard/app.js", "utf8") + "\nwindow.__renderCycle = renderCycle;";
vm.runInThisContext(source, { filename: "operator_dashboard/app.js" });
const overview = { snapshot_fingerprint: "overview-fp", snapshot_identity: "snapshot-1", active_goal_count: 1, total_goal_count: 1, completed_goal_count: 0, waiting_approval_goal_count: 0, blocked_goal_count: 0, failed_goal_count: 0, active_mission_count: 0, runtime_mission_budget: 4, remaining_mission_capacity: 4, daemon_status: "idle", daemon_cycle_count: 0, goal_summaries: [{ goal_id: "goal-1", title: "Stable goal", status: "running", progress_percentage: 10, current_milestone_ids: ["m1"] }] };
const base = { overview, health: { critical: false, degraded: false, checks: { goal_store: true }, warnings: [], issues: [], recommended_operator_actions: [] }, approvals: { pending_approvals: [] }, status: { read_only_mode: true, write_actions_enabled: false } };
window.__renderCycle(base);
const first = { header: header.identity, title: title.identity, metric: ids.metricGrid.firstChild.identity, goal: ids.goalList.firstChild.identity, health: ids.healthList.firstChild.identity, healthText: ids.healthList.firstChild.lastChild.textContent };
for (let index = 0; index < 10; index += 1) window.__renderCycle(base);
const repeated = { header: header.identity, title: title.identity, metric: ids.metricGrid.firstChild.identity, goal: ids.goalList.firstChild.identity, health: ids.healthList.firstChild.identity, healthText: ids.healthList.firstChild.lastChild.textContent };
window.__renderCycle({ ...base, health: { ...base.health, checks: { goal_store: false } } });
const healthChanged = { header: header.identity, title: title.identity, metric: ids.metricGrid.firstChild.identity, goal: ids.goalList.firstChild.identity, health: ids.healthList.firstChild.identity, healthText: ids.healthList.firstChild.lastChild.textContent };
if (JSON.stringify(first) !== JSON.stringify(repeated)) throw new Error("unchanged polling recreated dashboard DOM");
for (const key of ["header", "title", "metric", "goal", "health"]) if (first[key] !== healthChanged[key]) throw new Error(`${key} identity changed during health-only update`);
if (first.healthText === healthChanged.healthText) throw new Error("health-only change was not rendered");
const afterHealth = { ...base, health: { ...base.health, checks: { goal_store: false } } };
const addedGoal = { goal_id: "goal-2", title: "New goal", status: "running", progress_percentage: 0, current_milestone_ids: [] };
window.__renderCycle({ ...afterHealth, overview: { ...overview, snapshot_fingerprint: "overview-fp-2", active_goal_count: 2, total_goal_count: 2, goal_summaries: [...overview.goal_summaries, addedGoal] } });
const goalAdded = { header: header.identity, title: title.identity, metric: ids.metricGrid.firstChild.identity, existingGoal: ids.goalList.querySelector('[data-goal-id="goal-1"]').identity, newGoal: ids.goalList.querySelector('[data-goal-id="goal-2"]').identity, health: ids.healthList.firstChild.identity, approvalCount: ids.approvalList.children.length };
if (goalAdded.header !== first.header || goalAdded.title !== first.title || goalAdded.metric !== first.metric || goalAdded.existingGoal !== first.goal || goalAdded.health !== first.health || goalAdded.approvalCount !== 1) throw new Error("goal addition updated an unrelated DOM region");
const withGoal = { ...afterHealth, overview: { ...overview, snapshot_fingerprint: "overview-fp-2", active_goal_count: 2, total_goal_count: 2, goal_summaries: [...overview.goal_summaries, addedGoal] } };
const approval = { approval_or_proposal_id: "approval-1", milestone_id: "m2", goal_id: "goal-2", current_status: "pending", requested_scope: ["execute"], blocking_reason: "operator_approval_required" };
window.__renderCycle({ ...withGoal, approvals: { pending_approvals: [approval] } });
const approvalAdded = { header: header.identity, title: title.identity, metric: ids.metricGrid.firstChild.identity, existingGoal: ids.goalList.querySelector('[data-goal-id="goal-1"]').identity, newGoal: ids.goalList.querySelector('[data-goal-id="goal-2"]').identity, health: ids.healthList.firstChild.identity, approval: ids.approvalList.querySelector('[data-approval-id="approval-1"]').identity };
for (const key of ["header", "title", "metric", "existingGoal", "newGoal", "health"]) if (goalAdded[key] !== approvalAdded[key]) throw new Error(`${key} changed during approval-only update`);
process.stdout.write(JSON.stringify({ passes: true, first, repeated, healthChanged, goalAdded, approvalAdded }) + "\n");
