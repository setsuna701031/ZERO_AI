from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


RUNTIME_CAPABILITY_RESERVATION_SCHEMA = "zero.runtime.capability_reservation.v1"


def _stable_id(payload: Mapping[str, Any], prefix: str) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return prefix + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _source_value(authority_envelope: Mapping[str, Any], name: str, default: Any) -> Any:
    if name in authority_envelope:
        return authority_envelope.get(name)
    source_execution_envelope = authority_envelope.get("source_execution_envelope")
    if isinstance(source_execution_envelope, Mapping):
        return source_execution_envelope.get(name, default)
    return default


def _validate_authority_envelope(authority_envelope: Mapping[str, Any]) -> None:
    execution_authority = authority_envelope.get("execution_authority")
    approved = (
        execution_authority.get("approved")
        if isinstance(execution_authority, Mapping)
        else None
    )
    if approved is not True:
        raise PermissionError("runtime_capability_reservation_authority_approval_required")
    if authority_envelope.get("authority_payload_only") is not True:
        raise PermissionError("runtime_capability_reservation_payload_only_required")
    if authority_envelope.get("mutation_allowed") is not False:
        raise PermissionError("runtime_capability_reservation_mutation_must_be_false")
    if authority_envelope.get("direct_execution") is not False:
        raise PermissionError("runtime_capability_reservation_direct_execution_must_be_false")


def authority_envelope_to_capability_reservation(
    authority_envelope: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(authority_envelope, Mapping):
        raise TypeError("runtime_authority_envelope_must_be_mapping")
    _validate_authority_envelope(authority_envelope)

    package_id = str(authority_envelope.get("package_id") or "").strip()
    if not package_id:
        raise ValueError("package_id_required")

    authority_envelope_id = str(
        authority_envelope.get("authority_envelope_id")
        or _stable_id(authority_envelope, "runtime-authority-envelope-")
    )
    reservation_id = str(
        authority_envelope.get("reservation_id")
        or _stable_id(
            {
                "package_id": package_id,
                "authority_envelope_id": authority_envelope_id,
                "authority_envelope": authority_envelope,
            },
            "runtime-capability-reservation-",
        )
    )

    return {
        "schema": RUNTIME_CAPABILITY_RESERVATION_SCHEMA,
        "reservation_id": reservation_id,
        "package_id": package_id,
        "authority_envelope_id": authority_envelope_id,
        "reservation_state": "reserved",
        "runtime_owner": "RuntimeDispatcher",
        "execution_authority": {
            "approved": True,
            "scope": "execution_package",
        },
        "runtime_execution_capability": {
            "status": "reserved",
        },
        "capability_scope": {
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
        },
        "mutation_allowed": False,
        "direct_execution": False,
        "reservation_payload_only": True,
        "non_mainline_reporting_enabled": bool(
            _source_value(authority_envelope, "non_mainline_reporting_enabled", False)
        ),
        "validation_commands": copy.deepcopy(
            _source_value(authority_envelope, "validation_commands", [])
        ),
        "source_authority_envelope": copy.deepcopy(dict(authority_envelope)),
    }


__all__ = [
    "RUNTIME_CAPABILITY_RESERVATION_SCHEMA",
    "authority_envelope_to_capability_reservation",
]
