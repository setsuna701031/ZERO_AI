from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.engineering_planning_common import ValidationResult

ALLOWED_CHANGE_CATEGORIES = ("compatibility_adjustment", "configuration_change", "contract_addition", "documentation_change", "source_change", "test_change")
FORBIDDEN_CHANGE_CATEGORIES = ("approval_bypass", "authorization_bypass", "executor_bypass", "frozen_contract_modification", "hidden_repository_mutation", "unauthorized_deletion", "unbounded_scope_expansion")
FORBIDDEN_PAYLOAD_KEYS = frozenset({"after", "after_content", "before", "before_content", "command", "diff", "executable_command", "file_content", "patch", "replacement_content", "shell_command", "source_content", "unified_diff"})


def proposal_boundary() -> dict[str, bool]:
    return {"sealed": True, "read_only": True, "proposal_artifact_created": True,
            "repository_modified": False, "patch_generated": False, "diff_generated": False,
            "execution_started": False, "mutation_allowed": False, "approval_granted": False,
            "authorization_granted": False, "token_issued": False, "runtime_activated": False,
            "authority_granted": False, "scope_expansion": False}


def proposal_artifact(schema: str, status: str, payload: Mapping[str, Any], id_key: str, prefix: str) -> dict[str, Any]:
    return identified({"schema": schema, "status": status, **deepcopy(dict(payload)), "boundary": proposal_boundary()}, id_key, prefix)


def contains_forbidden_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(k).lower() in FORBIDDEN_PAYLOAD_KEYS or contains_forbidden_payload(v) for k, v in value.items())
    if isinstance(value, list): return any(contains_forbidden_payload(v) for v in value)
    return False


def validate_proposal_artifact(value: Any, *, schema: str, statuses: set[str], id_key: str,
                               prefix: str, fields: set[str]) -> ValidationResult:
    if not isinstance(value, Mapping): return ValidationResult(False, ("artifact_not_object",))
    required={"schema","status",id_key,"fingerprint","boundary",*fields}; errors=[]
    errors += [f"missing:{k}" for k in sorted(required-set(value))]
    errors += [f"unexpected:{k}" for k in sorted(set(value)-required)]
    if value.get("schema")!=schema or value.get("status") not in statuses: errors.append("invalid_contract")
    if value.get("boundary")!=proposal_boundary(): errors.append("unsafe_boundary")
    if contains_forbidden_payload(value): errors.append("forbidden_payload")
    try:
        if not identity_valid(value,id_key,prefix): errors.append("identity_mismatch")
    except (TypeError,ValueError): errors.append("identity_mismatch")
    return ValidationResult(not errors,tuple(dict.fromkeys(errors)))


def stable_proposal_id(prefix: str, value: Mapping[str, Any]) -> str: return prefix+fingerprint(value)[:24]
def immutable(value: Any) -> Any: return deepcopy(value)
def stable_strings(value: Any) -> list[str]:
    if not isinstance(value,list) or any(not isinstance(x,str) or not x for x in value): raise ValueError("invalid_string_list")
    return sorted(set(value))
def scope_contained(requested: list[str], allowed: list[str], excluded: list[str]) -> bool:
    return set(requested)<=set(allowed) and not (set(requested)&set(excluded))
def closure_linkage(closure: Mapping[str,Any])->dict[str,Any]:
    return {"planning_closure_id":closure.get("planning_closure_id"),"planning_closure_fingerprint":closure.get("fingerprint"),"engineering_plan_id":closure.get("engineering_plan_id"),"engineering_plan_fingerprint":closure.get("engineering_plan_fingerprint")}

__all__=["ALLOWED_CHANGE_CATEGORIES","FORBIDDEN_CHANGE_CATEGORIES","ValidationResult","canonical_json","closure_linkage","contains_forbidden_payload","fingerprint","immutable","proposal_artifact","proposal_boundary","scope_contained","stable_proposal_id","stable_strings","validate_proposal_artifact"]
