from __future__ import annotations
from copy import deepcopy
from math import isfinite
from typing import Any, Mapping, Sequence
from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult

PROHIBITED_KEYS=frozenset({'command','command_line','shell','shell_command','script','source_code','bytecode','executable','binary','patch','diff','process','subprocess','callable','callback','function','module_path','import_path','entrypoint','raw_arguments','activation_callback','activation_command','invocation_command','runtime_entrypoint','credentials','password','private_key','bearer','access_token','refresh_token','api_key','authorization_header','environment_secrets','activation_token'})
PROHIBITED_STRINGS=('bearer ','-----begin','private key','password=','secret=','api_key=','access_token=','refresh_token=','#!/','&&',';','|','`','$(','def ','lambda ','import ')
WILDCARDS=frozenset({'*','all','global','unrestricted','any','everything','repository','repository-wide','system','system-wide','unbounded'})
FALSE_INVARIANTS=('activation_authorized','activation_token_issued','adapter_loaded','adapter_activated','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed')

def is_mapping(v:Any)->bool: return isinstance(v,Mapping)
def is_sequence(v:Any)->bool: return isinstance(v,Sequence) and not isinstance(v,(str,bytes,bytearray))
def canonical_fingerprint(v:Any)->str: return fingerprint(v)
def stable_artifact(base:Mapping[str,Any], id_key:str, prefix:str)->dict[str,Any]: return identified(deepcopy(dict(base)),id_key,prefix)
def valid_identity(v:Any,id_key:str,prefix:str)->bool:
 try: return isinstance(v,Mapping) and identity_valid(v,id_key,prefix)
 except (TypeError,ValueError): return False

def canonical_nonempty(s:Any)->bool: return isinstance(s,str) and s.strip()==s and bool(s) and s.lower() not in WILDCARDS and all(c.isalnum() or c in '._:-' for c in s)
def contains_prohibited(v:Any)->bool:
 if isinstance(v,Mapping):
  for k,x in v.items():
   key=str(k).lower()
   if key in PROHIBITED_KEYS and not (key=='executable' and x is False): return True
   if contains_prohibited(x): return True
  return False
 if is_sequence(v): return any(contains_prohibited(x) for x in v)
 if isinstance(v,str):
  s=v.lower(); return any(p in s for p in PROHIBITED_STRINGS)
 return isinstance(v,(bytes,bytearray,set,tuple)) or callable(v)
def contains_credential_like(v:Any)->bool: return contains_prohibited(v)
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
def passive_mapping(v:Any)->bool: return isinstance(v,Mapping) and bool(v) and not contains_prohibited(v)
def activation_constraints_valid(v:Any)->bool: return passive_mapping(v) and v.get('passive') is True and v.get('deterministic') is True
def resources_valid(v:Any)->bool: return isinstance(v,Mapping) and bool(v) and not contains_prohibited(v) and all(isinstance(x,(int,float)) and not isinstance(x,bool) and isfinite(x) and x>0 for x in v.values())
def timeout_valid(v:Any)->bool: return isinstance(v,Mapping) and v.get('finite') is True and isinstance(v.get('seconds'),(int,float)) and not isinstance(v.get('seconds'),bool) and isfinite(v.get('seconds')) and v.get('seconds')>0 and v.get('perpetual') is False and not contains_prohibited(v)
def environment_valid(v:Any)->bool: return passive_mapping(v)
def authority_valid(a:Any, scope:Any)->bool:
 if not isinstance(a,Mapping) or contains_prohibited(a): return False
 req={'non_transferable':True,'non_reusable':True,'scope_bound':True,'perpetual':False,'passive':True,'consumed':False,'closed':False,'unrestricted':False,'restricted':True}
 return all(a.get(k) is v for k,v in req.items()) and scope_bounded(a.get('scope'),scope)
def passive_invariants_valid(v:Any)->bool: return isinstance(v,Mapping) and v.get('passive_only') is True and not any(v.get(k) for k in FALSE_INVARIANTS)
def normalize_reasons(rs:Any)->list[str]: return sorted({r for r in rs if canonical_nonempty(r)})
def exact(a:Mapping[str,Any],ka:str,b:Mapping[str,Any],kb:str)->bool: return a.get(ka)==b.get(kb)
def validate_artifact(value:Any,*,schema:str,id_key:str,prefix:str,fields:set[str],status_key:str|None=None,statuses:set[str]|None=None)->ValidationResult:
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_object',))
 req={'schema',id_key,'fingerprint',*fields}; e=[f'missing:{k}' for k in sorted(req-set(value))]+[f'unexpected:{k}' for k in sorted(set(value)-req)]
 if value.get('schema')!=schema: e.append('invalid_schema')
 if status_key and statuses and value.get(status_key) not in statuses: e.append('invalid_status')
 if contains_prohibited(value): e.append('executable_payload')
 if contains_credential_like(value):
  if 'executable_payload' not in e: e.append('credential_like_payload')
 if not valid_identity(value,id_key,prefix): e.append('identity_mismatch')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
