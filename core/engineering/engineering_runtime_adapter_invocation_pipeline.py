from __future__ import annotations

from collections.abc import Mapping

from .engineering_runtime_adapter_activation_handoff import validate_runtime_adapter_activation_handoff
from .engineering_runtime_capability_admission import validate_runtime_capability_admission
from .engineering_runtime_adapter_invocation_intake import build_runtime_adapter_invocation_intake, build_runtime_adapter_invocation_intake_request
from .engineering_runtime_adapter_invocation_admission import build_default_runtime_adapter_invocation_admission_policy, build_runtime_adapter_invocation_admission
from .engineering_runtime_adapter_invocation_preparation import build_default_runtime_adapter_invocation_preparation_policy, build_runtime_adapter_invocation_preparation
from .engineering_runtime_adapter_invocation_review import build_runtime_adapter_invocation_review_request, evaluate_runtime_adapter_invocation_review
from .engineering_runtime_adapter_invocation_authorization import build_default_runtime_adapter_invocation_authorization_policy, build_runtime_adapter_invocation_authorization
from .engineering_runtime_adapter_controlled_invocation import build_runtime_adapter_controlled_invocation
from .engineering_runtime_adapter_invocation_observation import build_runtime_adapter_invocation_observation
from .engineering_runtime_adapter_invocation_evidence import build_runtime_adapter_invocation_evidence
from .engineering_runtime_adapter_invocation_result import build_runtime_adapter_invocation_result
from .engineering_runtime_adapter_invocation_verification import verify_runtime_adapter_invocation_governance
from .engineering_runtime_adapter_invocation_handoff import build_runtime_adapter_invocation_handoff
from .engineering_runtime_adapter_invocation_closure import build_runtime_adapter_invocation_governance_closure

REQUIRED_INPUT = frozenset({"activation_handoff", "request_fingerprint", "workspace_id", "capability_id", "registry_id", "registry_fingerprint", "registration_id", "registration_fingerprint", "adapter_id", "adapter_fingerprint", "requested_invocation_scope", "requested_operation", "input_bindings", "expected_output_contract", "invocation_constraints", "resource_constraints", "timeout_constraints", "environment_constraints", "intake_context"})


def _linkage_errors(invocation_input, runtime_context, capability_admission):
    errors = []
    if not isinstance(invocation_input, Mapping): return ["invocation_input_invalid"]
    missing = sorted(REQUIRED_INPUT - set(invocation_input))
    if missing: errors.extend("missing_" + key for key in missing)
    context = runtime_context if isinstance(runtime_context, Mapping) else {}
    capability = capability_admission if isinstance(capability_admission, Mapping) else {}
    handoff = invocation_input.get("activation_handoff")
    if not isinstance(handoff, Mapping) or not validate_runtime_adapter_activation_handoff(handoff).valid:
        errors.append("activation_handoff_invalid")
    if validate_runtime_capability_admission(capability): errors.append("capability_admission_invalid")
    if capability.get("status") != "admitted" or capability.get("registered") is not True or capability.get("eligible") is not True:
        errors.append("capability_not_admitted")
    checks = (
        (invocation_input.get("request_fingerprint"), context.get("request_fingerprint"), "request_linkage_mismatch"),
        (invocation_input.get("workspace_id"), context.get("workspace_id"), "workspace_identity_mismatch"),
        (invocation_input.get("capability_id"), capability.get("capability_id"), "capability_linkage_mismatch"),
        (invocation_input.get("registry_id"), capability.get("registry_id"), "registry_linkage_mismatch"),
        (invocation_input.get("registry_fingerprint"), capability.get("registry_fingerprint"), "registry_fingerprint_mismatch"),
        (invocation_input.get("registration_id"), capability.get("registration_id"), "registration_linkage_mismatch"),
        (invocation_input.get("registration_fingerprint"), capability.get("registration_fingerprint"), "registration_fingerprint_mismatch"),
        (invocation_input.get("adapter_id"), capability.get("owner_adapter_id"), "adapter_linkage_mismatch"),
        (invocation_input.get("adapter_fingerprint"), capability.get("owner_adapter_fingerprint"), "adapter_fingerprint_mismatch"),
        ((invocation_input.get("requested_operation") or {}).get("operation_id"), capability.get("operation"), "operation_linkage_mismatch"),
    )
    errors.extend(code for actual, expected, code in checks if actual != expected)
    if isinstance(handoff, Mapping):
        if handoff.get("execution_session_id") != context.get("session_id"): errors.append("session_linkage_mismatch")
        if handoff.get("adapter_id") != capability.get("owner_adapter_id"): errors.append("activation_adapter_linkage_mismatch")
        if handoff.get("eligible_for_invocation_governance") is not True or handoff.get("activation_governance_completed") is not True:
            errors.append("activation_not_completed")
    return sorted(set(errors))


