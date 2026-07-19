from __future__ import annotations
from copy import deepcopy
from math import isfinite
from typing import Any, Mapping, Sequence
from core.engineering.engineering_intake_common import fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult
PROHIBITED_TERMS=frozenset('command shell script source_code executable binary bytecode import module_loading import_path module_path entrypoint callback callable patch diff token credential credentials password private_key api_key bearer authorization_header secret environment_secret subprocess os.system shell=True eval exec compile importlib __import__ requests urllib socket network'.lower().split())
IDENTITY_ONLY=frozenset('adapter_id adapter_version execution_session_id invocation_descriptor_id activation_handoff_id activation_result_id invocation_handoff_id invocation_closure_id invocation_fingerprint upstream_closure_fingerprint capability_id binding_resolution_id environment_admission_id isolation_policy_id resource_budget_id timeout_policy_id execution_request_id execution_preparation_id execution_review_id execution_authorization_id execution_envelope_id readiness_verification_id executor_handoff_id fingerprint'.split())
FALSE_FIELDS=('real_execution_authorized','executor_invoked','runtime_invoked','effects_performed','mutation_performed','adapter_loaded','adapter_invoked','adapter_code_executed','external_effect_performed','authority_consumed')
WILDCARDS=frozenset({'*','all','global','unrestricted','any','everything','system','repository-wide','unbounded'})
def canonical_json(v:Any)->str: return fingerprint.__globals__['json'].dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
def canonical_fingerprint(v:Any)->str:
 try: return fingerprint(v)
 except Exception: return fingerprint({'malformed':True})
def stable_artifact(base:Mapping[str,Any], id_key:str, prefix:str)->dict[str,Any]:
 body=deepcopy(dict(base)); body.pop(id_key,None); body.pop('fingerprint',None); return identified(body,id_key,prefix)
def is_sequence(v:Any)->bool: return isinstance(v,Sequence) and not isinstance(v,(str,bytes,bytearray))
def strict_mapping(v:Any)->bool: return isinstance(v,Mapping) and not contains_prohibited(v)
def strict_sequence(v:Any)->bool: return is_sequence(v) and not contains_prohibited(v)
def strict_bool(v:Any)->bool: return isinstance(v,bool)
def strict_int(v:Any,lo:int,hi:int)->bool: return isinstance(v,int) and not isinstance(v,bool) and lo<=v<=hi
def canonical_nonempty(s:Any)->bool: return isinstance(s,str) and s.strip()==s and bool(s) and s.lower() not in WILDCARDS and all(c.isalnum() or c in '._:-' for c in s)
def normalize_reasons(rs:Any)->list[str]: return sorted({r for r in (rs or []) if canonical_nonempty(r)})
def canonical_order(xs:Any)->list[Any]: return sorted(list(xs or []), key=lambda x: canonical_json(x))
def dedupe(xs:Any)->list[Any]:
 out=[]; seen=set()
 for x in canonical_order(xs if is_sequence(xs) else []):
  f=canonical_fingerprint(x)
  if f not in seen: seen.add(f); out.append(x)
 return out
def contains_prohibited(v:Any)->bool:
 if callable(v) or isinstance(v,(bytes,bytearray,set,tuple)): return True
 if isinstance(v,float): return True
 if isinstance(v,Mapping):
  for k,x in v.items():
   key=str(k).lower().replace('-','_')
   if key in PROHIBITED_TERMS and key not in IDENTITY_ONLY and not (isinstance(x,bool) and x is False): return True
   if contains_prohibited(x): return True
  return False
 if is_sequence(v): return any(contains_prohibited(x) for x in v)
 if isinstance(v,str):
  low=v.lower(); return any(t in low for t in ('bearer ','-----begin','private key','password=','secret=','api_key=','access_token=','authorization:','#!/','&&',';','|','`','$(','def ','lambda ','import '))
 return not (v is None or isinstance(v,(str,bool,int)))
def scope_subset(child:Any,parent:Any)->bool:
 if isinstance(child,str) and child in WILDCARDS: return False
 if isinstance(parent,str) and parent in WILDCARDS: return False
 if isinstance(parent,Mapping) and isinstance(child,Mapping): return bool(child) and all(k in parent and scope_subset(v,parent[k]) for k,v in child.items())
 if isinstance(parent,list) and isinstance(child,list): return bool(child) and all(v in parent for v in child)
 return child==parent
def operation_equal(a:Any,b:Any)->bool: return a==b and isinstance(a,Mapping) and canonical_nonempty(a.get('operation_id'))
def output_contract_equal(a:Any,b:Any)->bool: return a==b and isinstance(a,Mapping) and canonical_nonempty(a.get('contract_id'))
def authority_subset(child:Any,parent:Any)->bool: return isinstance(child,Mapping) and isinstance(parent,Mapping) and child.get('consumed') is False and parent.get('consumed') is False and scope_subset(child.get('scope',{}),parent.get('scope',{}))
def passive_invariants(v:Mapping[str,Any])->bool: return all(v.get(k) is False for k in FALSE_FIELDS if k in v)
def validate_artifact(value:Any,*,schema:str,id_key:str,prefix:str,fields:set[str],status_key:str|None=None,statuses:set[str]|None=None)->ValidationResult:
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_object',))
 req={'schema',id_key,'fingerprint',*fields};
 if status_key: req.add(status_key)
 e=[f'missing:{k}' for k in sorted(req-set(value))]
 if value.get('schema')!=schema: e.append('invalid_schema')
 if status_key and statuses and value.get(status_key) not in statuses: e.append('invalid_status')
 if contains_prohibited(value): e.append('prohibited_payload')
 try:
  if not identity_valid(value,id_key,prefix): e.append('identity_mismatch')
 except Exception: e.append('identity_mismatch')
 if not passive_invariants(value): e.append('non_execution_invariant_failed')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_result(valid:bool, reasons:Any)->dict[str,Any]: return {'valid':bool(valid),'reason_codes':normalize_reasons(reasons)}
def link_ok(a:Mapping[str,Any],b:Mapping[str,Any],keys:Sequence[str])->bool: return all(a.get(k)==b.get(k) for k in keys)
