from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping, Sequence

from core.engineering.engineering_runtime_adapter_execution_integration_common import (
    canonical_fingerprint,
    canonical_json,
)
from core.engineering.repository_analysis_common import ValidationResult

SCHEMA = "zero.engineering.capability_registry.v1"
REGISTRATION_SCHEMA = "zero.engineering.capability_registration.v1"
LOOKUP_SCHEMA = "zero.engineering.capability_registry_lookup.v1"
STATUSES = frozenset({"enabled", "disabled", "blocked", "unavailable", "deprecated"})
WORKSPACE_SCOPES = frozenset({"none", "repository_relative", "workspace_relative", "admitted_workspace"})
EXECUTION_BOUNDARIES = frozenset({"engineering_runtime", "runtime_adapter", "workspace_adapter", "governed_mutation_executor"})
MAX_REGISTRATIONS = 256
MAX_OPERATIONS = 64
MAX_EVIDENCE = 16
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset({
    "schema", "registration_id", "fingerprint", "capability_id", "capability_version",
    "display_name", "owner_domain", "owner_adapter_id", "owner_adapter_fingerprint",
    "supported_operations", "read_only", "mutation_capable", "requires_operator_approval",
    "requires_mutation_authorization", "requires_adapter_activation", "requires_activation_token",
    "workspace_scope_type", "allowed_execution_boundary", "status", "deprecation_replacement",
    "registration_evidence",
})


def _text(value: Any, *, identifier: bool = False) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 128 and value == value.strip()
            and (not identifier or bool(_IDENTIFIER.fullmatch(value))))


def _absolute_path(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith(("/", "\\\\")) or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    if isinstance(value, Mapping):
        return any(_absolute_path(k) or _absolute_path(v) for k, v in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_absolute_path(item) for item in value)
    return False


def _bounded_json(value: Any, depth: int = 0) -> bool:
    if depth > 3: return False
    if value is None or isinstance(value, bool): return True
    if isinstance(value, int) and not isinstance(value, bool): return -(10 ** 12) <= value <= 10 ** 12
    if isinstance(value, str): return len(value) <= 256 and not _absolute_path(value)
    if isinstance(value, list): return len(value) <= 16 and all(_bounded_json(item, depth + 1) for item in value)
    if isinstance(value, Mapping):
        return (len(value) <= 16 and all(_text(key, identifier=True) for key in value)
                and all(_bounded_json(item, depth + 1) for item in value.values()))
    return False


def _registration_body(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value[key]) for key in sorted(_FIELDS - {"registration_id", "fingerprint"}) if key in value}


def build_capability_registration(**fields: Any) -> dict[str, Any]:
    body = {"schema": REGISTRATION_SCHEMA, **deepcopy(fields)}
    body["supported_operations"] = sorted(body.get("supported_operations", []))
    body["registration_evidence"] = sorted(body.get("registration_evidence", []), key=canonical_json)
    fingerprint = canonical_fingerprint(body)
    return {**body, "registration_id": "engineering-capability-registration-" + fingerprint[:24], "fingerprint": fingerprint}


