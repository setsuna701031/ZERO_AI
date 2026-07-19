from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_activation_eligibility_common import *
from core.engineering.engineering_runtime_adapter_activation_eligibility_request import validate_runtime_adapter_activation_eligibility_request
SCHEMA='zero.engineering.runtime_adapter_activation_constraint_profile.v1';ID='activation_constraint_profile_id';PREFIX='engineering-runtime-adapter-activation-constraint-profile-'
FIELDS={'activation_eligibility_request_id','activation_eligibility_request_fingerprint','preparation_review_handoff_id','preparation_review_handoff_fingerprint','adapter_id','adapter_version','approved_scope','requested_activation_scope','activation_constraints','resource_constraints','timeout_constraints','environment_constraints','authority_constraints','scope_valid','resources_valid','timeout_valid','environment_valid','authority_valid','passive_only','executable','activation_authorized','activation_token_issued','adapter_loaded','adapter_activated','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed'}
def build_runtime_adapter_activation_constraint_profile(request:Mapping[str,Any])->dict[str,Any]:
 return stable_artifact({'schema':SCHEMA,'activation_eligibility_request_id':request.get('activation_eligibility_request_id'),'activation_eligibility_request_fingerprint':request.get('fingerprint'),'preparation_review_handoff_id':request.get('preparation_review_handoff_id'),'preparation_review_handoff_fingerprint':request.get('preparation_review_handoff_fingerprint'),'adapter_id':request.get('adapter_id'),'adapter_version':request.get('adapter_version'),'approved_scope':request.get('approved_scope'),'requested_activation_scope':request.get('requested_activation_scope'),'activation_constraints':request.get('activation_constraints'),'resource_constraints':request.get('resource_constraints'),'timeout_constraints':request.get('timeout_constraints'),'environment_constraints':request.get('environment_constraints'),'authority_constraints':request.get('authority_constraints'),'scope_valid':scope_bounded(request.get('requested_activation_scope'),request.get('approved_scope')),'resources_valid':resources_valid(request.get('resource_constraints')),'timeout_valid':timeout_valid(request.get('timeout_constraints')),'environment_valid':environment_valid(request.get('environment_constraints')),'authority_valid':authority_valid(request.get('authority_constraints'),request.get('approved_scope')),'passive_only':True,'executable':False,'activation_authorized':False,'activation_token_issued':False,'adapter_loaded':False,'adapter_activated':False,'adapter_invoked':False,'runtime_invoked':False,'executor_invoked':False,'scheduler_invoked':False,'authority_consumed':False,'mutation_performed':False},ID,PREFIX)
def validate_runtime_adapter_activation_constraint_profile(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,id_key=ID,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
 if isinstance(v,Mapping):
  if not v.get('scope_valid'): e.append('scope_expansion')
  if not v.get('resources_valid'): e.append('unbounded_resources')
  if not v.get('timeout_valid'): e.append('invalid_timeout')
  if not v.get('environment_valid'): e.append('invalid_environment_constraints')
  if not v.get('authority_valid'): e.append('unbounded_authority')
  if v.get('executable') is not False or not passive_invariants_valid(v): e.append('passive_invariant_violation')
  if not activation_constraints_valid(v.get('activation_constraints')): e.append('invalid_activation_constraints')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_activation_constraint_profile(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_activation_constraint_profile(v); return {'schema':SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
