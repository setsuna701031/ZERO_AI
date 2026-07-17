from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_autonomous_execution_admission_contract import (
    AUTONOMOUS_EXECUTION_ADMISSION_CONTRACT_VERSION,
    AUTONOMOUS_EXECUTION_ACCEPTED_TRIGGERS,
    AUTONOMOUS_EXECUTION_FORBIDDEN_EFFECTS,
    AutonomousExecutionAdmissionRequest,
)

AUTONOMOUS_EXECUTION_ADMISSION_POLICY_VERSION = (
    "runtime.autonomous_execution_admission.policy.v1.review"
)


def _budget_positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def evaluate_autonomous_execution_admission(
    request: AutonomousExecutionAdmissionRequest | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(request, AutonomousExecutionAdmissionRequest):
        payload = request.to_dict()
    else:
        payload = dict(request)

    trigger_source = str(payload.get("trigger_source") or "").strip()
    operator_override = bool(payload.get("operator_override"))
    execution_budget = payload.get("execution_budget") or {}
    stop_condition = str(payload.get("stop_condition") or "").strip()
    self_loop_guard = bool(payload.get("self_loop_guard"))
    audit_required = bool(payload.get("audit_required"))

    blockers: list[str] = []
    if trigger_source not in AUTONOMOUS_EXECUTION_ACCEPTED_TRIGGERS:
        blockers.append("untrusted_trigger_source")
    if not operator_override:
        blockers.append("operator_override_missing")
    if not isinstance(execution_budget, Mapping):
        blockers.append("execution_budget_not_mapping")
    else:
        if not _budget_positive_int(execution_budget.get("max_steps")):
            blockers.append("max_steps_budget_missing")
        if not _budget_positive_int(execution_budget.get("max_seconds")):
            blockers.append("max_seconds_budget_missing")
    if not stop_condition:
        blockers.append("stop_condition_missing")
    if not self_loop_guard:
        blockers.append("self_loop_guard_missing")
    if not audit_required:
        blockers.append("audit_not_required")

    admission_ready_preview = not blockers

    return {
        "contract_version": AUTONOMOUS_EXECUTION_ADMISSION_CONTRACT_VERSION,
        "policy_version": AUTONOMOUS_EXECUTION_ADMISSION_POLICY_VERSION,
        "enabled": False,
        "review_only": True,
        "preview_only": True,
        "autonomous_execution_admission_ready_preview": admission_ready_preview,
        "autonomous_execution_allowed": False,
        "autonomous_loop_start_allowed": False,
        "new_task_dispatch_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "queue_mutation_allowed": False,
        "external_io_allowed": False,
        "blockers": blockers,
        "forbidden_effects": list(AUTONOMOUS_EXECUTION_FORBIDDEN_EFFECTS),
        "reason": "autonomous_execution_admission_reserved_for_future_activation",
    }
