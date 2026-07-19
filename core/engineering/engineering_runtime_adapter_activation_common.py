from __future__ import annotations
from copy import deepcopy
from math import isfinite
from typing import Any, Mapping, Sequence
from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult
PROHIBITED_KEYS=frozenset('command command_line shell shell_command script source_code bytecode executable binary patch diff process subprocess callable callback function module_path import_path entrypoint runtime_entrypoint adapter_entrypoint activation_callback invocation_callback raw_arguments token_value raw_token bearer_token token_secret secret_token credentials password private_key secret_key bearer access_token refresh_token api_key authorization_header environment_secrets'.split())
IDENTITY_ONLY=frozenset('token_id activation_id authority_reference execution_session_id invocation_descriptor_id adapter_id token_handoff_id'.split())
PROHIBITED_STRINGS=('bearer ','-----begin','private key','password=','secret=','api_key=','access_token=','refresh_token=','authorization:','#!/','&&',';','|','`','$(','def ','lambda ','import ')
WILDCARDS=frozenset({'*','all','global','unrestricted','any','everything','repository','repository-wide','system','system-wide','unbounded'})
FALSE_FIELDS=('adapter_loaded','adapter_activated','adapter_code_executed','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed','repository_mutation_performed','secret_material_consumed','external_credential_consumed')
def is_sequence(v:Any)->bool: return isinstance(v,Sequence) and not isinstance(v,(str,bytes,bytearray))
def canonical_fingerprint(v:Any)->str:
 try: return fingerprint(v)
 except (TypeError,ValueError,OverflowError): return fingerprint({'malformed':True})
def stable_artifact(base:Mapping[str,Any], id_key:str, prefix:str)->dict[str,Any]: return identified(deepcopy(dict(base)),id_key,prefix)
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
def validate_status(status:Any, allowed:set[str])->bool: return status in allowed
def validate_artifact(value:Any,*,schema:str,id_key:str,prefix:str,fields:set[str],status_key:str|None=None,statuses:set[str]|None=None)->ValidationResult:
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_object',))
 req={'schema',id_key,'fingerprint',*fields}; e=[f'missing:{k}' for k in sorted(req-set(value))]+[f'unexpected:{k}' for k in sorted(set(value)-req)]
 if value.get('schema')!=schema: e.append('invalid_schema')
 if status_key and statuses and value.get(status_key) not in statuses: e.append('invalid_status')
 if contains_prohibited(value): e.append('prohibited_payload')
 if not valid_identity(value,id_key,prefix): e.append('identity_mismatch')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def fingerprint_valid(v:Mapping[str,Any])->bool: return v.get('fingerprint')==canonical_fingerprint({k:x for k,x in v.items() if k not in {'fingerprint', next((k for k in v if k.endswith('_id') and k.split('_id')[0] in k), '')}})
def exact(a:Mapping[str,Any],b:Mapping[str,Any],keys:Sequence[str])->bool: return all(a.get(k)==b.get(k) for k in keys)
def passive_false(v:Mapping[str,Any])->bool: return all(v.get(k) is False for k in FALSE_FIELDS if k in v)
def activation_configuration_valid(v:Any)->bool: return isinstance(v,Mapping) and v.get('passive_only') is True and not contains_prohibited(v)
def resource_constraints_valid(v:Any)->bool: return isinstance(v,Mapping) and bool(v) and not contains_prohibited(v) and all(isinstance(x,(int,float)) and isfinite(x) and x>0 for x in v.values() if isinstance(x,(int,float)))
def timeout_constraints_valid(v:Any)->bool: return isinstance(v,Mapping) and bool(v) and not contains_prohibited(v) and all(isinstance(x,(int,float)) and isfinite(x) and x>0 for x in v.values())
def authority_valid(v:Any,scope:Any)->bool: return isinstance(v,Mapping) and v.get('valid') is True and v.get('consumed') is False and v.get('passive') is True and not contains_prohibited(v) and ('scope' not in v or scope_bounded(v['scope'],scope))
def inspect_result(valid:bool, reasons:list[str]|tuple[str,...])->dict[str,Any]: return {'valid':bool(valid),'reason_codes':normalize_reasons(reasons)}
