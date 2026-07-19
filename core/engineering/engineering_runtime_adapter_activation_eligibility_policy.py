from __future__ import annotations
from typing import Any
from core.engineering.engineering_runtime_adapter_activation_eligibility_common import *
SCHEMA='zero.engineering.runtime_adapter_activation_eligibility_policy.v1';ID='activation_eligibility_policy_id';PREFIX='engineering-runtime-adapter-activation-eligibility-policy-'
FIELDS={'requirements','frozen','invalid_input_fails_closed'}
REQ=('valid_approved_preparation_review','valid_closed_preparation_review_closure','valid_preparation_review_handoff','eligible_for_activation_review','exact_upstream_linkage','exact_adapter_identity_and_version_linkage','bounded_requested_activation_scope','explicit_passive_activation_constraints','bounded_resource_constraints','finite_positive_timeout_constraints','valid_passive_environment_constraints','non_transferable_authority','non_reusable_authority','scope_bound_authority','non_perpetual_authority','passive_authority','unconsumed_authority','open_authority','restricted_authority','non_unrestricted_authority','no_executable_payload','no_credential_like_payload','no_activation_authorization','no_activation_token','no_adapter_loading','no_adapter_activation','no_adapter_invocation','no_runtime_invocation','no_executor_or_scheduler_invocation','invalid_input_fails_closed')
def build_default_runtime_adapter_activation_eligibility_policy()->dict[str,Any]: return stable_artifact({'schema':SCHEMA,'requirements':list(REQ),'frozen':True,'invalid_input_fails_closed':True},ID,PREFIX)
def validate_runtime_adapter_activation_eligibility_policy(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,id_key=ID,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
 if isinstance(v,dict) and (v.get('frozen') is not True or v.get('invalid_input_fails_closed') is not True or tuple(v.get('requirements',()))!=REQ): e.append('invalid_activation_eligibility_policy')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_activation_eligibility_policy(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_activation_eligibility_policy(v); return {'schema':SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
