from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_real_tool_execution_admission_contract import (
    REAL_TOOL_EXECUTION_ADMISSION_CONTRACT_VERSION,
    REAL_TOOL_EXECUTION_ACCEPTED_AUTHORITIES,
    REAL_TOOL_EXECUTION_ALLOWED_CAPABILITY_SCOPES,
    REAL_TOOL_EXECUTION_ALLOWED_SIDE_EFFECT_CLASSES,
    REAL_TOOL_EXECUTION_FORBIDDEN_EFFECTS,
    RealToolExecutionAdmissionRequest,
)

REAL_TOOL_EXECUTION_ADMISSION_POLICY_VERSION = (
    "runtime.real_tool_execution_admission.policy.v1.review"
)


def evaluate_real_tool_execution_admission(
    request: RealToolExecutionAdmissionRequest | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(request, RealToolExecutionAdmissionRequest):
        payload = request.to_dict()
    else:
        payload = dict(request)

    tool_name = str(payload.get("tool_name") or "").strip()
    capability_scope = str(payload.get("capability_scope") or "").strip()
    side_effect_class = str(payload.get("side_effect_class") or "").strip()
    executor_authority = str(payload.get("executor_authority") or "").strip()
    audit_required = bool(payload.get("audit_required"))

    blockers: list[str] = []
    if not tool_name:
        blockers.append("missing_tool_name")
    if capability_scope not in REAL_TOOL_EXECUTION_ALLOWED_CAPABILITY_SCOPES:
        blockers.append("unknown_capability_scope")
    if side_effect_class not in REAL_TOOL_EXECUTION_ALLOWED_SIDE_EFFECT_CLASSES:
        blockers.append("unknown_side_effect_class")
    if executor_authority not in REAL_TOOL_EXECUTION_ACCEPTED_AUTHORITIES:
        blockers.append("untrusted_executor_authority")
    if not audit_required:
        blockers.append("audit_not_required")

    if side_effect_class == "runtime_admitted" and capability_scope != "runtime_mutation_admitted":
        blockers.append("runtime_side_effect_without_runtime_mutation_admission")

    admission_ready_preview = not blockers

    return {
        "contract_version": REAL_TOOL_EXECUTION_ADMISSION_CONTRACT_VERSION,
        "policy_version": REAL_TOOL_EXECUTION_ADMISSION_POLICY_VERSION,
        "enabled": False,
        "review_only": True,
        "preview_only": True,
        "real_tool_execution_admission_ready_preview": admission_ready_preview,
        "real_tool_execution_allowed": False,
        "tool_invocation_allowed": False,
        "tool_side_effect_allowed": False,
        "runtime_mutation_allowed": False,
        "queue_mutation_allowed": False,
        "external_io_allowed": False,
        "autonomous_execution_allowed": False,
        "blockers": blockers,
        "forbidden_effects": list(REAL_TOOL_EXECUTION_FORBIDDEN_EFFECTS),
        "reason": "real_tool_execution_admission_reserved_for_future_activation",
    }
