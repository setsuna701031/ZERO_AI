from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


RUNTIME_EXECUTION_AUTHORITY_TOKEN_SCHEMA = (
    "zero.runtime.execution_authority_token.v1"
)


def _stable_id(payload: Mapping[str, Any], prefix: str) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return prefix + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _validate_capability_reservation(reservation: Mapping[str, Any]) -> None:
    execution_authority = reservation.get("execution_authority")
    approved = (
        execution_authority.get("approved")
        if isinstance(execution_authority, Mapping)
        else None
    )
    runtime_execution_capability = reservation.get("runtime_execution_capability")
    capability_status = (
        runtime_execution_capability.get("status")
        if isinstance(runtime_execution_capability, Mapping)
        else None
    )
    capability_scope = reservation.get("capability_scope")
    taskrunner_required = (
        capability_scope.get("taskrunner_required")
        if isinstance(capability_scope, Mapping)
        else None
    )
    step_executor_endpoint_only = (
        capability_scope.get("step_executor_endpoint_only")
        if isinstance(capability_scope, Mapping)
        else None
    )

    if reservation.get("reservation_state") != "reserved":
        raise PermissionError("runtime_execution_authority_token_reserved_state_required")
    if approved is not True:
        raise PermissionError("runtime_execution_authority_token_approval_required")
    if reservation.get("reservation_payload_only") is not True:
        raise PermissionError("runtime_execution_authority_token_payload_only_required")
    if reservation.get("mutation_allowed") is not False:
        raise PermissionError("runtime_execution_authority_token_mutation_must_be_false")
    if reservation.get("direct_execution") is not False:
        raise PermissionError("runtime_execution_authority_token_direct_execution_must_be_false")
    if capability_status != "reserved":
        raise PermissionError("runtime_execution_authority_token_capability_reserved_required")
    if taskrunner_required is not True:
        raise PermissionError("runtime_execution_authority_token_taskrunner_required")
    if step_executor_endpoint_only is not True:
        raise PermissionError("runtime_execution_authority_token_step_executor_endpoint_only")


def capability_reservation_to_execution_authority_token(
    reservation: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(reservation, Mapping):
        raise TypeError("runtime_capability_reservation_must_be_mapping")
    _validate_capability_reservation(reservation)

    package_id = str(reservation.get("package_id") or "").strip()
    if not package_id:
        raise ValueError("package_id_required")

    reservation_id = str(reservation.get("reservation_id") or "").strip()
    if not reservation_id:
        raise ValueError("reservation_id_required")

    authority_envelope_id = str(reservation.get("authority_envelope_id") or "").strip()
    if not authority_envelope_id:
        raise ValueError("authority_envelope_id_required")

    token_id = str(
        reservation.get("execution_authority_token_id")
        or reservation.get("authority_token_id")
        or _stable_id(
            {
                "package_id": package_id,
                "reservation_id": reservation_id,
                "authority_envelope_id": authority_envelope_id,
                "reservation": reservation,
            },
            "runtime-execution-authority-token-",
        )
    )

    return {
        "schema": RUNTIME_EXECUTION_AUTHORITY_TOKEN_SCHEMA,
        "execution_authority_token_id": token_id,
        "reservation_id": reservation_id,
        "package_id": package_id,
        "authority_envelope_id": authority_envelope_id,
        "token_state": "issued",
        "runtime_owner": "RuntimeDispatcher",
        "execution_authority": {
            "approved": True,
            "scope": "execution_package",
            "tokenized": True,
        },
        "runtime_execution_capability": {
            "status": "authority_token_issued",
            "source_status": "reserved",
        },
        "capability_scope": {
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
        },
        "mutation_allowed": False,
        "direct_execution": False,
        "runtime_execution_performed": False,
        "authority_token_payload_only": True,
        "non_mainline_reporting_enabled": bool(
            reservation.get("non_mainline_reporting_enabled")
        ),
        "validation_commands": copy.deepcopy(
            reservation.get("validation_commands") or []
        ),
        "source_capability_reservation": copy.deepcopy(dict(reservation)),
    }


__all__ = [
    "RUNTIME_EXECUTION_AUTHORITY_TOKEN_SCHEMA",
    "capability_reservation_to_execution_authority_token",
]
