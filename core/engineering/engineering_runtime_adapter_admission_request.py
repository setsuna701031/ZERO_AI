from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_admission_common import *
SCHEMA='zero.engineering.runtime_adapter_admission_request.v1';ID='request_id';PREFIX='engineering-runtime-adapter-admission-request-'
FIELDS={'engineering_runtime_handoff_id','engineering_runtime_handoff_fingerprint','execution_session_id','execution_session_fingerprint','governed_execution_admission_id','governed_execution_admission_fingerprint','requested_adapter_id','requested_adapter_version','requested_scope','authority_reference','authority_constraints','input_fingerprint'}
def build_runtime_adapter_admission_request(handoff:Mapping[str,Any],session:Mapping[str,Any],admission:Mapping[str,Any],requested_adapter_id:str,requested_adapter_version:str,requested_scope:Any,authority_reference:Any,authority_constraints:Mapping[str,Any])->dict[str,Any]:
 p={'schema':SCHEMA,'engineering_runtime_handoff_id':handoff.get('engineering_runtime_handoff_id'),'engineering_runtime_handoff_fingerprint':handoff.get('fingerprint'),'execution_session_id':session.get('engineering_execution_session_id'),'execution_session_fingerprint':session.get('fingerprint'),'governed_execution_admission_id':admission.get('engineering_execution_admission_id'),'governed_execution_admission_fingerprint':admission.get('fingerprint'),'requested_adapter_id':requested_adapter_id,'requested_adapter_version':requested_adapter_version,'requested_scope':requested_scope,'authority_reference':authority_reference,'authority_constraints':dict(authority_constraints),'input_fingerprint':canonical_fingerprint({'handoff':handoff,'session':session,'admission':admission,'adapter':requested_adapter_id,'version':requested_adapter_version,'scope':requested_scope,'authority_reference':authority_reference,'authority_constraints':authority_constraints}),'boundary':boundary()}
 return stable_artifact(p,ID,PREFIX)
def validate_runtime_adapter_admission_request(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,statuses=set(),id_key=ID,prefix=PREFIX,fields=FIELDS)
 e=list(r.errors)
 if isinstance(v,Mapping):
  if not canonical_nonempty(v.get('requested_adapter_id')): e.append('invalid_adapter_id')
  if not canonical_nonempty(v.get('requested_adapter_version')): e.append('invalid_adapter_version')
  if not authority_valid(v.get('authority_constraints'),v.get('requested_scope')): e.append('invalid_authority_constraints')
  if contains_wildcard(v.get('requested_scope')): e.append('scope_not_bounded')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_admission_request(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_admission_request(v); return {'schema':SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
