from __future__ import annotations

import copy
from typing import Any, Dict, Tuple


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


def _zero_v7336_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    summary = _zero_v7336_verified_mutation_continuation_summary(task)
    if summary.get("verified_mutation_continuation") and summary.get("reentry_terminality") == "terminal":
        return False, "terminal verified mutation continuation cannot be repaired recursively"
    if summary.get("verified_mutation_continuation") and not summary.get("constitutional_reentry_allowed"):
        return False, "verified mutation continuation requires governed review before retry"
    return original(scheduler, task)
