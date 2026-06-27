from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

from .overlay_v7332 import _zero_v7332_constitutional_metadata
from .overlay_v7333 import _zero_v7333_governed_continuation_summary


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


def _zero_v7334_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    summary = _zero_v7334_governed_self_repair_summary(task)
    if summary.get("self_repair_terminal_block"):
        return False, "terminal constitutional boundary; constitutional block self-repair block requires governed review"
    if summary.get("self_repair_review_required"):
        return False, "governed self-repair requires review"
    return original(scheduler, task)
