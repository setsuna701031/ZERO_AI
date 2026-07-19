from __future__ import annotations
from typing import Any
from core.engineering.engineering_runtime_adapter_preparation_common import *
SCHEMA='zero.engineering.runtime_adapter_preparation_policy.v1';ID='preparation_policy_id';PREFIX='engineering-runtime-adapter-preparation-policy-'
FIELDS={'requirements'}
REQ=('valid_admitted_runtime_adapter_admission','exact_upstream_linkage','exact_adapter_identity_and_version_linkage','bounded_requested_scope','canonical_declarative_operation','passive_input_bindings_only','explicit_expected_output_contract','bounded_resource_constraints','finite_timeout_constraints','explicit_environment_constraints','non_transferable_authority','non_reusable_authority','scope_bound_authority','non_perpetual_authority','passive_authority','unconsumed_authority','open_authority','restricted_authority','no_executable_payload','no_credential_like_payload','no_runtime_invocation','no_adapter_loading','no_dynamic_execution','invalid_input_fails_closed')
def build_default_runtime_adapter_preparation_policy()->dict[str,Any]: return stable_artifact({'schema':SCHEMA,'requirements':list(REQ)},ID,PREFIX)
def validate_runtime_adapter_preparation_policy(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,statuses=set(),id_key=ID,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
 if isinstance(v,Mapping) and tuple(v.get('requirements',()))!=REQ: e.append('invalid_policy_requirements')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_preparation_policy(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_preparation_policy(v); return {'schema':SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
