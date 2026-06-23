from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


RUNTIME_AUTHORITY_CONTEXT_SCHEMA = "zero.runtime.authority_context.v1"
EXPECTED_AUTHORITY_TOKEN_SCHEMA = "zero.runtime.execution_authority_token.v1"
_RUNTIME_OWNER = "Runtime" + "Dispatcher"


def _stable_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _token_id(token: dict[str, Any]) -> str:
    return str(
        token.get("authority_token_id")
        or token.get("token_id")
        or token.get("execution_authority_token_id")
        or ""
    )


def _authority_state(token: dict[str, Any]) -> str:
    capability_token = _as_dict(token.get("capability_token"))
    return str(
        token.get("authority_state")
        or token.get("token_state")
        or capability_token.get("state")
        or ""
    )


def _require_authority_token(token: dict[str, Any]) -> None:
    if not isinstance(token, dict):
        raise PermissionError("authority_token_required")

    schema = str(token.get("schema") or "")
    if schema and schema != EXPECTED_AUTHORITY_TOKEN_SCHEMA:
        raise PermissionError("execution_authority_token_schema_required")

    if _authority_state(token) != "issued":
        raise PermissionError("authority_token_issued_required")

    if token.get("authority_payload_only") is not True:
        raise PermissionError("authority_payload_only_required")

    if token.get("mutation_allowed") is not False:
        raise PermissionError("mutation_not_allowed")

    if token.get("direct_execution") is not False:
        raise PermissionError("direct_execution_not_allowed")

    execution_authority = _as_dict(token.get("execution_authority"))
    if execution_authority.get("approved") is not True:
        raise PermissionError("execution_authority_approval_required")


def execution_authority_token_to_context(token: dict[str, Any]) -> dict[str, Any]:
    _require_authority_token(token)

    source_token = copy.deepcopy(token)
    execution_authority = _as_dict(token.get("execution_authority"))
    runtime_execution_capability = _as_dict(token.get("runtime_execution_capability"))

    authority_token_id = _token_id(token)
    package_id = str(token.get("package_id") or "")
    authority_owner = str(
        token.get("runtime_owner")
        or execution_authority.get("owner")
        or _RUNTIME_OWNER
    )
    authority_scope = str(execution_authority.get("scope") or "execution_package")

    context_id = "runtime-authority-context-" + _stable_fingerprint(
        {
            "package_id": package_id,
            "authority_token_id": authority_token_id,
            "authority_owner": authority_owner,
            "authority_scope": authority_scope,
        }
    )[:16]

    return {
        "schema": RUNTIME_AUTHORITY_CONTEXT_SCHEMA,
        "authority_context_id": context_id,
        "package_id": package_id,
        "authority_owner": authority_owner,
        "authority_scope": authority_scope,
        "authority_token_id": authority_token_id,
        "authority_state": "issued",
        "execution_authority": copy.deepcopy(execution_authority),
        "runtime_execution_capability": copy.deepcopy(runtime_execution_capability),
        "mutation_allowed": False,
        "direct_execution": False,
        "authority_payload_only": True,
        "validation_commands": _as_list(token.get("validation_commands")),
        "non_mainline_reporting_enabled": bool(
            token.get("non_mainline_reporting_enabled")
        ),
        "source_authority_token": source_token,
    }