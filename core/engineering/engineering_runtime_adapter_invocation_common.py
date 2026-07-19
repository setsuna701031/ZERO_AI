from __future__ import annotations
from copy import deepcopy
from math import isfinite
from typing import Any, Mapping, Sequence
from core.engineering.engineering_intake_common import fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult
PROHIBITED_KEYS=frozenset('command command_line shell shell_command script source_code bytecode executable binary patch diff process subprocess callable callback function module_path import_path entrypoint runtime_entrypoint adapter_entrypoint invocation_callback execution_callback raw_arguments token_value raw_token bearer_token token_secret credentials password private_key secret_key bearer access_token refresh_token api_key authorization_header environment_secrets'.split())
IDENTITY_ONLY=frozenset('invocation_id invocation_intake_request_id invocation_intake_id invocation_admission_id invocation_preparation_id invocation_review_request_id invocation_review_id invocation_authorization_id controlled_invocation_id activation_handoff_id activation_result_id activation_verification_id controlled_activation_id token_consumption_id token_id activation_authorization_id adapter_id execution_session_id invocation_descriptor_id authority_reference invocation_observation_id invocation_evidence_id invocation_result_id invocation_verification_id invocation_handoff_id observation_id evidence_id result_id'.split())
PROHIBITED_STRINGS=('bearer ','-----begin','private key','password=','secret=','api_key=','access_token=','refresh_token=','authorization:','#!/','&&',';','|','`','$(','def ','lambda ','import ')
WILDCARDS=frozenset({'*','all','global','unrestricted','any','everything','repository','repository-wide','system','system-wide','unbounded'})
FALSE_FIELDS=('adapter_loaded','adapter_code_executed','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','external_effect_performed','authority_consumed','mutation_performed','real_execution_performed','real_execution_authorized')
def is_sequence(v:Any)->bool: return isinstance(v,Sequence) and not isinstance(v,(str,bytes,bytearray))
def canonical_fingerprint(v:Any)->str:
 try: return fingerprint(v)
 except (TypeError,ValueError,OverflowError): return fingerprint({'malformed':True})
def stable_artifact(base:Mapping[str,Any], id_key:str, prefix:str)->dict[str,Any]:
 body=deepcopy(dict(base)); body.pop(id_key, None); body.pop('fingerprint', None); return identified(body,id_key,prefix)
def valid_identity(v:Any,id_key:str,prefix:str)->bool:
 try: return isinstance(v,Mapping) and identity_valid(v,id_key,prefix)
 except (TypeError,ValueError): return False
def canonical_nonempty(s:Any)->bool: return isinstance(s,str) and s.strip()==s and bool(s) and s.lower() not in WILDCARDS and all(c.isalnum() or c in '._:-' for c in s)
def contains_prohibited(v:Any)->bool:
 if callable(v) or isinstance(v,(bytes,bytearray,set,tuple)): return True
 if isinstance(v,float) and not isfinite(v): return True
 if isinstance(v,Mapping):
  for k,x in v.items():
   key=str(k).lower()
   if key in PROHIBITED_KEYS and key not in IDENTITY_ONLY and not (isinstance(x,bool) and x is False): return True
   if contains_prohibited(x): return True
  return False
 if is_sequence(v): return any(contains_prohibited(x) for x in v)
 if isinstance(v,str): return any(p in v.lower() for p in PROHIBITED_STRINGS)
 return not (v is None or isinstance(v,(str,bool,int,float)))
def contains_wildcard(v:Any)->bool:
 if isinstance(v,str): return v.lower() in WILDCARDS
 if isinstance(v,Mapping): return any(str(k).lower() in WILDCARDS or contains_wildcard(x) for k,x in v.items())
 if is_sequence(v): return any(contains_wildcard(x) for x in v)
 return False
def scope_bounded(child:Any,parent:Any)->bool:
 if contains_wildcard(child) or contains_wildcard(parent): return False
 if isinstance(parent,Mapping) and isinstance(child,Mapping): return bool(child) and all(k in parent and scope_bounded(v,parent[k]) for k,v in child.items())
 if isinstance(parent,list) and isinstance(child,list): return bool(child) and all(v in parent for v in child)
 return child==parent
