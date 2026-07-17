from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.agent.runtime_goal_operations_health import build_health, stalled_goal
from core.agent.runtime_goal_operations_references import active_references, build_reference_chains
from core.agent.runtime_goal_operations_snapshot import CONTRACT, PROJECTION_VERSION, VERSION, GoalOperationsConfig, GoalOperationsGoalInspection, GoalOperationsHealth, GoalOperationsOverview, GoalOperationsPendingApprovals, GoalOperationsTimeline, finalize_projection, load_goal_sources, runtime_budget_projection, snapshot_fingerprint, snapshot_identity, source_manifest_projection
from core.agent.runtime_goal_operations_timeline import build_goal_timeline
from core.agent.runtime_long_horizon_goal import TERMINAL_GOALS
from core.runtime.runtime_operator_session import fingerprint
from core.runtime.runtime_operator_session import parse_time

STATUS_ORDER = {status: index for index, status in enumerate(("running", "ready", "partially_completed", "waiting_for_approval", "paused", "blocked", "failed", "stopped", "cancelled", "completed", "draft"))}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _base(kind: str, sources: Mapping[str, Any], query: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"contract": CONTRACT, "version": VERSION, "projection_version": PROJECTION_VERSION, "projection_kind": kind, "snapshot_identity": snapshot_identity(kind, sources, query), "snapshot_fingerprint": snapshot_fingerprint(kind, sources, query), "query": deepcopy(dict(query or {})), "source_fingerprints": deepcopy(sources["source_fingerprints"]), "source_manifest": source_manifest_projection(sources)}
def _seal(kind: str, sources: Mapping[str, Any], body: Mapping[str, Any], query: Mapping[str, Any] | None = None) -> dict[str, Any]: return finalize_projection({**_base(kind, sources, query), **deepcopy(dict(body))})
def _refs_for_all(sources: Mapping[str, Any]) -> dict[str, dict[str, Any]]: return {str(goal["goal_id"]): build_reference_chains(goal, sources.get("entries") or {}) for goal in sources.get("goals") or []}
def _public_chain(chain: Mapping[str, Any]) -> dict[str, Any]:
    clean = {key: deepcopy(value) for key, value in chain.items() if not key.endswith("_path")}
    plan = _mapping(clean.get("execution_plan_reference"))
    if plan: clean["execution_plan_reference"] = {key: plan.get(key) for key in ("plan_id", "fingerprint")}
    return clean

