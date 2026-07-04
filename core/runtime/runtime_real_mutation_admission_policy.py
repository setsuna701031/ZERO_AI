from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_real_mutation_admission_contract import (
    REAL_MUTATION_ADMISSION_CONTRACT_VERSION,
    REAL_MUTATION_ALLOWED_SCOPES,
    REAL_MUTATION_ALLOWED_TYPES,
    REAL_MUTATION_FORBIDDEN_EFFECTS,
    RuntimeRealMutationAdmissionRequest,
)

REAL_MUTATION_ADMISSION_POLICY_VERSION = "runtime.real_mutation_admission.policy.v1.review"

_ACCEPTED_AUTHORITY_SOURCES = frozenset(
    {
        "runtime_activation_gate",
        "operator_explicit_approval",
        "sealed_test_authority",
    }
)


def evaluate_real_mutation_admission(
    request: RuntimeRealMutationAdmissionRequest | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(request, RuntimeRealMutationAdmissionRequest):
        payload = request.to_dict()
    else:
        payload = dict(request)

    mutation_type = str(payload.get("mutation_type") or "").strip()
    target_scope = str(payload.get("target_scope") or "").strip()
    authority_source = str(payload.get("authority_source") or "").strip()
    audit_required = bool(payload.get("audit_required"))

    blockers: list[str] = []
    if mutation_type not in REAL_MUTATION_ALLOWED_TYPES:
        blockers.append("unknown_mutation_type")
    if target_scope not in REAL_MUTATION_ALLOWED_SCOPES:
        blockers.append("unknown_target_scope")
    if authority_source not in _ACCEPTED_AUTHORITY_SOURCES:
        blockers.append("untrusted_authority_source")
    if not audit_required:
        blockers.append("audit_not_required")

    admission_ready_preview = not blockers

    return {
        "contract_version": REAL_MUTATION_ADMISSION_CONTRACT_VERSION,
        "policy_version": REAL_MUTATION_ADMISSION_POLICY_VERSION,
        "enabled": False,
        "review_only": True,
        "preview_only": True,
        "real_mutation_admission_ready_preview": admission_ready_preview,
        "real_mutation_allowed": False,
        "runtime_state_mutation_allowed": False,
        "queue_mutation_allowed": False,
        "task_lifecycle_mutation_allowed": False,
        "result_store_mutation_allowed": False,
        "tool_execution_allowed": False,
        "autonomous_execution_allowed": False,
        "blockers": blockers,
        "forbidden_effects": list(REAL_MUTATION_FORBIDDEN_EFFECTS),
        "reason": "real_mutation_admission_reserved_for_future_activation",
    }
