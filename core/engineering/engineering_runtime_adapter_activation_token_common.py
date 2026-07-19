from __future__ import annotations
from copy import deepcopy
from math import isfinite
from typing import Any, Mapping, Sequence
from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult
PROHIBITED_KEYS=frozenset({'command','command_line','shell','shell_command','script','source_code','bytecode','executable','binary','patch','diff','process','subprocess','callable','callback','function','module_path','import_path','entrypoint','raw_arguments','activation_callback','activation_command','invocation_command','runtime_entrypoint','token_value','raw_token','bearer_token','token_secret','secret_token','credentials','password','private_key','secret_key','bearer','access_token','refresh_token','api_key','authorization_header','environment_secrets','raw_token_bytes','signature_secret','code','token_material'})
IDENTITY_ONLY=frozenset({'token_request_id','token_preparation_id','token_review_id','token_authorization_id','token_issuance_id','token_id','authority_reference'})
PROHIBITED_STRINGS=('bearer ','-----begin','private key','password=','secret=','api_key=','access_token=','refresh_token=','authorization:','token=','#!/','&&',';','|','`','$(','def ','lambda ','import ','command_line','shell_command')
WILDCARDS=frozenset({'*','all','global','unrestricted','any','everything','repository','repository-wide','system','system-wide','unbounded'})
FALSE_INVARIANTS=('token_material_present','adapter_loaded','adapter_activated','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','planner_invoked','worker_invoked','authority_consumed','mutation_performed')
def is_sequence(v:Any)->bool: return isinstance(v,Sequence) and not isinstance(v,(str,bytes,bytearray))
def canonical_fingerprint(v:Any)->str:
 try: return fingerprint(v)
 except (TypeError,ValueError,OverflowError): return fingerprint({'malformed':True})
def stable_artifact(base:Mapping[str,Any], id_key:str, prefix:str)->dict[str,Any]:
 try: return identified(deepcopy(dict(base)),id_key,prefix)
 except (TypeError,ValueError,OverflowError):
  body=deepcopy(dict(base)); body[id_key]=prefix+'malformed'; body['fingerprint']=canonical_fingerprint({'malformed':True}); return body
def valid_identity(v:Any,id_key:str,prefix:str)->bool:
 try: return isinstance(v,Mapping) and identity_valid(v,id_key,prefix)
 except (TypeError,ValueError): return False
def canonical_nonempty(s:Any)->bool: return isinstance(s,str) and s.strip()==s and bool(s) and s.lower() not in WILDCARDS and all(c.isalnum() or c in '._:-' for c in s)
def contains_prohibited(v:Any)->bool:
 if isinstance(v,Mapping):
  for k,x in v.items():
   key=str(k).lower()
   if key in PROHIBITED_KEYS and not (key in IDENTITY_ONLY or (key in {'executable','bearer','credential','secret','consumed','token_material'} and x is False)): return True
   if contains_prohibited(x): return True
  return False
 if is_sequence(v): return any(contains_prohibited(x) for x in v)
 if isinstance(v,str):
  s=v.lower(); return any(p in s for p in PROHIBITED_STRINGS)
 return isinstance(v,(bytes,bytearray,set,tuple)) or callable(v)
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
def normalize_reasons(rs:Any)->list[str]: return sorted({r for r in rs if canonical_nonempty(r)})
def token_constraints_valid(c:Any,scope:Any|None=None)->bool:
 if not isinstance(c,Mapping) or contains_prohibited(c): return False
 req={'non_transferable':True,'non_reusable':True,'scope_bound':True,'adapter_bound':True,'session_bound':True,'authorization_bound':True,'passive':True,'consumed':False,'restricted':True,'bearer':False,'credential':False,'secret':False,'executable':False}
 if not all(c.get(k) is v for k,v in req.items()): return False
 if c.get('perpetual') is not False or c.get('max_uses')!=1: return False
 if scope is not None and 'scope' in c and not scope_bounded(c.get('scope'),scope): return False
 return True
def authority_valid(a:Any, scope:Any)->bool:
 if not isinstance(a,Mapping) or contains_prohibited(a): return False
 req={'valid':True,'consumed':False,'restricted':True,'passive':True,'execution_authority_consumed':False,'activation_authority_consumed':False,'mutation_authority_consumed':False}
 return all(a.get(k) is v for k,v in req.items()) and (('scope' not in a) or scope_bounded(a.get('scope'),scope))
def passive_invariants_valid(v:Any)->bool: return isinstance(v,Mapping) and v.get('passive_only',True) is True and not any(v.get(k) for k in FALSE_INVARIANTS)
def validate_artifact(value:Any,*,schema:str,id_key:str,prefix:str,fields:set[str],status_key:str|None=None,statuses:set[str]|None=None)->ValidationResult:
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_object',))
 req={'schema',id_key,'fingerprint',*fields}; e=[f'missing:{k}' for k in sorted(req-set(value))]+[f'unexpected:{k}' for k in sorted(set(value)-req)]
 if value.get('schema')!=schema: e.append('invalid_schema')
 if status_key and statuses and value.get(status_key) not in statuses: e.append('invalid_status')
 if contains_prohibited(value): e+=['executable_payload','credential_like_payload']
 if not valid_identity(value,id_key,prefix): e.append('identity_mismatch')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def exact_link(a:Mapping[str,Any], aid:str, afp:str, b:Mapping[str,Any], bid:str)->bool: return a.get(aid)==b.get(bid) and a.get(afp)==b.get('fingerprint')