class GoalOperationsService:
    def __init__(self, config: GoalOperationsConfig):
        if not isinstance(config, GoalOperationsConfig): raise TypeError("goal_operations_config_required")
        self.config = config

    def _sources(self, *, permit_corrupt: bool = False) -> dict[str, Any]:
        sources = load_goal_sources(self.config)
        if sources["errors"] and not permit_corrupt: raise ValueError(";".join(str(item["error"]) for item in sources["errors"]))
        return sources

    def overview(self) -> GoalOperationsOverview:
        sources = self._sources(); refs = _refs_for_all(sources); summaries = []
        for goal in sources["goals"]:
            progress = _mapping(goal.get("progress")); reference = refs[str(goal["goal_id"])]
            stalled, _ = stalled_goal(goal, reference["chains"]); active = active_references(reference["chains"])
            recoveries = [chain for chain in reference["chains"] if chain.get("last_recovery_at")]
            summary = {"goal_id": goal["goal_id"], "title": goal.get("goal_title") or goal.get("normalized_goal"), "status": goal.get("goal_status"), "progress_percentage": progress.get("completion_percentage", 0), "current_milestone_ids": [goal.get("current_milestone_id")] if goal.get("current_milestone_id") else [], "ready_milestone_ids": deepcopy(progress.get("next_ready_milestone_ids") or []), "waiting_approval_milestone_ids": deepcopy(progress.get("waiting_approval_milestones") or []), "blocked_milestone_ids": deepcopy(progress.get("blocked_milestones") or []), "failed_milestone_ids": deepcopy(progress.get("failed_milestones") or []), "completed_milestone_count": len(progress.get("completed_milestones") or []), "total_milestone_count": progress.get("total_milestones", len(goal.get("milestone_order") or [])), **active, "last_state_transition": {"status": goal.get("goal_status"), "persisted_at": goal.get("updated_at")}, "latest_recovery_result": ({"session_id": recoveries[-1].get("session_id"), "recovery_count": recoveries[-1].get("recovery_count"), "persisted_at": recoveries[-1].get("last_recovery_at")} if recoveries else None), "latest_replan_result": deepcopy((goal.get("replan_history") or [None])[-1]), "reflection_reference": _mapping(goal.get("reflection_reference")).get("reflection_id"), "experience_reference": _mapping(goal.get("experience_reference")).get("experience_id"), "goal_fingerprint": goal.get("goal_fingerprint"), "stalled": stalled}
            summaries.append(summary)
        summaries.sort(key=lambda item: (STATUS_ORDER.get(str(item["status"]), 999), str(item["last_state_transition"]["persisted_at"]), str(item["goal_id"])))
        def count(status: str) -> int: return sum(goal.get("goal_status") == status for goal in sources["goals"])
        budget = runtime_budget_projection(sources); daemon = _mapping(sources.get("daemon"))
        body = {"total_goal_count": len(summaries), "active_goal_count": sum(goal.get("goal_status") not in TERMINAL_GOALS and goal.get("goal_status") not in {"paused", "stopped", "cancelled"} for goal in sources["goals"]), "completed_goal_count": count("completed"), "paused_goal_count": count("paused"), "stopped_goal_count": count("stopped"), "cancelled_goal_count": count("cancelled"), "blocked_goal_count": count("blocked"), "failed_goal_count": count("failed"), "waiting_approval_goal_count": sum(bool(_mapping(goal.get("progress")).get("waiting_approval_milestones")) for goal in sources["goals"]), "stalled_goal_count": sum(item["stalled"] for item in summaries), "ready_milestone_count": sum(len(item["ready_milestone_ids"]) for item in summaries), "active_mission_count": budget["active_mission_count"], "runtime_mission_budget": budget["runtime_budget"], "remaining_mission_capacity": budget["remaining_mission_capacity"], "daemon_status": daemon.get("daemon_status") or "not_initialized", "daemon_last_cycle_identity": daemon.get("last_cycle_id"), "daemon_last_cycle_result": None, "daemon_cycle_count": daemon.get("cycle_count", 0), "daemon_last_error": deepcopy(daemon.get("last_error")), "goal_summaries": summaries}
        return GoalOperationsOverview(_seal("overview", sources, body))

    def inspect(self, goal_id: str) -> GoalOperationsGoalInspection:
        sources = self._sources(); goal = next((item for item in sources["goals"] if item.get("goal_id") == str(goal_id)), None)
        if goal is None: raise ValueError("goal_not_found")
        refs = build_reference_chains(goal, sources.get("entries") or {}); by_milestone = {}
        for chain in refs["chains"]:
            clean = _public_chain(chain)
            by_milestone.setdefault(str(chain["milestone_id"]), []).append(clean)
        milestones = []
        for milestone_id in goal.get("milestone_order") or []:
            item = _mapping(_mapping(goal.get("milestones")).get(milestone_id)); milestones.append({"milestone_id": milestone_id, "status": item.get("milestone_status"), "title": item.get("title"), "dependencies": deepcopy(item.get("dependencies") or []), "dependency_projection": f"{milestone_id} <- {', '.join(item.get('dependencies') or []) or 'root'}", "mission_templates": deepcopy(item.get("mission_templates") or []), "reference_chains": by_milestone.get(milestone_id, []), "evidence_references": deepcopy(item.get("evidence_requirements") or []), "reflection_references": deepcopy(item.get("reflection_references") or []), "experience_references": deepcopy(item.get("experience_references") or []), "failure_or_block_reason": deepcopy(item.get("failure")), "milestone_fingerprint": item.get("milestone_fingerprint")})
        public_refs = {**refs, "chains": [_public_chain(chain) for chain in refs["chains"]]}
        body = {"goal_identity": goal["goal_id"], "goal_contract": goal.get("contract"), "goal_status": goal.get("goal_status"), "goal_progress": deepcopy(goal.get("progress")), "goal_scope": {"workspace": "<workspace-root>", "target": "<target-root>", "constraints": deepcopy(goal.get("constraints") or [])}, "policy_references": {"memory_context": goal.get("memory_context_reference"), "planning_feedback": goal.get("planning_feedback_reference")}, "approval_expectations": {item["milestone_id"]: bool(_mapping(_mapping(goal.get("milestones")).get(item["milestone_id"])).get("approval_expected")) for item in milestones}, "attempt_policy": {"max_replans": goal.get("max_replans"), "current_replan_count": goal.get("replan_count")}, "replan_history": deepcopy(goal.get("replan_history") or []), "crash_recovery_history": [{"session_id": chain.get("session_id"), "recovery_count": chain.get("recovery_count"), "last_recovery_at": chain.get("last_recovery_at")} for chain in refs["chains"] if chain.get("recovery_count")], "milestone_dependency_graph": [item["dependency_projection"] for item in milestones], "milestones": milestones, "reflection_reference": _mapping(goal.get("reflection_reference")).get("reflection_id"), "experience_reference": _mapping(goal.get("experience_reference")).get("experience_id"), "failure_or_block_reason": deepcopy(goal.get("failure")), "latest_controller_projection": {"current_milestone_id": goal.get("current_milestone_id"), "progress": deepcopy(goal.get("progress")), "persisted_at": goal.get("updated_at")}, "goal_fingerprint": goal.get("goal_fingerprint"), "milestone_fingerprints": {item["milestone_id"]: item["milestone_fingerprint"] for item in milestones}, "reference_integrity_result": public_refs}
        return GoalOperationsGoalInspection(_seal("goal_inspection", sources, body, {"goal_id": str(goal_id)}))

    def timeline(self, goal_id: str) -> GoalOperationsTimeline:
        sources = self._sources(); goal = next((item for item in sources["goals"] if item.get("goal_id") == str(goal_id)), None)
        if goal is None: raise ValueError("goal_not_found")
        refs = build_reference_chains(goal, sources.get("entries") or {}); events, warnings = build_goal_timeline(goal, sources, refs)
        return GoalOperationsTimeline(_seal("timeline", sources, {"goal_id": str(goal_id), "event_count": len(events), "events": events, "warnings": warnings}, {"goal_id": str(goal_id)}))

    def health(self) -> GoalOperationsHealth:
        sources = self._sources(permit_corrupt=True); refs = _refs_for_all(sources); return GoalOperationsHealth(_seal("health", sources, build_health(sources, refs)))

    def pending_approvals(self) -> GoalOperationsPendingApprovals:
        sources = self._sources(); approvals = []
        for goal in sources["goals"]:
            refs = build_reference_chains(goal, sources.get("entries") or {})
            for chain in refs["chains"]:
                if chain.get("entry_status") != "waiting_for_approval": continue
                approval = _mapping(chain.get("approval")); plan = _mapping(chain.get("execution_plan_reference")); milestone = _mapping(_mapping(goal.get("milestones")).get(str(chain.get("milestone_id"))))
                status = approval.get("status") or "pending"; expiry = approval.get("expires_at")
                if expiry and self.config.reference_time and parse_time(self.config.reference_time) >= parse_time(expiry): status = "expired"
                value = {"goal_id": goal["goal_id"], "milestone_id": chain.get("milestone_id"), "entry_id": chain.get("entry_id"), "mission_id": chain.get("mission_id"), "session_id": chain.get("session_id"), "approval_or_proposal_id": approval.get("approval_id") or plan.get("plan_id"), "requested_scope": deepcopy(approval.get("requested_scope") or chain.get("requested_scope") or []), "approval_expectation": bool(milestone.get("approval_expected")), "created_timestamp": approval.get("created_at") or chain.get("artifact_created_at"), "expiry_timestamp": expiry, "current_status": status, "blocking_reason": "approval_expired" if status == "expired" else "operator_approval_required", "goal_progress": _mapping(goal.get("progress")).get("completion_percentage", 0), "other_milestones_can_continue": bool([item for item in _mapping(goal.get("progress")).get("next_ready_milestone_ids") or [] if item != chain.get("milestone_id")]), "reference_integrity": bool(chain.get("integrity")), "fingerprint": fingerprint({"goal": goal["goal_id"], "milestone": chain.get("milestone_id"), "entry": chain.get("entry_id"), "approval": approval.get("approval_fingerprint"), "plan": plan.get("fingerprint")})}
                approvals.append(value)
        approvals.sort(key=lambda item: (str(item["created_timestamp"]), str(item["goal_id"]), str(item["milestone_id"]), str(item["entry_id"])))
        return GoalOperationsPendingApprovals(_seal("pending_approvals", sources, {"pending_approval_count": len(approvals), "pending_approvals": approvals}))

__all__ = ["GoalOperationsConfig", "GoalOperationsGoalInspection", "GoalOperationsHealth", "GoalOperationsOverview", "GoalOperationsPendingApprovals", "GoalOperationsService", "GoalOperationsTimeline"]
