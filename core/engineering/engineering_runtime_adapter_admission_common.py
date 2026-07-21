from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping, Sequence
from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.repository_analysis_common import ValidationResult

PROHIBITED_KEYS=frozenset({'secret','secrets','token','credentials','credential','password','private_key','bearer','signature','raw_signature','command','shell_command','patch','diff','payload','executable','executor','scheduler','subprocess','runtime_handle','adapter_instance'})
PROHIBITED_STRINGS=('bearer ','-----begin','private key','password=','token=','secret=','#!/','&&',';','|','`','$(')
WILDCARDS=frozenset({'*','all','global','unrestricted','any','everything'})
TERMINAL_STATES=frozenset({'rejected','closed','closed_completed','closed_partial','failed','blocked','denied','revoked','consumed'})

def is_mapping(v:Any)->bool: return isinstance(v,Mapping)
def is_sequence(v:Any)->bool: return isinstance(v,Sequence) and not isinstance(v,(str,bytes,bytearray))
def canonical_fingerprint(v:Any)->str: return fingerprint(v)
def canonical_identity(prefix:str, fields:Mapping[str,Any])->str: return prefix+fingerprint(dict(fields))[:24]
def stable_artifact(base:Mapping[str,Any], id_key:str, prefix:str)->dict[str,Any]: return identified(deepcopy(dict(base)),id_key,prefix)
def valid_identity(v:Any,id_key:str,prefix:str)->bool:
    if not isinstance(v,Mapping): return False
    try: return identity_valid(v,id_key,prefix)
    except (TypeError,ValueError): return False

def contains_prohibited(v:Any)->bool:
    if isinstance(v,Mapping):
        return any(((str(k).lower() in PROHIBITED_KEYS and x is not None and not str(k).lower().endswith(('_identity','_id','_fingerprint')) and x not in {'not_granted','granted','consumed','closed'}) or contains_prohibited(x)) for k,x in v.items())
    if is_sequence(v): return any(contains_prohibited(x) for x in v)
    if isinstance(v,str):
        s=v.lower(); return any(p in s for p in PROHIBITED_STRINGS)
    return isinstance(v,(bytes,bytearray,set,tuple))

def canonical_nonempty(s:Any)->bool:
    return isinstance(s,str) and s.strip()==s and bool(s) and s.lower() not in WILDCARDS and all(c.isalnum() or c in '._-' for c in s)

def scope_bounded(child:Any,parent:Any)->bool:
    if contains_wildcard(child): return False
    if isinstance(parent,Mapping) and isinstance(child,Mapping): return all(k in parent and scope_bounded(v,parent[k]) for k,v in child.items())
    if isinstance(parent,list) and isinstance(child,list): return all(v in parent and v not in WILDCARDS for v in child)
    return child==parent and child not in WILDCARDS

def contains_wildcard(v:Any)->bool:
    if isinstance(v,str): return v.lower() in WILDCARDS
    if isinstance(v,Mapping): return any(contains_wildcard(x) for x in v.values())
    if is_sequence(v): return any(contains_wildcard(x) for x in v)
    return False

def authority_valid(a:Any, scope:Any)->bool:
    if not isinstance(a,Mapping) or contains_prohibited(a): return False
    required={'non_transferable':True,'non_reusable':True,'scope_bound':True,'perpetual':False,'passive':True,'consumed':False,'closed':False,'unrestricted':False}
    if any(a.get(k) is not val for k,val in required.items()): return False
    if a.get('scope') is not None and not scope_bounded(a.get('scope'),scope): return False
    return not contains_wildcard(a)

def boundary()->dict[str,bool]:
    return {'sealed':True,'passive_only':True,'runtime_adapter_invoked':False,'execution_prepared':False,'execution_activated':False,'authority_consumed':False,'repository_mutated':False,'ungoverned_execution_authorized':False}

def validate_artifact(value:Any,*,schema:str,statuses:set[str],id_key:str,prefix:str,fields:set[str])->ValidationResult:
    if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_object',))
    req={'schema',id_key,'fingerprint','boundary',*fields}; errors=[f'missing:{k}' for k in sorted(req-set(value))]+[f'unexpected:{k}' for k in sorted(set(value)-req)]
    if value.get('schema')!=schema or (('status' in fields or any(k.endswith('_status') for k in fields)) and not any(value.get(k) in statuses for k in ('status','eligibility_status','admission_status','package_status'))): errors.append('invalid_contract')
    if value.get('boundary')!=boundary(): errors.append('unsafe_boundary')
    if contains_prohibited(value): errors.append('prohibited_payload')
    if not valid_identity(value,id_key,prefix): errors.append('identity_mismatch')
    return ValidationResult(not errors,tuple(dict.fromkeys(errors)))
