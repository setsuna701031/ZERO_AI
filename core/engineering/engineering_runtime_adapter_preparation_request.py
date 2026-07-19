from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_preparation_common import *
SCHEMA='zero.engineering.runtime_adapter_preparation_request.v1';ID='preparation_request_id';PREFIX='engineering-runtime-adapter-preparation-request-'
FIELDS={'runtime_adapter_admission_id','runtime_adapter_admission_fingerprint','runtime_adapter_admission_status','engineering_runtime_handoff_id','engineering_runtime_handoff_fingerprint','execution_session_id','execution_session_fingerprint','requested_adapter_id','requested_adapter_version','requested_operation','requested_scope','input_bindings','expected_output_contract','resource_constraints','environment_constraints','timeout_constraints','authority_reference','authority_constraints','request_input_fingerprint'}
def build_runtime_adapter_preparation_request(admission:Mapping[str,Any],handoff:Mapping[str,Any],session:Mapping[str,Any],requested_adapter_id:str,requested_adapter_version:str,requested_operation:Mapping[str,Any],requested_scope:Any,input_bindings:Mapping[str,Any],expected_output_contract:Mapping[str,Any],resource_constraints:Mapping[str,Any],environment_constraints:Mapping[str,Any],timeout_constraints:Mapping[str,Any],authority_reference:Any,authority_constraints:Mapping[str,Any])->dict[str,Any]:
 p={'schema':SCHEMA,'runtime_adapter_admission_id':admission.get('admission_id'),'runtime_adapter_admission_fingerprint':admission.get('fingerprint'),'runtime_adapter_admission_status':admission.get('admission_status'),'engineering_runtime_handoff_id':handoff.get('engineering_runtime_handoff_id'),'engineering_runtime_handoff_fingerprint':handoff.get('fingerprint'),'execution_session_id':session.get('engineering_execution_session_id'),'execution_session_fingerprint':session.get('fingerprint'),'requested_adapter_id':requested_adapter_id,'requested_adapter_version':requested_adapter_version,'requested_operation':dict(requested_operation),'requested_scope':requested_scope,'input_bindings':dict(input_bindings),'expected_output_contract':dict(expected_output_contract),'resource_constraints':dict(resource_constraints),'environment_constraints':dict(environment_constraints),'timeout_constraints':dict(timeout_constraints),'authority_reference':authority_reference,'authority_constraints':dict(authority_constraints),'request_input_fingerprint':canonical_fingerprint({'admission':admission,'handoff':handoff,'session':session,'adapter':requested_adapter_id,'version':requested_adapter_version,'operation':requested_operation,'scope':requested_scope,'input':input_bindings,'output':expected_output_contract,'resources':resource_constraints,'environment':environment_constraints,'timeout':timeout_constraints,'authority_reference':authority_reference,'authority_constraints':authority_constraints})}
 return stable_artifact(p,ID,PREFIX)
def validate_runtime_adapter_preparation_request(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,statuses=set(),id_key=ID,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
 if isinstance(v,Mapping):
  if v.get('runtime_adapter_admission_status')!='admitted': e.append('admission_not_admitted')
  if not canonical_nonempty(v.get('requested_adapter_id')): e.append('invalid_adapter_id')
  if not canonical_nonempty(v.get('requested_adapter_version')): e.append('invalid_adapter_version')
  if not operation_valid(v.get('requested_operation')): e.append('invalid_operation')
  if contains_wildcard(v.get('requested_scope')): e.append('wildcard_scope')
  for key,code,fn in (('input_bindings','invalid_input_bindings',passive_mapping),('expected_output_contract','invalid_output_contract',passive_mapping),('resource_constraints','unbounded_resources',resources_valid),('timeout_constraints','invalid_timeout',timeout_valid),('environment_constraints','invalid_environment_constraints',environment_valid)):
   if not fn(v.get(key)): e.append(code)
  if not authority_valid(v.get('authority_constraints'),v.get('requested_scope')): e.append('invalid_authority_constraints')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_preparation_request(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_preparation_request(v); return {'schema':SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
