from __future__ import annotations

"""Scheduler runtime contract adapter.

This module is the narrow compatibility surface used by external-facing
runtime/agent layers that need scheduler-owned summary helpers without directly
importing ``core.tasks.scheduler``.

Boundary rule:
- Agent-facing code imports this adapter only.
- The adapter remains inside ``core.tasks`` and may delegate to scheduler-owned
  compatibility helpers.
- The adapter does not enqueue tasks, execute steps, mutate runtime state, or
  bypass governance gates.
"""

import copy
from typing import Any, Dict, Mapping


SCHEDULER_RUNTIME_CONTRACT_SCHEMA = "zero.scheduler.runtime_contract.v1"
SCHEDULER_RUNTIME_TRANSITIONS = {
    "queued": frozenset({"planned", "claimed", "paused", "blocked", "failed"}),
    "planned": frozenset({"claimed", "paused", "blocked", "failed"}),
    "claimed": frozenset({"executing", "paused", "blocked", "failed"}),
    "executing": frozenset({"executing", "paused", "blocked", "failed", "completed"}),
    "paused": frozenset({"planned", "claimed", "blocked", "failed"}),
    "blocked": frozenset({"planned", "failed"}),
    "failed": frozenset(),
    "completed": frozenset(),
}


class SchedulerRuntimeContractError(RuntimeError):
    pass


def validate_scheduler_lifecycle_transition(from_state: str, to_state: str) -> bool:
    return str(to_state or "") in SCHEDULER_RUNTIME_TRANSITIONS.get(
        str(from_state or ""), frozenset()
    )


def build_scheduler_runtime_contract(
    payload: Mapping[str, Any],
    *,
    lifecycle_state: str,
    dispatch_path: str,
) -> Dict[str, Any]:
    authority = payload.get("execution_authority")
    if not isinstance(authority, Mapping):
        context = payload.get("authority_context")
        authority = (
            context.get("execution_authority")
            if isinstance(context, Mapping)
            and isinstance(context.get("execution_authority"), Mapping)
            else {}
        )
    task_id = str(payload.get("task_id") or payload.get("task_name") or "").strip()
    return {
        "schema": SCHEDULER_RUNTIME_CONTRACT_SCHEMA,
        "package_id": str(payload.get("package_id") or "").strip(),
        "session_id": str(
            payload.get("session_id")
            or payload.get("operator_session_id")
            or payload.get("persistent_operator_session_id")
            or ""
        ).strip(),
        "task_id": task_id,
        "lifecycle_state": str(lifecycle_state or "").strip(),
        "authority": copy.deepcopy(dict(authority)),
        "dispatch_path": str(dispatch_path or "").strip(),
    }


def validate_scheduler_runtime_contract(
    contract: Mapping[str, Any],
    *,
    require_package_identity: bool = False,
    require_session_identity: bool = False,
    require_authority_metadata: bool = False,
) -> Dict[str, Any]:
    errors = []
    if str(contract.get("schema") or "") != SCHEDULER_RUNTIME_CONTRACT_SCHEMA:
        errors.append("invalid_schema")
    if require_package_identity and not str(contract.get("package_id") or "").strip():
        errors.append("package_identity_missing")
    if require_session_identity and not str(contract.get("session_id") or "").strip():
        errors.append("session_identity_missing")
    if not str(contract.get("task_id") or "").strip():
        errors.append("task_identity_missing")
    if str(contract.get("lifecycle_state") or "") not in SCHEDULER_RUNTIME_TRANSITIONS:
        errors.append("lifecycle_state_invalid")
    authority = contract.get("authority")
    if require_authority_metadata and (not isinstance(authority, Mapping) or not authority):
        errors.append("authority_metadata_missing")
    elif require_authority_metadata and not str(authority.get("authority_source") or "").strip():
        errors.append("authority_source_missing")
    if not str(contract.get("dispatch_path") or "").strip():
        errors.append("dispatch_path_missing")
    return {"ok": not errors, "errors": errors, "contract": copy.deepcopy(dict(contract))}


def seal_scheduler_runtime_contract(
    payload: Mapping[str, Any],
    *,
    lifecycle_state: str,
    dispatch_path: str,
    require_package_identity: bool = False,
    require_session_identity: bool = False,
    require_authority_metadata: bool = False,
) -> Dict[str, Any]:
    contract = build_scheduler_runtime_contract(
        payload,
        lifecycle_state=lifecycle_state,
        dispatch_path=dispatch_path,
    )
    validation = validate_scheduler_runtime_contract(
        contract,
        require_package_identity=require_package_identity,
        require_session_identity=require_session_identity,
        require_authority_metadata=require_authority_metadata,
    )
    if not validation["ok"]:
        raise SchedulerRuntimeContractError(
            "invalid_scheduler_runtime_contract:" + ",".join(validation["errors"])
        )
    return contract


def _scheduler_module() -> Any:
    from core.tasks import scheduler as scheduler_module

    return scheduler_module


def _safe_summary(function_name: str, payload: Any) -> Dict[str, Any]:
    try:
        function = getattr(_scheduler_module(), function_name, None)
        if not callable(function):
            return {}
        summary = function(payload)
    except Exception:
        return {}
    return copy.deepcopy(summary) if isinstance(summary, dict) else {}


def governed_continuation_summary(payload: Any) -> Dict[str, Any]:
    return _safe_summary("_zero_v7333_governed_continuation_summary", payload)


def governed_self_repair_summary(payload: Any) -> Dict[str, Any]:
    return _safe_summary("_zero_v7334_governed_self_repair_summary", payload)


def controlled_mutation_bridge_summary(payload: Any) -> Dict[str, Any]:
    return _safe_summary("_zero_v7335_controlled_mutation_bridge_summary", payload)


__all__ = [
    "SCHEDULER_RUNTIME_CONTRACT_SCHEMA",
    "SCHEDULER_RUNTIME_TRANSITIONS",
    "SchedulerRuntimeContractError",
    "build_scheduler_runtime_contract",
    "governed_continuation_summary",
    "governed_self_repair_summary",
    "controlled_mutation_bridge_summary",
    "seal_scheduler_runtime_contract",
    "validate_scheduler_lifecycle_transition",
    "validate_scheduler_runtime_contract",
]
