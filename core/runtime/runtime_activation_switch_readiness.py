from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_activation_switch_readiness_audit import (
    build_activation_switch_readiness_audit_record,
)
from core.runtime.runtime_activation_switch_readiness_contract import (
    build_activation_switch_readiness_request,
)
from core.runtime.runtime_activation_switch_readiness_policy import (
    evaluate_activation_switch_readiness,
)
from core.runtime.runtime_activation_switch_readiness_projection import (
    project_activation_switch_readiness,
)


def prepare_runtime_activation_switch_readiness(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    request = build_activation_switch_readiness_request(payload)
    request_payload = request.to_dict()
    policy_result = evaluate_activation_switch_readiness(request)
    projection = project_activation_switch_readiness(
        request_payload=request_payload,
        policy_result=policy_result,
    )
    audit_record = build_activation_switch_readiness_audit_record(
        request_payload=request_payload,
        policy_result=policy_result,
        projection=projection,
    )

    return {
        "enabled": False,
        "readiness_only": True,
        "preview_only": True,
        "request": request_payload,
        "policy_result": policy_result,
        "projection": projection,
        "audit_record": audit_record,
        "activation_switch_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "real_mutation_enabled": False,
        "real_tool_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "new_task_dispatched": False,
        "external_io_performed": False,
    }


__all__ = ["prepare_runtime_activation_switch_readiness"]
