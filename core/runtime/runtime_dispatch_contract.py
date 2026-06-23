from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


RUNTIME_DISPATCH_CONTRACT_SCHEMA = "zero.runtime.dispatch_contract.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _stable_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return "runtime-dispatch-request-" + hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest()[:16]


def _approval(dispatch_request: Mapping[str, Any]) -> dict[str, Any]:
    direct = _mapping(dispatch_request.get("approval"))
    if direct:
        return direct
    approved_proposal = _mapping(dispatch_request.get("approved_proposal"))
    return _mapping(approved_proposal.get("approval"))


def _validate_dispatch_request(dispatch_request: Mapping[str, Any]) -> None:
    approval = _approval(dispatch_request)
    if approval.get("approved") is not True:
        raise PermissionError("runtime_dispatch_request_requires_approved_proposal")
    if dispatch_request.get("mutation_allowed") is not False:
        raise PermissionError("runtime_dispatch_request_mutation_must_be_false")
    if dispatch_request.get("direct_execution") is not False:
        raise PermissionError("runtime_dispatch_request_direct_execution_must_be_false")


def runtime_dispatch_request_to_contract(dispatch_request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(dispatch_request, Mapping):
        raise TypeError("runtime_dispatch_request_must_be_mapping")
    _validate_dispatch_request(dispatch_request)

    package_id = str(dispatch_request.get("package_id") or "").strip()
    if not package_id:
        raise ValueError("package_id_required")

    runtime_queue_item = _mapping(dispatch_request.get("runtime_queue_item"))
    runtime_queue_item.update(
        {
            "package_id": str(runtime_queue_item.get("package_id") or package_id),
            "runtime_owner": "RuntimeDispatcher",
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "mutation_allowed": False,
            "direct_execution": False,
            "dispatch_payload_only": True,
            "steps": copy.deepcopy(
                runtime_queue_item.get("steps")
                if isinstance(runtime_queue_item.get("steps"), list)
                else dispatch_request.get("executable_steps") or []
            ),
        }
    )

    return {
        "schema": RUNTIME_DISPATCH_CONTRACT_SCHEMA,
        "package_id": package_id,
        "dispatch_request_id": str(
            dispatch_request.get("dispatch_request_id") or _stable_id(dispatch_request)
        ),
        "runtime_owner": "RuntimeDispatcher",
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
        "mutation_allowed": False,
        "direct_execution": False,
        "dispatch_payload_only": True,
        "non_mainline_reporting_enabled": bool(
            dispatch_request.get("non_mainline_reporting_enabled")
        ),
        "validation_commands": copy.deepcopy(
            dispatch_request.get("validation_commands") or []
        ),
        "runtime_queue_item": runtime_queue_item,
        "source_dispatch_request": copy.deepcopy(dict(dispatch_request)),
    }


__all__ = [
    "RUNTIME_DISPATCH_CONTRACT_SCHEMA",
    "runtime_dispatch_request_to_contract",
]
