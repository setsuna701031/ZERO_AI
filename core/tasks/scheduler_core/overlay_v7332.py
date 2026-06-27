from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

def _zero_v7332_constitutional_metadata(payload: Any, depth: int = 0) -> Dict[str, Any]:
    if depth > 6 or not isinstance(payload, dict):
        return {}
    candidates = []
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        candidates.append(metadata)
    runtime_payload = payload.get("runtime_execution_result")
    if isinstance(runtime_payload, dict):
        runtime_metadata = runtime_payload.get("metadata")
        if isinstance(runtime_metadata, dict):
            candidates.append(runtime_metadata)
    candidates.append(payload)
    for candidate in candidates:
        if (
            candidate.get("constitutional_blocked") is True
            or candidate.get("constitutional_activation") is True
            or isinstance(candidate.get("constitutional_enforcement_snapshot"), dict)
            or isinstance(candidate.get("runtime_enforcement_decision"), dict)
        ):
            return copy.deepcopy(candidate)
    for key in ("last_step_result", "step_result", "last_result", "result", "task", "runtime_state", "execution", "raw_result"):
        found = _zero_v7332_constitutional_metadata(payload.get(key), depth + 1)
        if found:
            return found
    for key in ("results", "step_results", "execution_log", "executed_results"):
        items = payload.get(key)
        if isinstance(items, list):
            for item in reversed(items):
                found = _zero_v7332_constitutional_metadata(item, depth + 1)
                if found:
                    return found
    return {}


def _zero_v7332_is_constitutional_block(payload: Any) -> bool:
    metadata = _zero_v7332_constitutional_metadata(payload)
    if metadata.get("constitutional_blocked") is True:
        return True
    snapshot = metadata.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = metadata.get("runtime_enforcement_decision")
    return bool(
        isinstance(snapshot, dict)
        and snapshot.get("classification") == "block_recommended"
        and snapshot.get("safe_to_enforce") is True
        and metadata.get("constitutional_activation") is True
    )


def _zero_v7332_constitutional_boundary_payload(metadata: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = metadata.get("constitutional_enforcement_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = metadata.get("runtime_enforcement_decision")
    if not isinstance(snapshot, dict):
        snapshot = {}
    return {
        "constitutional_activation": bool(metadata.get("constitutional_activation", True)),
        "constitutional_activation_" + "mode": str(metadata.get("constitutional_activation_" + "mode") or ""),
        "constitutional_activation_reason": str(
            metadata.get("constitutional_activation_reason")
            or snapshot.get("reason")
            or "constitutional_blocked"
        ),
        "constitutional_blocked": bool(metadata.get("constitutional_blocked", False)),
        "constitutional_enforcement_snapshot": copy.deepcopy(snapshot),
        "constitutional_continuity_status": str(metadata.get("constitutional_continuity_status") or snapshot.get("classification") or ""),
        "runtime_enforcement_decision": copy.deepcopy(
            metadata.get("runtime_enforcement_decision")
            if isinstance(metadata.get("runtime_enforcement_decision"), dict)
            else snapshot
        ),
    }


def _zero_v7332_mark_constitutional_boundary(
    scheduler: Any,
    *,
    task: Dict[str, Any],
    runner_result: Dict[str, Any],
    status_review_required: str = "review_required",
) -> Dict[str, Any]:
    if not isinstance(runner_result, dict):
        return runner_result
    metadata = _zero_v7332_constitutional_metadata(runner_result)
    if not metadata or not _zero_v7332_is_constitutional_block(runner_result):
        return runner_result
    boundary = _zero_v7332_constitutional_boundary_payload(metadata)
    reason = boundary["constitutional_activation_reason"] or "constitutional_blocked"
    enriched = copy.deepcopy(runner_result)
    enriched["ok"] = False
    enriched["status"] = status_review_required
    enriched["action"] = "constitutional_blocked"
    enriched["blocked_reason"] = reason
    enriched["waiting_reason"] = "constitutional_review_required"
    enriched["retryable"] = False
    enriched["constitutional_boundary"] = copy.deepcopy(boundary)
    enriched["constitutional_blocked"] = True
    enriched["needs_review"] = True
    enriched["requires_review"] = True
    for target in (task, enriched.get("task"), enriched.get("runtime_state")):
        if isinstance(target, dict):
            target["status"] = status_review_required
            target["blocked_reason"] = reason
            target["waiting_reason"] = "constitutional_review_required"
            target["failure_type"] = "constitutional_blocked"
            target["constitutional_boundary"] = copy.deepcopy(boundary)
            target["constitutional_blocked"] = True
            target["requires_review"] = True
            target["retry_count"] = int(target.get("retry_count", 0) or 0)
            target["next_retry_tick"] = 0
    if isinstance(enriched.get("last_step_result"), dict):
        enriched["last_step_result"]["retryable"] = False
    return enriched

def _zero_v7332_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    if _zero_v7332_is_constitutional_block(task):
        return False, "constitutional block requires governed review"
    return original(scheduler, task)
