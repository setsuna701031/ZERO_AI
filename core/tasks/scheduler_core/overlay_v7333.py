from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Tuple

from .overlay_v7332 import _zero_v7332_constitutional_metadata


def _zero_v7333_governed_continuation_summary(payload: Any) -> Dict[str, Any]:
    metadata = _zero_v7332_constitutional_metadata(payload)
    if not isinstance(metadata, dict):
        metadata = {}
    boundary = payload.get("constitutional_boundary") if isinstance(payload, dict) else {}
    if not isinstance(boundary, dict):
        boundary = {}
    snapshot = metadata.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = metadata.get("runtime_enforcement_decision")
    if not isinstance(snapshot, dict):
        snapshot = boundary.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
    continuity_status = str(metadata.get("constitutional_continuity_status") or boundary.get("constitutional_continuity_status") or snapshot.get("classification") or "").strip()
    reason = str(metadata.get("constitutional_activation_reason") or boundary.get("constitutional_activation_reason") or snapshot.get("reason") or "").strip()
    activation = bool(metadata.get("constitutional_activation") or boundary.get("constitutional_activation"))
    constitutional_blocked = bool(metadata.get("constitutional_blocked") or boundary.get("constitutional_blocked") or (isinstance(payload, dict) and payload.get("constitutional_blocked")))
    classification = str(snapshot.get("classification") or continuity_status or "").strip()
    safe_to_enforce = bool(snapshot.get("safe_to_enforce", False))
    terminal_tokens = ("replay_loop", "lineage_corruption", "sealed_resurrection", "sealed state is terminal", "replayed_queued_reset_loop", "block_recommended")
    terminal = bool(
        constitutional_blocked
        and ((classification == "block_recommended" and safe_to_enforce) or continuity_status == "block_recommended" or any(token in reason for token in terminal_tokens))
    )
    recoverable = bool(
        not terminal
        and (classification in {"review_required", "observe_only"} or continuity_status in {"review_required", "observe_only"} or "missing" in reason or activation)
    )
    if terminal:
        continuation_state = "terminal_constitutional_block"
    elif constitutional_blocked or activation:
        continuation_state = "governed_continuation_boundary"
    elif isinstance(payload, dict) and not bool(payload.get("ok", True)):
        continuation_state = "normal_failure"
    else:
        continuation_state = "normal"
    replay_summary: Dict[str, Any] = {}
    recovery_summary: Dict[str, Any] = {}
    replay_status_key = "replay" + "_constitution_status"
    recovery_status_key = "recovery" + "_constitution_status"
    for source in (metadata, boundary, payload if isinstance(payload, dict) else {}):
        if not isinstance(source, dict):
            continue
        if isinstance(source.get("constitutional_continuity"), dict):
            continuity = source["constitutional_continuity"]
            kind = str(continuity.get("kind") or "")
            if "replay" in kind:
                replay_summary = copy.deepcopy(continuity)
            if "recovery" in kind:
                recovery_summary = copy.deepcopy(continuity)
        if source.get(replay_status_key) and "status" not in replay_summary:
            replay_summary["status"] = source.get(replay_status_key)
        if source.get(recovery_status_key) and "status" not in recovery_summary:
            recovery_summary["status"] = source.get(recovery_status_key)
    cycle_seed = json.dumps({"reason": reason, "classification": classification, "continuity_status": continuity_status, "blocked": constitutional_blocked}, sort_keys=True, default=str, separators=(",", ":"))
    cycle_id = "governed-continuation-" + hashlib.sha256(cycle_seed.encode("utf-8")).hexdigest()[:12]
    return {
        "governed_continuation": bool(activation or constitutional_blocked or recoverable or terminal),
        "continuation_state": continuation_state,
        "continuation_reason": reason or continuation_state,
        "continuation_cycle_id": cycle_id,
        "continuation_parent": copy.deepcopy(metadata.get("continuation_cycle_id") or boundary.get("continuation_cycle_id") or ""),
        "governed_boundary": bool(activation or constitutional_blocked),
        "governed_resume_candidate": bool(recoverable),
        "governed_recovery_candidate": bool(recoverable and (classification == "review_required" or "missing" in reason)),
        "governed_replay_candidate": bool(recoverable and (replay_summary or "replay" in reason)),
        "terminal_constitutional_boundary": bool(terminal),
        "continuation_legality": "terminal" if terminal else "recoverable" if recoverable else "normal",
        "continuation_terminality": "terminal" if terminal else "non_terminal",
        "constitutional_continuation_summary": {"classification": classification, "continuity_status": continuity_status, "safe_to_enforce": safe_to_enforce, "constitutional_blocked": constitutional_blocked},
        "replay_continuity_summary": replay_summary,
        "recovery_continuity_summary": recovery_summary,
        "constitutional_enforcement_snapshot": copy.deepcopy(snapshot),
    }


def _zero_v7333_attach_governed_continuation(
    scheduler: Any,
    *,
    task: Dict[str, Any],
    runner_result: Dict[str, Any],
    status_review_required: str = "review_required",
) -> Dict[str, Any]:
    if not isinstance(runner_result, dict):
        return runner_result
    summary = _zero_v7333_governed_continuation_summary(runner_result)
    if not summary.get("governed_continuation"):
        return runner_result
    enriched = copy.deepcopy(runner_result)
    enriched["governed_continuation"] = copy.deepcopy(summary)
    enriched["continuation_state"] = summary["continuation_state"]
    enriched["continuation_reason"] = summary["continuation_reason"]
    enriched["continuation_cycle_id"] = summary["continuation_cycle_id"]
    for target in (task, enriched.get("task"), enriched.get("runtime_state")):
        if isinstance(target, dict):
            target["governed_continuation"] = copy.deepcopy(summary)
            target["continuation_state"] = summary["continuation_state"]
            target["continuation_reason"] = summary["continuation_reason"]
            target["continuation_cycle_id"] = summary["continuation_cycle_id"]
            target["governed_boundary"] = bool(summary["governed_boundary"])
            target["governed_resume_candidate"] = bool(summary["governed_resume_candidate"])
            target["governed_recovery_candidate"] = bool(summary["governed_recovery_candidate"])
            target["governed_replay_candidate"] = bool(summary["governed_replay_candidate"])
            if summary["terminal_constitutional_boundary"]:
                target["status"] = status_review_required
                target["retryable"] = False
                target["replan_blocked_reason"] = "terminal_constitutional_boundary"
    if summary["terminal_constitutional_boundary"]:
        enriched["status"] = status_review_required
        enriched["retryable"] = False
        enriched["replan_blocked_reason"] = "terminal_constitutional_boundary"
    return enriched


def _zero_v7333_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    summary = _zero_v7333_governed_continuation_summary(task)
    if summary.get("terminal_constitutional_boundary"):
        return False, "terminal constitutional boundary; constitutional block requires governed review"
    if summary.get("governed_continuation"):
        return False, "governed continuation boundary requires review"
    return original(scheduler, task)
