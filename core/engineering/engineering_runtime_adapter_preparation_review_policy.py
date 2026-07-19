from __future__ import annotations
from typing import Any
from core.engineering.engineering_runtime_adapter_preparation_review_common import *
SCHEMA='zero.engineering.runtime_adapter_preparation_review_policy.v1';ID='review_policy_id';PREFIX='engineering-runtime-adapter-preparation-review-policy-'
FIELDS={'requirements'}
REQ=('valid_preparation_request','valid_preparation_policy','valid_preparation_eligibility','valid_passive_invocation_descriptor','valid_preparation_decision','valid_preparation_closure','preparation_status_prepared','closure_status_closed','exact_linkage_across_all_artifacts','exact_adapter_id_version_linkage','prepared_scope_bounded_by_admitted_scope','passive_descriptor_invariants_preserved','bounded_resource_constraints','finite_timeout_constraints','valid_environment_constraints','valid_authority_constraints','no_executable_payload','no_credential_like_payload','no_terminal_or_invalid_upstream_state','no_consumed_or_closed_authority','no_runtime_invocation','no_adapter_loading_or_activation','invalid_input_fails_closed')
def build_default_runtime_adapter_preparation_review_policy()->dict[str,Any]: return stable_artifact({'schema':SCHEMA,'requirements':list(REQ)},ID,PREFIX)
def validate_runtime_adapter_preparation_review_policy(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,statuses=set(),id_key=ID,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
 if isinstance(v,Mapping) and tuple(v.get('requirements',()))!=REQ: e.append('invalid_policy_requirements')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_preparation_review_policy(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_preparation_review_policy(v); return {'schema':SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
