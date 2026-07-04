from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_autonomous_execution_admission_audit import (
    build_autonomous_execution_admission_audit_record,
)
from core.runtime.runtime_autonomous_execution_admission_contract import (
    build_autonomous_execution_admission_request,
)
from core.runtime.runtime_autonomous_execution_admission_policy import (
    evaluate_autonomous_execution_admission,
)
from core.runtime.runtime_autonomous_execution_admission_projection import (
    project_autonomous_execution_admission_review,
)


def prepare_runtime_autonomous_execution_admission_review(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    request = build_autonomous_execution_admission_request(payload)
    request_payload = request.to_dict()
    policy_result = evaluate_autonomous_execution_admission(request)
    projection = project_autonomous_execution_admission_review(
        request_payload=request_payload,
        policy_result=policy_result,
    )
    audit_record = build_autonomous_execution_admission_audit_record(
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
        "autonomous_execution_allowed": False,
        "autonomous_loop_started": False,
        "new_task_dispatched": False,
        "tool_execution_performed": False,
        "runtime_mutation_performed": False,
        "queue_mutation_performed": False,
        "external_io_performed": False,
    }


__all__ = ["prepare_runtime_autonomous_execution_admission_review"]
