from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

from .overlay_v7332 import _zero_v7332_constitutional_boundary_payload, _zero_v7332_constitutional_metadata, _zero_v7332_is_constitutional_block, _zero_v7332_mark_constitutional_boundary, _zero_v7332_repairable_decision
from .overlay_v7333 import _zero_v7333_attach_governed_continuation, _zero_v7333_governed_continuation_summary, _zero_v7333_repairable_decision


def _zero_v7334_governed_self_repair_summary(payload: Any) -> Dict[str, Any]:
    continuation = {}
    if isinstance(payload, dict) and isinstance(payload.get("governed_continuation"), dict):
        continuation = copy.deepcopy(payload["governed_continuation"])
    if not continuation:
        continuation = _zero_v7333_governed_continuation_summary(payload)
    metadata = _zero_v7332_constitutional_metadata(payload)
    if not isinstance(metadata, dict):
        metadata = {}
    snapshot = continuation.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = metadata.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = metadata.get("runtime_enforcement_decision")
    if not isinstance(snapshot, dict):
        snapshot = {}
    terminal = bool(continuation.get("terminal_constitutional_boundary"))
    recoverable = bool(continuation.get("governed_resume_candidate") or continuation.get("governed_recovery_candidate") or continuation.get("governed_replay_candidate"))
    reason = str(continuation.get("continuation_reason") or metadata.get("constitutional_activation_reason") or snapshot.get("reason") or "")
    classification = str(snapshot.get("classification") or "")
    verification_failed = bool(isinstance(payload, dict) and (payload.get("verification_passed") is False or payload.get("failed") is True or payload.get("ok") is False))
    if terminal:
        state = "repair_blocked_terminal"
    elif recoverable and ("missing" in reason or classification == "review_required"):
        state = "repair_review_required"
    elif recoverable or (classification == "observe_only" and verification_failed):
        state = "repair_candidate"
    elif classification == "observe_only":
        state = "repair_deferred"
    else:
        state = "no_repair"
    candidate = state in {"repair_candidate", "repair_review_required"}
    review_required = state == "repair_review_required"
    terminal_block = state == "repair_blocked_terminal"
    lineage = {
        "continuation_cycle_id": continuation.get("continuation_cycle_id", ""),
        "continuation_parent": continuation.get("continuation_parent", ""),
        "replay_continuity_summary": copy.deepcopy(continuation.get("replay_continuity_summary", {})),
        "recovery_continuity_summary": copy.deepcopy(continuation.get("recovery_continuity_summary", {})),
    }
    boundary = {"reason": reason or state, "classification": classification, "continuation_state": continuation.get("continuation_state", ""), "terminal_constitutional_boundary": terminal, "enforcement_snapshot": copy.deepcopy(snapshot)}
    return {
        "governed_self_repair": state != "no_repair",
        "self_repair_state": state,
        "self_repair_reason": reason or state,
        "self_repair_candidate": candidate,
        "self_repair_review_required": review_required,
        "self_repair_terminal_block": terminal_block,
        "self_repair_bridge_ready": False,
        "self_repair_boundary": boundary,
        "self_repair_lineage": lineage,
        "governed_self_repair_summary": {"state": state, "candidate": candidate, "requires_review": review_required, "terminal_block": terminal_block, "bridge_ready": False, "reason": reason or state},
        "self_repair_legality": "blocked" if terminal_block else "review_required" if review_required else "candidate" if candidate else "none",
        "self_repair_terminality": "terminal" if terminal_block else "non_terminal",
        "self_repair_requires_review": bool(review_required or candidate),
        "self_repair_bridge_status": "not_wired",
    }