def validate_capability_registration(value: Any) -> ValidationResult:
    if not isinstance(value, Mapping):
        return ValidationResult(False, ("registration_not_object",))
    errors: list[str] = []
    if set(value) != _FIELDS: errors.append("registration_fields_invalid")
    if value.get("schema") != REGISTRATION_SCHEMA: errors.append("registration_schema_invalid")
    for key in ("capability_id", "owner_domain", "owner_adapter_id"):
        if not _text(value.get(key), identifier=True): errors.append(key + "_invalid")
    if not _text(value.get("capability_version")) or not all(character.isalnum() or character in "._-" for character in value["capability_version"]):
        errors.append("capability_version_invalid")
    if not _text(value.get("display_name")): errors.append("display_name_invalid")
    if not isinstance(value.get("owner_adapter_fingerprint"), str) or not _FINGERPRINT.fullmatch(value["owner_adapter_fingerprint"]):
        errors.append("adapter_linkage_invalid")
    operations = value.get("supported_operations")
    if (not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS
            or operations != sorted(set(operations)) or not all(_text(item, identifier=True) for item in operations)):
        errors.append("supported_operations_invalid")
    booleans = ("read_only", "mutation_capable", "requires_operator_approval",
                "requires_mutation_authorization", "requires_adapter_activation", "requires_activation_token")
    if not all(isinstance(value.get(key), bool) for key in booleans): errors.append("governance_flags_invalid")
    if value.get("read_only") is value.get("mutation_capable"): errors.append("authority_mode_contradictory")
    if value.get("read_only") is True and value.get("requires_mutation_authorization") is True:
        errors.append("authority_requirements_contradictory")
    if value.get("mutation_capable") is True and value.get("requires_mutation_authorization") is not True:
        errors.append("mutation_authorization_required")
    if value.get("requires_activation_token") is True and value.get("requires_adapter_activation") is not True:
        errors.append("activation_token_requires_activation")
    if value.get("workspace_scope_type") not in WORKSPACE_SCOPES: errors.append("workspace_scope_invalid")
    if value.get("allowed_execution_boundary") not in EXECUTION_BOUNDARIES: errors.append("execution_boundary_invalid")
    if value.get("status") not in STATUSES: errors.append("status_invalid")
    replacement = value.get("deprecation_replacement")
    if value.get("status") == "deprecated":
        if not _text(replacement, identifier=True) or replacement == value.get("capability_id"): errors.append("deprecation_linkage_invalid")
    elif replacement is not None: errors.append("deprecation_linkage_invalid")
    evidence = value.get("registration_evidence")
    if (not isinstance(evidence, list) or not 1 <= len(evidence) <= MAX_EVIDENCE
            or evidence != sorted(evidence, key=canonical_json)
            or any(not isinstance(item, Mapping) or not item or len(item) > 8 or not _bounded_json(item) for item in evidence)
            or _absolute_path(evidence)):
        errors.append("registration_evidence_invalid")
    expected = canonical_fingerprint(_registration_body(value))
    if value.get("fingerprint") != expected or value.get("registration_id") != "engineering-capability-registration-" + expected[:24]:
        errors.append("registration_identity_invalid")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


