from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


RUNTIME_AUTHORITY_ENVELOPE_SCHEMA = "zero.runtime.authority_envelope.v1"


def _stable_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return "runtime-execution-envelope-" + hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest()[:16]


def _validate_envelope(envelope: Mapping[str, Any]) -> None:
    if envelope.get("mutation_allowed") is not False:
        raise PermissionError("runtime_execution_envelope_mutation_must_be_false")
    if envelope.get("direct_execution") is not False:
        raise PermissionError("runtime_execution_envelope_direct_execution_must_be_false")
    if envelope.get("dispatch_payload_only") is not True:
        raise PermissionError("runtime_execution_envelope_payload_only_required")


def execution_envelope_to_authority_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(envelope, Mapping):
        raise TypeError("runtime_execution_envelope_must_be_mapping")
    _validate_envelope(envelope)

    package_id = str(envelope.get("package_id") or "").strip()
    if not package_id:
        raise ValueError("package_id_required")

    dispatch_contract_id = str(envelope.get("dispatch_contract_id") or "").strip()
    if not dispatch_contract_id:
        raise ValueError("dispatch_contract_id_required")

    return {
        "schema": RUNTIME_AUTHORITY_ENVELOPE_SCHEMA,
        "package_id": package_id,
        "dispatch_contract_id": dispatch_contract_id,
        "execution_envelope_id": str(
            envelope.get("execution_envelope_id") or _stable_id(envelope)
        ),
        "authority_state": "pending",
        "execution_authority": {
            "owner": "RuntimeDispatcher",
            "scope": "execution_package",
            "approved": True,
        },
        "runtime_execution_capability": {
            "status": "reserved",
        },
        "mutation_allowed": False,
        "direct_execution": False,
        "authority_payload_only": True,
        "source_execution_envelope": copy.deepcopy(dict(envelope)),
    }


__all__ = [
    "RUNTIME_AUTHORITY_ENVELOPE_SCHEMA",
    "execution_envelope_to_authority_envelope",
]
