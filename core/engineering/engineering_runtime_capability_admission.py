from __future__ import annotations

import re
from typing import Any, Mapping

from .engineering_capability_registry import validate_capability_registry
from .engineering_runtime_orchestrator_common import fingerprint, reasons

SCHEMA = "zero.engineering.runtime_capability_admission.v1"
STATUSES = frozenset({"admitted", "not_registered", "inactive", "deprecated", "ambiguous",
                      "adapter_mismatch", "operation_unsupported", "invalid_registry",
                      "invalid_request", "blocked"})
GOVERNANCE_FIELDS = ("read_only", "mutation_capable", "requires_operator_approval",
                     "requires_mutation_authorization", "requires_adapter_activation",
                     "requires_activation_token", "workspace_scope_type", "allowed_execution_boundary")
BOUNDARIES = frozenset({"engineering_runtime", "runtime_adapter", "workspace_adapter", "governed_mutation_executor"})


def _artifact(body: Mapping[str, Any]) -> dict[str, Any]:
    value = {"schema": SCHEMA, **dict(body)}
    value["fingerprint"] = fingerprint(value)
    value["capability_admission_id"] = "engineering-capability-admission-" + value["fingerprint"][:24]
    return value


def _base(session: Mapping[str, Any], request: Mapping[str, Any], registry: Any, capability_id: Any,
          operation: Any, adapter_id: Any, adapter_fingerprint: Any) -> dict[str, Any]:
    registry_mapping = registry if isinstance(registry, Mapping) else {}
    return {"session_id": session.get("session_id"), "request_fingerprint": request.get("fingerprint"),
            "registry_id": registry_mapping.get("registry_id"), "registry_fingerprint": registry_mapping.get("fingerprint"),
            "capability_id": capability_id, "operation": operation, "requested_adapter_id": adapter_id,
            "requested_adapter_fingerprint": adapter_fingerprint, "registration_id": None,
            "registration_fingerprint": None, "owner_adapter_id": None, "owner_adapter_fingerprint": None,
            "governance_requirements": {}, "registered": False, "eligible": False, "ambiguous": False,
            "adapter_selected": False, "adapter_invoked": False, "activation_performed": False,
            "token_consumed": False, "workspace_accessed": False, "mutation_performed": False,
            "approval_granted": False, "authorization_granted": False}


def build_runtime_capability_admission(*, session: Mapping[str, Any], request: Mapping[str, Any],
                                       capability_registry: Any, requested_capability_id: Any,
                                       requested_operation: Any, requested_adapter_id: Any,
                                       requested_adapter_fingerprint: Any,
                                       prior_admission: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body = _base(session, request, capability_registry, requested_capability_id, requested_operation,
                 requested_adapter_id, requested_adapter_fingerprint)
    findings: list[str] = []
    text_inputs = (requested_capability_id, requested_operation, requested_adapter_id)
    fingerprint_valid = isinstance(requested_adapter_fingerprint, str) and bool(re.fullmatch(r"[0-9a-f]{64}", requested_adapter_fingerprint))
    if not all(isinstance(item, str) and item and len(item) <= 128 for item in text_inputs) or not fingerprint_valid:
        status = "invalid_request"; findings.append("capability_request_incomplete")
    else:
        validation = validate_capability_registry(capability_registry)
        if not validation.valid:
            status = "invalid_registry"; findings.extend("registry:" + item for item in validation.errors)
        else:
            registrations = capability_registry["registrations"]
            operation_owners = [item for item in registrations if item["status"] == "enabled" and requested_operation in item["supported_operations"]]
            selected = [item for item in registrations if item["capability_id"] == requested_capability_id]
            if len(operation_owners) > 1:
                status = "ambiguous"; findings.append("ambiguous_operation_ownership"); body["ambiguous"] = True
            elif not selected:
                status = "not_registered"; findings.append("capability_not_registered")
            else:
                registration = selected[0]
                body.update(registration_id=registration["registration_id"], registration_fingerprint=registration["fingerprint"],
                            owner_adapter_id=registration["owner_adapter_id"], owner_adapter_fingerprint=registration["owner_adapter_fingerprint"],
                            governance_requirements={key: registration[key] for key in GOVERNANCE_FIELDS}, registered=True)
                if registration["status"] == "deprecated": status = "deprecated"; findings.append("capability_deprecated")
                elif registration["status"] != "enabled": status = "inactive"; findings.append("capability_" + registration["status"])
                elif requested_operation not in registration["supported_operations"]:
                    status = "operation_unsupported"; findings.append("operation_unsupported")
                elif requested_adapter_id != registration["owner_adapter_id"] or requested_adapter_fingerprint != registration["owner_adapter_fingerprint"]:
                    status = "adapter_mismatch"; findings.append("adapter_identity_mismatch")
                elif registration["allowed_execution_boundary"] not in BOUNDARIES:
                    status = "blocked"; findings.append("execution_boundary_incompatible")
                elif registration["workspace_scope_type"] == "none" and request.get("scope_constraints"):
                    status = "blocked"; findings.append("workspace_scope_incompatible")
                else:
                    status = "admitted"; body["eligible"] = True
    if prior_admission:
        links = ("session_id", "request_fingerprint", "registry_fingerprint", "registration_fingerprint",
                 "capability_id", "operation", "requested_adapter_id", "requested_adapter_fingerprint")
        if validate_runtime_capability_admission(prior_admission):
            status = "blocked"; body["eligible"] = False; findings.append("prior_capability_admission_invalid")
        elif any(prior_admission.get(key) != body.get(key) for key in links):
            status = "blocked"; body["eligible"] = False; findings.append("capability_admission_resume_mismatch")
    body.update(status=status, findings=reasons(findings))
    return _artifact(body)


def validate_runtime_capability_admission(value: Any) -> list[str]:
    if not isinstance(value, Mapping): return ["capability_admission_invalid"]
    errors = []
    if value.get("schema") != SCHEMA or value.get("status") not in STATUSES: errors.append("capability_admission_schema_invalid")
    base = {key: item for key, item in value.items() if key not in ("fingerprint", "capability_admission_id")}
    expected = fingerprint(base)
    if value.get("fingerprint") != expected or value.get("capability_admission_id") != "engineering-capability-admission-" + expected[:24]:
        errors.append("capability_admission_identity_invalid")
    if value.get("status") == "admitted" and (value.get("eligible") is not True or value.get("registered") is not True):
        errors.append("capability_admission_state_invalid")
    passive = ("adapter_selected", "adapter_invoked", "activation_performed", "token_consumed", "workspace_accessed",
               "mutation_performed", "approval_granted", "authorization_granted")
    if any(value.get(key) is not False for key in passive): errors.append("capability_admission_passive_invariant_failed")
    return reasons(errors)


__all__ = ["build_runtime_capability_admission", "validate_runtime_capability_admission", "SCHEMA"]
