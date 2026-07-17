from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


RUNTIME_DISPATCH_CAPABILITY_SCHEMA = "zero.runtime.dispatch_capability.v1"
EXPECTED_AUTHORITY_CONTEXT_SCHEMA = "zero.runtime.authority_context.v1"
_RUNTIME_OWNER = "Runtime" + "Dispatcher"


def _stable_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _require_authority_context(context: dict[str, Any]) -> None:
    if not isinstance(context, dict):
        raise PermissionError("authority_context_required")

    schema = str(context.get("schema") or "")
    if schema and schema != EXPECTED_AUTHORITY_CONTEXT_SCHEMA:
        raise PermissionError("authority_context_schema_required")

    if str(context.get("authority_state") or "") != "issued":
        raise PermissionError("authority_context_issued_required")

    if context.get("authority_payload_only") is not True:
        raise PermissionError("authority_payload_only_required")

    if context.get("mutation_allowed") is not False:
        raise PermissionError("mutation_not_allowed")

    if context.get("direct_execution") is not False:
        raise PermissionError("direct_execution_not_allowed")

    capability = _as_dict(context.get("runtime_execution_capability"))
    if str(capability.get("status") or "") != "reserved":
        raise PermissionError("runtime_execution_capability_reserved_required")


def authority_context_to_dispatch_capability(context: dict[str, Any]) -> dict[str, Any]:
    _require_authority_context(context)

    source_context = copy.deepcopy(context)
    package_id = str(context.get("package_id") or "")
    authority_context_id = str(context.get("authority_context_id") or "")
    runtime_owner = str(context.get("authority_owner") or context.get("runtime_owner") or _RUNTIME_OWNER)

    capability_id = "runtime-dispatch-capability-" + _stable_fingerprint(
        {
            "package_id": package_id,
            "authority_context_id": authority_context_id,
            "runtime_owner": runtime_owner,
        }
    )[:16]

    return {
        "schema": RUNTIME_DISPATCH_CAPABILITY_SCHEMA,
        "dispatch_capability_id": capability_id,
        "package_id": package_id,
        "authority_context_id": authority_context_id,
        "runtime_owner": runtime_owner,
        "capability_state": "issued",
        "dispatch_allowed": True,
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
        "mutation_allowed": False,
        "direct_execution": False,
        "capability_payload_only": True,
        "validation_commands": _as_list(context.get("validation_commands")),
        "non_mainline_reporting_enabled": bool(context.get("non_mainline_reporting_enabled")),
        "source_authority_context": source_context,
    }