def _zero_v7334_attach_self_repair_summary(target: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(target, dict):
        return target
    summary = _zero_v7334_governed_self_repair_summary(target)
    if not summary.get("governed_self_repair"):
        return target
    target["governed_self_repair"] = copy.deepcopy(summary)
    for key in ("self_repair_state", "self_repair_reason", "self_repair_candidate", "self_repair_review_required", "self_repair_terminal_block", "self_repair_bridge_ready", "self_repair_boundary", "self_repair_lineage", "governed_self_repair_summary", "self_repair_legality", "self_repair_terminality", "self_repair_requires_review", "self_repair_bridge_status"):
        target[key] = copy.deepcopy(summary[key])
    if summary["self_repair_terminal_block"]:
        target["retryable"] = False
        target["replan_blocked_reason"] = "terminal_constitutional_boundary"
    return target


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


def _zero_v7336_verified_mutation_continuation_summary(payload: Any) -> Dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    vm = {}
    for candidate in (source.get("verified_mutation_continuation"), metadata.get("verified_mutation_continuation")):
        if isinstance(candidate, dict):
            vm = copy.deepcopy(candidate)
            break
    if not vm:
        for carrier in (source, metadata):
            if isinstance(carrier, dict) and ("verified_mutation_state" in carrier or "constitutional_reentry_allowed" in carrier or "verified_mutation_runtime_summary" in carrier):
                vm = copy.deepcopy(carrier)
                break
    if not vm:
        return {"verified_mutation_continuation": False, "verified_mutation_state": "no_verified_mutation_continuation", "constitutional_reentry_allowed": False, "verified_mutation_runtime_summary": {"reentry_legality": "not_applicable", "reentry_requires_review": False, "reentry_terminality": "non_terminal", "reentry_verification_status": "unknown", "reentry_replay_safe": False, "reentry_rollback_safe": False}, "reentry_legality": "not_applicable", "reentry_requires_review": False, "reentry_terminality": "non_terminal", "reentry_verification_status": "unknown", "reentry_replay_safe": False, "reentry_rollback_safe": False}
    state = str(vm.get("verified_mutation_state") or "").strip() or "verified_mutation_continuation"
    runtime_summary = vm.get("verified_mutation_runtime_summary")
    if not isinstance(runtime_summary, dict):
        runtime_summary = {}
    reentry_allowed = bool(vm.get("constitutional_reentry_allowed") or (isinstance(vm.get("verified_mutation_reentry"), dict) and vm["verified_mutation_reentry"].get("constitutional_reentry_allowed") is True))
    terminal = bool(vm.get("verified_mutation_terminality") == "terminal" or runtime_summary.get("reentry_terminality") == "terminal" or state.endswith("_terminal") or "blocked_terminal" in state)
    replay_safe = bool(vm.get("verified_mutation_replay_safe") or runtime_summary.get("reentry_replay_safe"))
    rollback_safe = bool(vm.get("verified_mutation_rollback_safe") or runtime_summary.get("reentry_rollback_safe"))
    verification_passed = bool(vm.get("verified_mutation_verification_passed") or runtime_summary.get("reentry_verification_status") == "passed")
    legality = "allowed" if reentry_allowed else "blocked" if terminal else "review_required"
    return {
        "verified_mutation_continuation": True,
        "verified_mutation_state": state,
        "verified_mutation_summary": copy.deepcopy(vm.get("verified_mutation_summary", {})),
        "verified_mutation_reentry": copy.deepcopy(vm.get("verified_mutation_reentry", {})),
        "constitutional_reentry_allowed": reentry_allowed,
        "verified_mutation_replay_safe": replay_safe,
        "verified_mutation_rollback_safe": rollback_safe,
        "verified_mutation_verification_passed": verification_passed,
        "verified_mutation_requires_review": bool(vm.get("verified_mutation_requires_review") or not reentry_allowed),
        "verified_mutation_terminality": "terminal" if terminal else "non_terminal",
        "verified_mutation_chain": copy.deepcopy(vm.get("verified_mutation_chain", {})),
        "verified_mutation_replay_snapshot": copy.deepcopy(vm.get("verified_mutation_replay_snapshot", {})),
        "verified_mutation_recovery_snapshot": copy.deepcopy(vm.get("verified_mutation_recovery_snapshot", {})),
        "verified_mutation_rollback_snapshot": copy.deepcopy(vm.get("verified_mutation_rollback_snapshot", {})),
        "verified_mutation_enforcement_snapshot": copy.deepcopy(vm.get("verified_mutation_enforcement_snapshot", {})),
        "verified_mutation_runtime_summary": {**copy.deepcopy(runtime_summary), "reentry_legality": legality, "reentry_requires_review": bool(not reentry_allowed), "reentry_terminality": "terminal" if terminal else "non_terminal", "reentry_verification_status": "passed" if verification_passed else runtime_summary.get("reentry_verification_status", "missing_or_failed"), "reentry_replay_safe": replay_safe, "reentry_rollback_safe": rollback_safe},
        "reentry_legality": legality,
        "reentry_requires_review": bool(not reentry_allowed),
        "reentry_terminality": "terminal" if terminal else "non_terminal",
        "reentry_verification_status": "passed" if verification_passed else "missing_or_failed",
        "reentry_replay_safe": replay_safe,
        "reentry_rollback_safe": rollback_safe,
    }


def _zero_v7336_attach_verified_mutation_continuation(target: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(target, dict):
        return target
    summary = _zero_v7336_verified_mutation_continuation_summary(target)
    if not summary.get("verified_mutation_continuation"):
        return target
    target["verified_mutation_continuation"] = copy.deepcopy(summary)
    for key in ("verified_mutation_state", "verified_mutation_summary", "verified_mutation_reentry", "constitutional_reentry_allowed", "verified_mutation_replay_safe", "verified_mutation_rollback_safe", "verified_mutation_verification_passed", "verified_mutation_requires_review", "verified_mutation_terminality", "verified_mutation_chain", "verified_mutation_replay_snapshot", "verified_mutation_recovery_snapshot", "verified_mutation_rollback_snapshot", "verified_mutation_enforcement_snapshot", "verified_mutation_runtime_summary", "reentry_legality", "reentry_requires_review", "reentry_terminality", "reentry_verification_status", "reentry_replay_safe", "reentry_rollback_safe"):
        target[key] = copy.deepcopy(summary[key])
    if summary["reentry_terminality"] == "terminal" or not summary["constitutional_reentry_allowed"]:
        target["retryable"] = False
        target.setdefault("replan_blocked_reason", summary["verified_mutation_state"])
    return target


def _zero_v7332_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    if _zero_v7332_is_constitutional_block(task):
        return False, "constitutional block requires governed review"
    return original(scheduler, task)


def _zero_v7334_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    summary = _zero_v7334_governed_self_repair_summary(task)
    if summary.get("self_repair_terminal_block"):
        return False, "terminal constitutional boundary; constitutional block self-repair block requires governed review"
    if summary.get("self_repair_review_required"):
        return False, "governed self-repair requires review"
    return original(scheduler, task)


def _zero_v7335_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    bridge = _zero_v7335_controlled_mutation_bridge_summary(task)
    if bridge.get("mutation_bridge_state") == "bridge_blocked_terminal":
        return False, "terminal constitutional boundary; constitutional block self-repair block cannot enter controlled mutation bridge"
    if bridge.get("mutation_bridge_eligible"):
        return False, "controlled mutation bridge requires governed review"
    return original(scheduler, task)


def _zero_v7336_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    summary = _zero_v7336_verified_mutation_continuation_summary(task)
    if summary.get("verified_mutation_continuation") and summary.get("reentry_terminality") == "terminal":
        return False, "terminal verified mutation continuation cannot be repaired recursively"
    if summary.get("verified_mutation_continuation") and not summary.get("constitutional_reentry_allowed"):
        return False, "verified mutation continuation requires governed review before retry"
    return original(scheduler, task)
