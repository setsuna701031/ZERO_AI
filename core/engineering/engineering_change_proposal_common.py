
from __future__ import annotations
import hashlib, json, math, re
from typing import Any, Mapping, Sequence

SCHEMAS={
 'intent':'zero.engineering.change_intent.v1','workspace_evidence':'zero.engineering.change_workspace_evidence.v1','target_admission':'zero.engineering.change_target_admission.v1','scope_policy':'zero.engineering.change_scope_policy.v1','file_precondition':'zero.engineering.change_file_precondition.v1','operation':'zero.engineering.change_operation.v1','content':'zero.engineering.change_content.v1','diff':'zero.engineering.change_diff.v1','proposal':'zero.engineering.change_proposal.v1','validation':'zero.engineering.change_proposal_validation.v1','safety_review':'zero.engineering.change_proposal_safety_review.v1','verification':'zero.engineering.change_proposal_verification.v1','evidence':'zero.engineering.change_proposal_evidence.v1','approval_handoff':'zero.engineering.change_proposal_approval_handoff.v1','closure':'zero.engineering.change_proposal_closure.v1'}
UPSTREAM_SCHEMAS=('zero.engineering.runtime_workspace_execution_closure.v1','zero.engineering.runtime_workspace_execution_verification.v1','zero.engineering.runtime_workspace_execution_result.v1','zero.engineering.runtime_workspace_observation_output.v1','zero.engineering.runtime_workspace_root_admission.v1','zero.engineering.runtime_workspace_read_scope.v1','zero.engineering.runtime_workspace_path_resolution.v1')
INTENT_CATEGORIES=('create_text_file','replace_text_file','delete_file_proposal','create_directory_proposal','rename_path_proposal','multi_file_text_change')
OPERATION_TYPES=('create_text_file','replace_text_file','delete_file','create_directory','rename_path')
FALSE_FLAGS=('mutation_authorized','mutation_performed','mutation_prepared','patch_applied','filesystem_write_performed','git_invoked','shell_invoked','runtime_kernel_invoked','operator_approval_obtained')
PROHIBITED_KEYS=('command','shell','callback','callable','adapter','credential','password','secret','api_key','access_token','private_key','authorization','binary','stdout','stderr','traceback','exception')
PROHIBITED_TEXT=('credential','password','private key','api key','bearer ','authorization header','access token','secret')

def canonical_json(v:Any)->str: return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def sha256_text(s:str)->str: return hashlib.sha256(s.encode('utf-8')).hexdigest()
def fingerprint(v:Any)->str: return sha256_text(canonical_json(v))
def stable_id(prefix:str,v:Any)->str: return prefix+'-'+fingerprint(v)[:24]
def reasons(items:Sequence[str])->list[str]: return sorted(set(str(x) for x in items if x))
def artifact(prefix:str,schema:str,body:Mapping[str,Any],id_field:str)->dict[str,Any]:
 b=dict(body); b['schema']=schema; fp=fingerprint(b); b['fingerprint']=fp; b[id_field]=prefix+'-'+fp[:24]; return b

def require_mapping(v:Any,name='payload')->list[str]: return [] if isinstance(v,dict) else [name+'_not_mapping']
def strict_bool(v:Any,name:str)->list[str]: return [] if type(v) is bool else [name+'_not_strict_bool']
def bounded_int(v:Any,name:str,minimum:int=0)->list[str]:
 if type(v) is not int: return [name+'_not_integer']
 if v<minimum: return [name+'_below_minimum']
 return []
def finite_number(v:Any,name:str)->list[str]:
 if type(v) not in (int,float) or isinstance(v,bool) or not math.isfinite(v): return [name+'_not_finite']
 return []

def normalize_relative_path(path:Any,max_len:int=240,max_segments:int=32)->tuple[str|None,list[str]]:
 rs=[]
 if not isinstance(path,str): return None,['path_not_string']
 if '\x00' in path: rs.append('path_contains_nul')
 p=path.replace('\\','/')
 if p.startswith('//'): rs.append('path_unc')
 if re.match(r'^[A-Za-z]:',p): rs.append('path_drive_qualified')
 if p.startswith('/'): rs.append('path_absolute')
 parts=[]
 for part in p.split('/'):
  if part in ('','.'): continue
  if part=='..': rs.append('path_parent_traversal'); continue
  if ':' in part: rs.append('path_alternate_stream')
  parts.append(part)
 norm='/'.join(parts)
 if not norm: rs.append('path_empty')
 if len(norm)>max_len: rs.append('path_too_long')
 if len(parts)>max_segments: rs.append('path_too_many_segments')
 return norm if not rs else None,reasons(rs)

def prefix_allowed(path:str,prefixes:Sequence[str])->bool:
 return any(path==p.strip('/') or path.startswith(p.strip('/')+'/') for p in prefixes)
def subset(child:Sequence[str],parent:Sequence[str])->bool: return set(child).issubset(set(parent))
def contains_prohibited_payload(v:Any)->list[str]:
 out=[]
 def walk(x,path=''):
  if callable(x): out.append('callable_payload'); return
  if isinstance(x,(bytes,bytearray,memoryview)): out.append('binary_payload'); return
  if isinstance(x,dict):
   for k,val in x.items():
    ks=str(k).lower().replace('-','_')
    if any(p in ks for p in PROHIBITED_KEYS): out.append('prohibited_key')
    walk(val,path+'.'+str(k))
  elif isinstance(x,(list,tuple)):
   for i,val in enumerate(x): walk(val,path+f'[{i}]')
  elif isinstance(x,str):
   low=x.lower()
   if any(p in low for p in PROHIBITED_TEXT): out.append('prohibited_text')
 walk(v); return reasons(out)
def validate_false_invariants(a:Mapping[str,Any])->list[str]:
 return reasons([f'{k}_not_false' for k in FALSE_FLAGS if k in a and a.get(k) is not False])
def line_stats(text:str)->dict[str,Any]:
 lines=text.splitlines()
 return {'line_count':len(lines),'max_line_length':max([len(x) for x in lines] or [0])}
def validate_text_content(text:Any,max_bytes:int,max_lines:int,max_line:int)->tuple[dict[str,Any],list[str]]:
 rs=[]
 if not isinstance(text,str): return {},['content_not_string']
 try: b=text.encode('utf-8')
 except UnicodeError: return {},['content_not_utf8']
 st=line_stats(text)
 if len(b)>max_bytes: rs.append('content_too_large')
 if st['line_count']>max_lines: rs.append('too_many_lines')
 if st['max_line_length']>max_line: rs.append('line_too_long')
 return {'byte_count':len(b),'sha256':hashlib.sha256(b).hexdigest(),**st},reasons(rs)
def validate_operation_conflicts(ops:Sequence[Mapping[str,Any]])->list[str]:
 targets=[o.get('target_relative_path') for o in ops]
 rs=[]
 if len([t for t in targets if t])!=len(set(t for t in targets if t)): rs.append('duplicate_target_conflict')
 pairs={(o.get('source_relative_path'),o.get('target_relative_path')) for o in ops if o.get('source_relative_path')}
 for a,b in pairs:
  if (b,a) in pairs: rs.append('source_target_cycle')
 allp=[p for o in ops for p in (o.get('source_relative_path'),o.get('target_relative_path')) if p]
 for a in allp:
  for b in allp:
   if a!=b and b.startswith(a.rstrip('/')+'/'): rs.append('parent_child_ambiguity')
 return reasons(rs)