def build_capability_registry(registrations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = sorted((deepcopy(dict(item)) for item in registrations), key=lambda item: (item.get("capability_id", ""), item.get("fingerprint", "")))
    body = {"schema": SCHEMA, "registrations": items,
            "evidence": {"authority_source": "explicit_canonical_input", "inventory_authoritative": False},
            "closure": {"status": "closed", "read_only": True, "adapter_invoked": False,
                        "execution_performed": False, "mutation_performed": False, "authority_granted": False}}
    fingerprint = canonical_fingerprint(body)
    return {**body, "registry_id": "engineering-capability-registry-" + fingerprint[:24], "fingerprint": fingerprint}


def validate_capability_registry(value: Any) -> ValidationResult:
    if not isinstance(value, Mapping): return ValidationResult(False, ("registry_not_object",))
    errors: list[str] = []
    if set(value) != {"schema", "registry_id", "fingerprint", "registrations", "evidence", "closure"}: errors.append("registry_fields_invalid")
    if value.get("schema") != SCHEMA: errors.append("registry_schema_invalid")
    items = value.get("registrations")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_REGISTRATIONS: errors.append("registrations_invalid"); items = []
    ids: list[str] = []
    operations: dict[str, list[str]] = {}
    for item in items:
        result = validate_capability_registration(item)
        errors.extend("registration:" + error for error in result.errors)
        if isinstance(item, Mapping):
            capability_id = item.get("capability_id")
            if isinstance(capability_id, str): ids.append(capability_id)
            if item.get("status") == "enabled":
                for operation in item.get("supported_operations", []) if isinstance(item.get("supported_operations"), list) else []:
                    operations.setdefault(operation, []).append(str(capability_id))
    if len(ids) != len(set(ids)): errors.append("duplicate_capability_id")
    known_ids = set(ids)
    if any(item.get("status") == "deprecated" and item.get("deprecation_replacement") not in known_ids
           for item in items if isinstance(item, Mapping)):
        errors.append("deprecation_replacement_unregistered")
    if items != sorted(items, key=lambda item: (item.get("capability_id", ""), item.get("fingerprint", ""))): errors.append("registration_order_invalid")
    evidence = value.get("evidence")
    if evidence != {"authority_source": "explicit_canonical_input", "inventory_authoritative": False}: errors.append("registry_evidence_invalid")
    closure = value.get("closure")
    expected_closure = {"status": "closed", "read_only": True, "adapter_invoked": False,
                        "execution_performed": False, "mutation_performed": False, "authority_granted": False}
    if closure != expected_closure: errors.append("registry_closure_invalid")
    body = {key: deepcopy(value.get(key)) for key in ("schema", "registrations", "evidence", "closure")}
    fingerprint = canonical_fingerprint(body)
    if value.get("fingerprint") != fingerprint or value.get("registry_id") != "engineering-capability-registry-" + fingerprint[:24]: errors.append("registry_identity_invalid")
    if _absolute_path(value): errors.append("absolute_path_prohibited")
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


def _result(status: str, *, registrations: Sequence[Mapping[str, Any]] = (), reasons: Sequence[str] = ()) -> dict[str, Any]:
    body = {"schema": LOOKUP_SCHEMA, "lookup_status": status, "registrations": list(registrations),
            "reason_codes": sorted(set(reasons)), "adapter_inferred": False, "adapter_invoked": False,
            "execution_performed": False, "mutation_performed": False, "authority_granted": False,
            "operator_approval_granted": False, "mutation_authorization_granted": False}
    body["fingerprint"] = canonical_fingerprint(body)
    return body


def lookup_capability(registry: Mapping[str, Any], capability_id: str, *, include_inactive: bool = False) -> dict[str, Any]:
    valid = validate_capability_registry(registry)
    if not valid.valid: return _result("invalid", reasons=valid.errors)
    matches = [item for item in registry["registrations"] if item["capability_id"] == capability_id]
    if not include_inactive: matches = [item for item in matches if item["status"] == "enabled"]
    return _result("found", registrations=matches) if matches else _result("unavailable", reasons=("capability_not_selectable",))


def lookup_operation(registry: Mapping[str, Any], operation: str, *, include_inactive: bool = False) -> dict[str, Any]:
    valid = validate_capability_registry(registry)
    if not valid.valid: return _result("invalid", reasons=valid.errors)
    matches = [item for item in registry["registrations"] if operation in item["supported_operations"] and (include_inactive or item["status"] == "enabled")]
    if len(matches) > 1: return _result("ambiguous", registrations=matches, reasons=("ambiguous_operation_ownership",))
    return _result("found", registrations=matches) if matches else _result("unavailable", reasons=("operation_not_registered",))


def list_capabilities(registry: Mapping[str, Any], *, enabled_only: bool = True, read_only: bool | None = None,
                      mutation_capable: bool | None = None, adapter_id: str | None = None,
                      execution_boundary: str | None = None) -> dict[str, Any]:
    valid = validate_capability_registry(registry)
    if not valid.valid: return _result("invalid", reasons=valid.errors)
    items = [item for item in registry["registrations"] if not enabled_only or item["status"] == "enabled"]
    if read_only is not None: items = [item for item in items if item["read_only"] is read_only]
    if mutation_capable is not None: items = [item for item in items if item["mutation_capable"] is mutation_capable]
    if adapter_id is not None: items = [item for item in items if item["owner_adapter_id"] == adapter_id]
    if execution_boundary is not None: items = [item for item in items if item["allowed_execution_boundary"] == execution_boundary]
    return _result("found", registrations=items)


def validate_requested_capability(registry: Mapping[str, Any], *, capability_id: str, operation: str,
                                  adapter_id: str, adapter_fingerprint: str) -> dict[str, Any]:
    selected = lookup_capability(registry, capability_id)
    if selected["lookup_status"] != "found": return selected
    registration = selected["registrations"][0]
    reasons = []
    if operation not in registration["supported_operations"]: reasons.append("operation_not_supported")
    if adapter_id != registration["owner_adapter_id"] or adapter_fingerprint != registration["owner_adapter_fingerprint"]:
        reasons.append("adapter_linkage_mismatch")
    return _result("registered", registrations=(registration,)) if not reasons else _result("unavailable", reasons=reasons)


__all__ = [name for name in globals() if name.startswith(("build_", "validate_", "lookup_", "list_"))]