def normalize_reasons(rs:Any)->list[str]: return sorted({r for r in (rs or []) if canonical_nonempty(r)})
def validate_artifact(value:Any,*,schema:str,id_key:str,prefix:str,fields:set[str],status_key:str|None=None,statuses:set[str]|None=None)->ValidationResult:
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_object',))
 req={'schema',id_key,'fingerprint',*fields};
 if status_key: req.add(status_key)
 e=[f'missing:{k}' for k in sorted(req-set(value))]
 if value.get('schema')!=schema: e.append('invalid_schema')
 if status_key and statuses and value.get(status_key) not in statuses: e.append('invalid_status')
 if contains_prohibited(value): e.append('prohibited_payload')
 if not valid_identity(value,id_key,prefix): e.append('identity_mismatch')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_result(valid:bool, reasons:Any)->dict[str,Any]: return {'valid':bool(valid),'reason_codes':normalize_reasons(reasons)}
def passive_false(v:Mapping[str,Any])->bool: return all(v.get(k) is False for k in FALSE_FIELDS if k in v)
def passive_payload(v:Any)->bool: return isinstance(v,Mapping) and not contains_prohibited(v)
def operation_valid(v:Any)->bool: return isinstance(v,Mapping) and canonical_nonempty(v.get('operation_id')) and v.get('declarative') is True and not contains_prohibited(v)
def output_contract_valid(v:Any)->bool: return isinstance(v,Mapping) and canonical_nonempty(v.get('contract_id')) and bool(v.get('outputs')) and not contains_prohibited(v)
def resource_constraints_valid(v:Any)->bool: return isinstance(v,Mapping) and bool(v) and not contains_prohibited(v) and all(isinstance(x,(int,float)) and isfinite(x) and x>0 for x in v.values() if isinstance(x,(int,float))) and 'unbounded' not in v
def timeout_constraints_valid(v:Any)->bool: return isinstance(v,Mapping) and bool(v) and not contains_prohibited(v) and all(isinstance(x,(int,float)) and isfinite(x) and x>0 for x in v.values())
def authority_valid(v:Any,scope:Any)->bool: return isinstance(v,Mapping) and v.get('valid') is True and v.get('consumed') is False and v.get('passive') is True and not contains_prohibited(v) and ('scope' not in v or scope_bounded(v['scope'],scope))
def validate_common_invocation(v:Mapping[str,Any])->list[str]:
 e=[]
 scope=v.get('requested_invocation_scope',v.get('admitted_scope',v.get('prepared_invocation_scope',v.get('review_scope',v.get('authorized_invocation_scope',v.get('invoked_scope',v.get('observed_scope',v.get('evidenced_scope',v.get('invocation_scope',v.get('verified_scope'))))))))))
 parent=v.get('activated_scope',scope)
 if scope is not None and not scope_bounded(scope,parent): e.append('scope_not_bounded')
 if ('requested_operation' in v or 'operation' in v) and not operation_valid(v.get('requested_operation',v.get('operation',{}))): e.append('invalid_operation')
 if 'input_bindings' in v and not passive_payload(v.get('input_bindings',{})): e.append('invalid_input_bindings')
 if 'expected_output_contract' in v and not output_contract_valid(v.get('expected_output_contract')): e.append('invalid_output_contract')
 if 'resource_constraints' in v and v.get('resource_constraints') is not None and not resource_constraints_valid(v.get('resource_constraints')): e.append('invalid_resource_constraints')
 if 'timeout_constraints' in v and v.get('timeout_constraints') is not None and not timeout_constraints_valid(v.get('timeout_constraints')): e.append('invalid_timeout_constraints')
 if 'environment_constraints' in v and v.get('environment_constraints') is not None and not passive_payload(v.get('environment_constraints')): e.append('invalid_environment_constraints')
 if 'authority_constraints' in v and v.get('authority_constraints') is not None and not authority_valid(v.get('authority_constraints'), scope): e.append('invalid_authority')
 if not passive_false(v): e.append('non_execution_invariant_failed')
 return e
