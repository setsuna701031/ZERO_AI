from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_real_tool_execution_admission_audit import (
    build_real_tool_execution_admission_audit_record,
)
from core.runtime.runtime_real_tool_execution_admission_contract import (
    build_real_tool_execution_admission_request,
)
from core.runtime.runtime_real_tool_execution_admission_policy import (
    evaluate_real_tool_execution_admission,
)
from core.runtime.runtime_real_tool_execution_admission_projection import (
    project_real_tool_execution_admission_review,
)


def prepare_runtime_real_tool_execution_admission_review(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    request = build_real_tool_execution_admission_request(payload)
    request_payload = request.to_dict()
    policy_result = evaluate_real_tool_execution_admission(request)
    projection = project_real_tool_execution_admission_review(
        request_payload=request_payload,
        policy_result=policy_result,
    )
    audit_record = build_real_tool_execution_admission_audit_record(
        request_payload=request_payload,
        policy_result=policy_result,
        projection=projection,
    )

    return {
        "enabled": False,
        "review_only": True,
        "preview_only": True,
        "request": request_payload,
        "policy_result": policy_result,
        "projection": projection,
        "audit_record": audit_record,
        "real_tool_execution_allowed": False,
        "tool_invocation_performed": False,
        "tool_side_effect_performed": False,
        "runtime_mutation_performed": False,
        "queue_mutation_performed": False,
        "external_io_performed": False,
        "autonomous_execution_performed": False,
    }


__all__ = ["prepare_runtime_real_tool_execution_admission_review"]