def orchestrate_runtime_adapter_invocation(invocation_input, runtime_context, capability_admission):
    handoff = invocation_input.get("activation_handoff") if isinstance(invocation_input, Mapping) else None
    errors = _linkage_errors(invocation_input, runtime_context, capability_admission)
    if errors:
        return {"status": "invalid", "reason_codes": errors, "artifacts": {}}
    try:
        request = build_runtime_adapter_invocation_intake_request(
            handoff, invocation_input["requested_invocation_scope"], invocation_input["requested_operation"],
            invocation_input["input_bindings"], invocation_input["expected_output_contract"],
            invocation_input["invocation_constraints"], invocation_input["resource_constraints"],
            invocation_input["timeout_constraints"], invocation_input["environment_constraints"],
            invocation_input["intake_context"])
        intake = build_runtime_adapter_invocation_intake(request, handoff)
        admission_policy = build_default_runtime_adapter_invocation_admission_policy(); admission = build_runtime_adapter_invocation_admission(intake, admission_policy)
        preparation_policy = build_default_runtime_adapter_invocation_preparation_policy(); preparation = build_runtime_adapter_invocation_preparation(admission, preparation_policy)
        review_request = build_runtime_adapter_invocation_review_request(preparation, admission, intake); review = evaluate_runtime_adapter_invocation_review(review_request, preparation, admission, intake)
        authorization_policy = build_default_runtime_adapter_invocation_authorization_policy()
        authorization_upstream = {**review, "admitted_scope": admission.get("admitted_scope"),
                                  "prepared_invocation_scope": preparation.get("prepared_invocation_scope"),
                                  "resource_constraints": preparation.get("resource_constraints"),
                                  "timeout_constraints": preparation.get("timeout_constraints"),
                                  "environment_constraints": preparation.get("environment_constraints")}
        authorization = build_runtime_adapter_invocation_authorization(authorization_upstream, authorization_policy)
        controlled = build_runtime_adapter_controlled_invocation(authorization, preparation); observation = build_runtime_adapter_invocation_observation(controlled)
        evidence = build_runtime_adapter_invocation_evidence(observation, controlled); result = build_runtime_adapter_invocation_result(controlled, observation, evidence)
        verification = verify_runtime_adapter_invocation_governance(intake, admission, preparation, review, authorization, controlled, observation, evidence, result)
        passive_handoff = build_runtime_adapter_invocation_handoff(result, verification, controlled)
        closure = build_runtime_adapter_invocation_governance_closure(request, intake, admission_policy, admission, preparation_policy, preparation, review_request, review, authorization_policy, authorization, controlled, observation, evidence, result, verification, passive_handoff)
    except Exception:
        return {"status": "invalid", "reason_codes": ["invocation_governance_invalid"], "artifacts": {}}
    artifacts = {"invocation_request": request, "invocation_intake": intake, "invocation_admission": admission,
                 "invocation_preparation": preparation, "invocation_review": review, "invocation_authorization": authorization,
                 "controlled_invocation": controlled, "invocation_observation": observation, "invocation_evidence": evidence,
                 "invocation_result": result, "passive_invocation_handoff": passive_handoff,
                 "invocation_verification": verification, "invocation_closure": closure}
    status = "completed_without_mutation" if closure.get("package_status") == "closed" else "not_closed"
    return {"status": status, "reason_codes": closure.get("reason_codes", []), "artifacts": artifacts}
