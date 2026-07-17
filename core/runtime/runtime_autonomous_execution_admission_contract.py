from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

AUTONOMOUS_EXECUTION_ADMISSION_CONTRACT_VERSION = (
    "runtime.autonomous_execution_admission.v1.review"
)

AUTONOMOUS_EXECUTION_REQUIRED_FIELDS = (
    "request_id",
    "task_id",
    "trigger_source",
    "operator_override",
    "execution_budget",
    "stop_condition",
    "self_loop_guard",
    "audit_required",
)

AUTONOMOUS_EXECUTION_ACCEPTED_TRIGGERS = frozenset(
    {
        "operator_explicit_start",
        "runtime_activation_gate",
        "sealed_test_authority",
    }
)

AUTONOMOUS_EXECUTION_FORBIDDEN_EFFECTS = (
    "start_autonomous_loop",
    "dispatch_new_task",
    "invoke_tool",
    "perform_runtime_mutation",
    "perform_queue_mutation",
    "perform_external_io",
)


@dataclass(frozen=True)
class AutonomousExecutionAdmissionRequest:
    request_id: str
    task_id: str
    trigger_source: str
    operator_override: bool
    execution_budget: Mapping[str, Any]
    stop_condition: str
    self_loop_guard: bool
    audit_required: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": AUTONOMOUS_EXECUTION_ADMISSION_CONTRACT_VERSION,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "trigger_source": self.trigger_source,
            "operator_override": self.operator_override,
            "execution_budget": dict(self.execution_budget),
            "stop_condition": self.stop_condition,
            "self_loop_guard": self.self_loop_guard,
            "audit_required": self.audit_required,
            "metadata": dict(self.metadata),
        }


def _budget_positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def _only_stop_condition_is_invalid(payload: Mapping[str, Any]) -> bool:
    execution_budget = payload.get("execution_budget")
    return (
        str(payload.get("request_id") or "").strip() != ""
        and str(payload.get("task_id") or "").strip() != ""
        and str(payload.get("trigger_source") or "").strip()
        in AUTONOMOUS_EXECUTION_ACCEPTED_TRIGGERS
        and bool(payload.get("operator_override")) is True
        and isinstance(execution_budget, Mapping)
        and _budget_positive_int(execution_budget.get("max_steps"))
        and _budget_positive_int(execution_budget.get("max_seconds"))
        and bool(payload.get("self_loop_guard")) is True
        and bool(payload.get("audit_required")) is True
    )


def build_autonomous_execution_admission_request(
    payload: Mapping[str, Any],
) -> AutonomousExecutionAdmissionRequest:
    missing = [
        field_name
        for field_name in ("request_id", "task_id", "trigger_source")
        if not str(payload.get(field_name) or "").strip()
    ]
    for required_field in (
        "operator_override",
        "execution_budget",
        "stop_condition",
        "self_loop_guard",
        "audit_required",
    ):
        if required_field not in payload:
            missing.append(required_field)

    if (
        "stop_condition" in payload
        and not str(payload.get("stop_condition") or "").strip()
        and _only_stop_condition_is_invalid(payload)
    ):
        missing.append("stop_condition")

    if missing:
        raise ValueError(
            "missing autonomous execution admission fields: " + ", ".join(missing)
        )

    execution_budget = payload.get("execution_budget")
    if not isinstance(execution_budget, Mapping):
        raise ValueError("execution_budget must be a mapping")

    return AutonomousExecutionAdmissionRequest(
        request_id=str(payload["request_id"]),
        task_id=str(payload["task_id"]),
        trigger_source=str(payload["trigger_source"]),
        operator_override=bool(payload["operator_override"]),
        execution_budget=dict(execution_budget),
        stop_condition=str(payload.get("stop_condition") or ""),
        self_loop_guard=bool(payload["self_loop_guard"]),
        audit_required=bool(payload["audit_required"]),
        metadata=dict(payload.get("metadata") or {}),
    )
