from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_queue_finalization_contract import (
    QUEUE_FINALIZATION_CONTRACT_VERSION,
    QUEUE_FINALIZATION_FORBIDDEN_EFFECTS,
    RuntimeQueueFinalizationRequest,
)

QUEUE_FINALIZATION_POLICY_VERSION = "runtime.queue_finalization.policy.v1.preview"

_FINALIZABLE_LIFECYCLE_STATUSES = frozenset(
    {
        "finished",
        "failed",
        "blocked",
        "cancelled",
    }
)

_READY_COMMIT_STATUSES = frozenset(
    {
        "committed",
        "preview_committed",
        "noop_committed",
    }
)

_READY_RUNTIME_STATE_STATUSES = frozenset(
    {
        "updated",
        "preview_updated",
        "noop_updated",
    }
)


def evaluate_queue_finalization_policy(
    request: RuntimeQueueFinalizationRequest | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(request, RuntimeQueueFinalizationRequest):
        payload = request.to_dict()
    else:
        payload = dict(request)

    lifecycle_status = str(payload.get("lifecycle_status") or "").strip().lower()
    result_commit_status = str(payload.get("result_commit_status") or "").strip().lower()
    runtime_state_update_status = str(payload.get("runtime_state_update_status") or "").strip().lower()

    finalizable = (
        lifecycle_status in _FINALIZABLE_LIFECYCLE_STATUSES
        and result_commit_status in _READY_COMMIT_STATUSES
        and runtime_state_update_status in _READY_RUNTIME_STATE_STATUSES
    )

    blockers: list[str] = []
    if lifecycle_status not in _FINALIZABLE_LIFECYCLE_STATUSES:
        blockers.append("lifecycle_status_not_finalizable")
    if result_commit_status not in _READY_COMMIT_STATUSES:
        blockers.append("result_commit_not_ready")
    if runtime_state_update_status not in _READY_RUNTIME_STATE_STATUSES:
        blockers.append("runtime_state_update_not_ready")

    return {
        "contract_version": QUEUE_FINALIZATION_CONTRACT_VERSION,
        "policy_version": QUEUE_FINALIZATION_POLICY_VERSION,
        "enabled": False,
        "preview_only": True,
        "queue_finalization_allowed": False,
        "queue_mutation_allowed": False,
        "runtime_state_mutation_allowed": False,
        "tool_execution_allowed": False,
        "autonomous_execution_allowed": False,
        "finalizable_preview": finalizable,
        "blockers": blockers,
        "forbidden_effects": list(QUEUE_FINALIZATION_FORBIDDEN_EFFECTS),
        "reason": "queue_finalization_reserved_for_future_activation",
    }
