from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping, Sequence
from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult

PROHIBITED_KEYS=frozenset({'command','command_line','shell','script','source_code','bytecode','executable','binary','patch','diff','process','subprocess','callable','callback','function','module_path','import_path','entrypoint','raw_arguments','credentials','password','private_key','bearer','access_token','refresh_token','api_key','authorization_header','environment_secrets'})
PROHIBITED_STRINGS=('bearer ','-----begin','private key','password=','secret=','api_key=','access_token=','refresh_token=','#!/','&&',';','|','`','$(','def ','lambda ','import ')
WILDCARDS=frozenset({'*','all','global','unrestricted','any','everything'})
PASSIVE_FALSE_KEYS=frozenset({'activation_authorized','adapter_activated','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed','eligible_for_activation_review'})

def is_mapping(v:Any)->bool: return isinstance(v,Mapping)
def is_sequence(v:Any)->bool: return isinstance(v,Sequence) and not isinstance(v,(str,bytes,bytearray))
def canonical_fingerprint(v:Any)->str: return fingerprint(v)
def canonical_identity(prefix:str, fields:Mapping[str,Any])->str: return prefix+fingerprint(dict(fields))[:24]
def stable_artifact(base:Mapping[str,Any], id_key:str, prefix:str)->dict[str,Any]: return identified(deepcopy(dict(base)),id_key,prefix)
def valid_identity(v:Any,id_key:str,prefix:str)->bool:
 try: return isinstance(v,Mapping) and identity_valid(v,id_key,prefix)
 except (TypeError,ValueError): return False

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
def canonical_nonempty(s:Any)->bool: return isinstance(s,str) and s.strip()==s and bool(s) and s.lower() not in WILDCARDS and all(c.isalnum() or c in '._:-' for c in s)
def contains_wildcard(v:Any)->bool:
 if isinstance(v,str): return v.lower() in WILDCARDS
 if isinstance(v,Mapping): return any(contains_wildcard(x) for x in v.values())
 if is_sequence(v): return any(contains_wildcard(x) for x in v)
 return False
def scope_bounded(child:Any,parent:Any)->bool:
 if contains_wildcard(child): return False
 if isinstance(parent,Mapping) and isinstance(child,Mapping): return bool(child) and all(k in parent and scope_bounded(v,parent[k]) for k,v in child.items())
 if isinstance(parent,list) and isinstance(child,list): return bool(child) and all(v in parent and v not in WILDCARDS for v in child)
 return child==parent and child not in WILDCARDS
def passive_mapping(v:Any)->bool: return isinstance(v,Mapping) and not contains_prohibited(v)
def resources_valid(v:Any)->bool: return isinstance(v,Mapping) and bool(v) and not contains_prohibited(v) and all(isinstance(x,(int,float)) and x>0 for x in v.values())
def timeout_valid(v:Any)->bool: return isinstance(v,Mapping) and v.get('finite') is True and isinstance(v.get('seconds'),(int,float)) and v.get('seconds')>0 and v.get('perpetual') is False and not contains_prohibited(v)
def environment_valid(v:Any)->bool: return isinstance(v,Mapping) and bool(v) and not contains_prohibited(v)
def authority_valid(a:Any, scope:Any)->bool:
 if not isinstance(a,Mapping) or contains_prohibited(a): return False
 req={'non_transferable':True,'non_reusable':True,'scope_bound':True,'perpetual':False,'passive':True,'consumed':False,'closed':False,'unrestricted':False,'restricted':True}
 return all(a.get(k) is v for k,v in req.items()) and a.get('scope')==scope and scope_bounded(a.get('scope'),scope)
def passive_invariants_valid(v:Any)->bool:
 return isinstance(v,Mapping) and v.get('passive_only') is True and not any(v.get(k) for k in ('activation_authorized','adapter_activated','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed'))
def normalize_reasons(rs:Any)->list[str]: return sorted({r for r in rs if canonical_nonempty(r)})
def normalize_findings(rs:Any)->list[str]: return normalize_reasons(rs)
def validate_link(a:Mapping[str,Any], aid:str, afp:str, b:Mapping[str,Any], bid:str='fingerprint')->bool: return a.get(aid)==b.get(aid) and a.get(afp)==b.get(bid)
def validate_artifact(value:Any,*,schema:str,statuses:set[str],id_key:str,prefix:str,fields:set[str],status_key:str|None=None)->ValidationResult:
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_object',))
 req={'schema',id_key,'fingerprint',*fields}; e=[f'missing:{k}' for k in sorted(req-set(value))]+[f'unexpected:{k}' for k in sorted(set(value)-req)]
 if value.get('schema')!=schema: e.append('invalid_contract')
 if status_key and value.get(status_key) not in statuses: e.append('invalid_contract')
 if contains_prohibited(value): e.append('prohibited_payload')
 if not valid_identity(value,id_key,prefix): e.append('identity_mismatch')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
