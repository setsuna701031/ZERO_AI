from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_gate_audit import (
    build_controlled_activation_gate_audit_record,
)
from core.runtime.runtime_controlled_activation_gate_contract import (
    build_controlled_activation_gate_review_request,
)
from core.runtime.runtime_controlled_activation_gate_policy import (
    evaluate_controlled_activation_gate,
)
from core.runtime.runtime_controlled_activation_gate_projection import (
    project_controlled_activation_gate_review,
)


def prepare_controlled_activation_gate_review(payload: Mapping[str, Any]) -> dict[str, Any]:
    request = build_controlled_activation_gate_review_request(payload)
    request_payload = request.to_dict()
    policy_result = evaluate_controlled_activation_gate(request)
    projection = project_controlled_activation_gate_review(
        request_payload=request_payload,
        policy_result=policy_result,
    )
    audit_record = build_controlled_activation_gate_audit_record(
        request_payload=request_payload,
        policy_result=policy_result,
        projection=projection,
    )

    return {
        "enabled": False,
        "gate_review_only": True,
        "preview_only": True,
        "request": request_payload,
        "policy_result": policy_result,
        "projection": projection,
        "audit_record": audit_record,
        "controlled_activation_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "real_mutation_enabled": False,
        "real_tool_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "new_task_dispatched": False,
        "tool_invoked": False,
        "external_io_performed": False,
    }


__all__ = ["prepare_controlled_activation_gate_review"]
