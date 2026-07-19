from __future__ import annotations
from typing import Any
from core.engineering.engineering_runtime_adapter_activation_authorization_common import *
SCHEMA='zero.engineering.runtime_adapter_activation_authorization_policy.v1';ID='activation_authorization_policy_id';PREFIX='engineering-runtime-adapter-activation-authorization-policy-'
REQUIREMENTS=('valid_eligible_activation_eligibility_decision','valid_closed_activation_eligibility_closure','valid_activation_eligibility_handoff','eligible_for_activation_authorization','exact_upstream_linkage','exact_adapter_identity_and_version_linkage','requested_authorized_scope_bounded_by_eligible_activation_scope','explicit_passive_authorization_constraints','bounded_resource_constraints','finite_positive_timeout_constraints','valid_passive_environment_constraints','non_transferable_authority','non_reusable_authority','scope_bound_authority','non_perpetual_authority','passive_authority','unconsumed_authority','open_authority','restricted_authority','non_unrestricted_authority','no_executable_payload','no_credential_like_payload','no_embedded_token','no_token_generation','no_adapter_loading','no_adapter_activation','no_adapter_invocation','no_runtime_invocation','no_executor_or_scheduler_invocation','invalid_input_fails_closed')
FIELDS={'requirements','frozen','deterministic','fail_closed'}
def build_default_runtime_adapter_activation_authorization_policy()->dict[str,Any]: return stable_artifact({'schema':SCHEMA,'requirements':list(REQUIREMENTS),'frozen':True,'deterministic':True,'fail_closed':True},ID,PREFIX)
def validate_runtime_adapter_activation_authorization_policy(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,id_key=ID,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
 if isinstance(v,dict):
  if v.get('requirements')!=list(REQUIREMENTS): e.append('policy_requirements_mismatch')
  if v.get('frozen') is not True or v.get('deterministic') is not True or v.get('fail_closed') is not True: e.append('policy_not_frozen')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_activation_authorization_policy(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_activation_authorization_policy(v); return {'schema':SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
