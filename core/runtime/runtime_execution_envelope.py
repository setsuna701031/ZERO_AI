from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


RUNTIME_EXECUTION_ENVELOPE_SCHEMA = "zero.runtime.execution_envelope.v1"


def _stable_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return "runtime-dispatch-contract-" + hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest()[:16]


def _validate_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("mutation_allowed") is not False:
        raise PermissionError("runtime_dispatch_contract_mutation_must_be_false")
    if contract.get("direct_execution") is not False:
        raise PermissionError("runtime_dispatch_contract_direct_execution_must_be_false")
    if contract.get("dispatch_payload_only") is not True:
        raise PermissionError("runtime_dispatch_contract_payload_only_required")


def dispatch_contract_to_execution_envelope(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, Mapping):
        raise TypeError("runtime_dispatch_contract_must_be_mapping")
    _validate_contract(contract)

    package_id = str(contract.get("package_id") or "").strip()
    if not package_id:
        raise ValueError("package_id_required")

    return {
        "schema": RUNTIME_EXECUTION_ENVELOPE_SCHEMA,
        "package_id": package_id,
        "dispatch_contract_id": str(
            contract.get("dispatch_contract_id")
            or contract.get("dispatch_request_id")
            or _stable_id(contract)
        ),
        "runtime_owner": str(contract.get("runtime_owner") or "RuntimeDispatcher"),
        "taskrunner_required": bool(contract.get("taskrunner_required")),
        "step_executor_endpoint_only": bool(contract.get("step_executor_endpoint_only")),
        "mutation_allowed": False,
        "direct_execution": False,
        "dispatch_payload_only": True,
        "validation_commands": copy.deepcopy(contract.get("validation_commands") or []),
        "non_mainline_reporting_enabled": bool(
            contract.get("non_mainline_reporting_enabled")
        ),
        "execution_authority": "pending",
        "runtime_execution_capability": "pending",
        "source_dispatch_contract": copy.deepcopy(dict(contract)),
    }


__all__ = [
    "RUNTIME_EXECUTION_ENVELOPE_SCHEMA",
    "dispatch_contract_to_execution_envelope",
]
