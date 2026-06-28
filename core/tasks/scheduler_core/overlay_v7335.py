from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

from .overlay_v7334 import _zero_v7334_governed_self_repair_summary


def _zero_v7335_controlled_mutation_bridge_summary(payload: Any) -> Dict[str, Any]:
    self_repair = {}
    if isinstance(payload, dict) and isinstance(payload.get("governed_self_repair"), dict):
        self_repair = copy.deepcopy(payload["governed_self_repair"])
    if not self_repair:
        self_repair = _zero_v7334_governed_self_repair_summary(payload)
    if not isinstance(self_repair, dict) or not self_repair.get("governed_self_repair"):
        return {"controlled_mutation_bridge": False, "mutation_bridge_state": "no_bridge", "mutation_bridge_reason": "no governed self-repair candidate", "mutation_bridge_eligible": False, "mutation_bridge_requires_review": False, "mutation_bridge_blocked": False, "bridge_legality": "not_applicable", "bridge_requires_review": False, "bridge_terminality": "non_terminal", "bridge_verification_required": False, "bridge_rollback_required": False}
    boundary = self_repair.get("self_repair_boundary")
    if not isinstance(boundary, dict):
        boundary = {}
    lineage = self_repair.get("self_repair_lineage")
    if not isinstance(lineage, dict):
        lineage = {}
    snapshot = boundary.get("enforcement_snapshot")
    if not isinstance(snapshot, dict):
        continuation = payload.get("governed_continuation") if isinstance(payload, dict) else {}
        if isinstance(continuation, dict):
            snapshot = continuation.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
    replay_snapshot = copy.deepcopy(lineage.get("replay_continuity_summary", {}))
    recovery_snapshot = copy.deepcopy(lineage.get("recovery_continuity_summary", {}))
    lineage_present = bool(lineage and (lineage.get("continuation_cycle_id") or lineage.get("continuation_parent")) and "replay_continuity_summary" in lineage and "recovery_continuity_summary" in lineage)
    candidate = bool(self_repair.get("self_repair_candidate") or self_repair.get("self_repair_review_required"))
    terminal = bool(self_repair.get("self_repair_terminal_block") or self_repair.get("self_repair_terminality") == "terminal" or (snapshot.get("classification") == "block_recommended" and snapshot.get("safe_to_enforce") is True))
    if terminal:
        state = "bridge_blocked_terminal"
        reason = "terminal constitutional repair block cannot enter mutation bridge"
    elif not candidate:
        state = "bridge_not_applicable"
        reason = "self-repair state is not a bridge candidate"
    elif not snapshot:
        state = "bridge_blocked_missing_enforcement_snapshot"
        reason = "controlled mutation bridge requires an enforcement snapshot"
    elif not lineage_present:
        state = "bridge_blocked_missing_continuation_lineage"
        reason = "controlled mutation bridge requires continuation lineage"
    else:
        state = "bridge_ready_for_review"
        reason = "self-repair candidate is eligible for guarded mutation bridge review"
    eligible = state == "bridge_ready_for_review"
    blocked = state.startswith("bridge_blocked")
    requires_review = bool(eligible or self_repair.get("self_repair_requires_review"))
    summary = {"state": state, "eligible": eligible, "requires_review": requires_review, "blocked": blocked, "terminal": terminal, "verification_required": eligible, "rollback_required": eligible, "reason": reason}
    return {
        "controlled_mutation_bridge": state != "no_bridge",
        "mutation_bridge_state": state,
        "mutation_bridge_reason": reason,
        "mutation_bridge_eligible": eligible,
        "mutation_bridge_requires_review": requires_review,
        "mutation_bridge_blocked": blocked,
        "mutation_bridge_lineage": copy.deepcopy(lineage),
        "mutation_bridge_enforcement_snapshot": copy.deepcopy(snapshot),
        "mutation_bridge_replay_snapshot": replay_snapshot,
        "mutation_bridge_recovery_snapshot": recovery_snapshot,
        "controlled_mutation_bridge_summary": summary,
        "bridge_legality": "review_required" if eligible else "blocked" if blocked else "not_applicable",
        "bridge_requires_review": requires_review,
        "bridge_terminality": "terminal" if terminal else "non_terminal",
        "bridge_verification_required": eligible,
        "bridge_rollback_required": eligible,
    }


def _zero_v7335_attach_controlled_mutation_bridge(target: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(target, dict):
        return target
    summary = _zero_v7335_controlled_mutation_bridge_summary(target)
    if not summary.get("controlled_mutation_bridge"):
        return target
    target["controlled_mutation_bridge"] = copy.deepcopy(summary)
    for key in ("mutation_bridge_state", "mutation_bridge_reason", "mutation_bridge_eligible", "mutation_bridge_requires_review", "mutation_bridge_blocked", "mutation_bridge_lineage", "mutation_bridge_enforcement_snapshot", "mutation_bridge_replay_snapshot", "mutation_bridge_recovery_snapshot", "controlled_mutation_bridge_summary", "bridge_legality", "bridge_requires_review", "bridge_terminality", "bridge_verification_required", "bridge_rollback_required"):
        target[key] = copy.deepcopy(summary[key])
    if summary["mutation_bridge_blocked"]:
        target["retryable"] = False
        target.setdefault("replan_blocked_reason", summary["mutation_bridge_state"])
    elif summary["mutation_bridge_eligible"]:
        target["requires_review"] = True
        target["waiting_reason"] = "controlled_mutation_bridge_review_required"
    return target


def _zero_v7335_has_approved_execution_authority(task: Any) -> bool:
    if not isinstance(task, dict):
        return False
    authority = task.get("execution_authority")
    if not isinstance(authority, dict):
        return False
    status = str(authority.get("authority_status") or authority.get("status") or "").strip().lower()
    endpoint = str(authority.get("execution_authority_endpoint") or authority.get("authority_endpoint") or "").strip().lower()
    return status in {"allowed", "allow", "approved"} and endpoint in {"step_executor", "runtime_step_executor"}


def _zero_v7335_is_repair_work(task: Any) -> bool:
    if not isinstance(task, dict):
        return False
    if isinstance(task.get("repair_context"), dict) or task.get("failed_file") or task.get("repair_intent"):
        return True
    steps = task.get("steps")
    if not isinstance(steps, list):
        return False
    repair_types = {"code_chain_repair", "governed_repair_mutation", "autonomous_repair_chain", "runtime_autonomous_repair_chain"}
    return any(isinstance(step, dict) and str(step.get("type") or step.get("action") or "").strip().lower() in repair_types for step in steps)


def _zero_v7335_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    bridge = _zero_v7335_controlled_mutation_bridge_summary(task)
    if bridge.get("mutation_bridge_state") == "bridge_blocked_terminal":
        return False, "terminal constitutional boundary; constitutional block self-repair block cannot enter controlled mutation bridge"
    if bridge.get("mutation_bridge_eligible"):
        return False, "controlled mutation bridge requires governed review"
    return original(scheduler, task)
