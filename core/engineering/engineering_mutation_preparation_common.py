from __future__ import annotations
import hashlib,json,re
from typing import Any,Mapping,Sequence
SCHEMAS={
'operator_approval_policy':'zero.engineering.operator_approval_policy.v1','operator_approval_request':'zero.engineering.operator_approval_request.v1','operator_approval_eligibility':'zero.engineering.operator_approval_eligibility.v1','operator_approval_decision':'zero.engineering.operator_approval_decision.v1','operator_approved_scope':'zero.engineering.operator_approved_scope.v1','operator_approval_verification':'zero.engineering.operator_approval_verification.v1','mutation_preparation_policy':'zero.engineering.mutation_preparation_policy.v1','mutation_preparation_request':'zero.engineering.mutation_preparation_request.v1','mutation_preparation_admission':'zero.engineering.mutation_preparation_admission.v1','prepared_mutation_operation':'zero.engineering.prepared_mutation_operation.v1','mutation_package':'zero.engineering.mutation_package.v1','mutation_package_validation':'zero.engineering.mutation_package_validation.v1','mutation_preparation_token_eligibility':'zero.engineering.mutation_preparation_token_eligibility.v1','mutation_preparation_token':'zero.engineering.mutation_preparation_token.v1','mutation_readiness_verification':'zero.engineering.mutation_readiness_verification.v1','mutation_handoff':'zero.engineering.mutation_handoff.v1','mutation_preparation_evidence':'zero.engineering.mutation_preparation_evidence.v1','mutation_preparation_closure':'zero.engineering.mutation_preparation_closure.v1'}
UPSTREAM_SCHEMAS=('zero.engineering.change_proposal_approval_handoff.v1','zero.engineering.change_proposal_closure.v1','zero.engineering.change_proposal_verification.v1','zero.engineering.change_proposal_safety_review.v1','zero.engineering.change_proposal_validation.v1','zero.engineering.change_proposal.v1')
FALSE_FLAGS=('mutation_authorized','mutation_performed','mutation_prepared','patch_applied','filesystem_write_performed','git_invoked','shell_invoked','adapter_invoked','runtime_kernel_invoked','mutation_executor_invoked','token_consumed')
PROHIBITED_TERMS=('command','shell','script','executable','bytecode','import_path','entrypoint','callback','callable','git_command','authentication_token','bearer_token','credential','password','private_key','api_key','authorization_header','session_cookie','secret','environment_secret')
OP_TYPES=('create_text_file','replace_text_file','delete_file','create_directory','rename_path')
def canonical_json(v:Any)->str: return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def fingerprint(v:Any)->str: return hashlib.sha256(canonical_json(v).encode()).hexdigest()
def sha256_text(s:str)->str: return hashlib.sha256(str(s).encode()).hexdigest()
def reasons(xs:Sequence[str])->list[str]: return sorted(set(str(x) for x in xs if x))
def artifact(prefix:str,schema:str,body:Mapping[str,Any],id_field:str)->dict[str,Any]:
 b=dict(body); b['schema']=schema; fp=fingerprint(b); b['fingerprint']=fp; b[id_field]=prefix+'-'+fp[:24]; return b
def bounded_int(v:Any,n:str,lo:int=0)->list[str]: return [] if type(v) is int and v>=lo else [n+'_invalid']
def seq(v:Any)->list[Any]: return list(v) if isinstance(v,(list,tuple)) else []
def ids(items:Sequence[Mapping[str,Any]],key:str)->list[Any]: return [x.get(key) for x in items]
def by_id(items:Sequence[Mapping[str,Any]],key='operation_id')->dict[Any,Mapping[str,Any]]: return {x.get(key):x for x in items}
def proposal_ops(proposal:Mapping[str,Any])->list[Mapping[str,Any]]: return seq(proposal.get('operations'))
def op_fingerprint(op:Mapping[str,Any])->str: return op.get('fingerprint') or fingerprint(op)
def target_fp(op:Mapping[str,Any])->str: return sha256_text(op.get('target_relative_path') or op.get('target_path') or op.get('target_relative_path_fingerprint') or '')
def content_fp(op:Mapping[str,Any])->Any: return op.get('proposed_content_fingerprint') or op.get('content_fingerprint')
def diff_fp_for(proposal:Mapping[str,Any],op:Mapping[str,Any])->Any:
 for d in seq(proposal.get('diffs')):
  if d.get('target_relative_path')==op.get('target_relative_path') or d.get('operation_id')==op.get('operation_id'): return d.get('fingerprint')
 return op.get('diff_fingerprint')
def pre_fp(op:Mapping[str,Any])->Any: return op.get('precondition_fingerprint')
def op_summary(proposal:Mapping[str,Any],op:Mapping[str,Any])->dict[str,Any]:
 return {'operation_id':op.get('operation_id'),'operation_fingerprint':op_fingerprint(op),'operation_type':op.get('operation_type'),'target_path_fingerprint':target_fp(op),'content_fingerprint':content_fp(op),'diff_fingerprint':diff_fp_for(proposal,op),'precondition_fingerprint':pre_fp(op),'expected_before_fingerprint':op.get('expected_before_fingerprint'),'expected_after_fingerprint':op.get('proposed_after_fingerprint') or op.get('expected_after_fingerprint')}
def selected_ops(proposal:Mapping[str,Any],operation_ids:Sequence[str])->list[Mapping[str,Any]]:
 m=by_id(proposal_ops(proposal)); return [m[i] for i in operation_ids if i in m]
def subset(child:Sequence[Any],parent:Sequence[Any])->bool: return set(child).issubset(set(parent))
def validate_false_invariants(*arts:Mapping[str,Any])->list[str]: return reasons([k+'_not_false' for a in arts for k in FALSE_FLAGS if k in a and a.get(k) is not False])
def validate_operator_identity(operator_id:Any,cls:Any,policy:Mapping[str,Any])->list[str]:
 rs=[]
 if not isinstance(operator_id,str) or not operator_id.strip(): rs.append('operator_id_invalid')
 if not isinstance(cls,str) or cls not in seq(policy.get('allowed_operator_identity_classes')): rs.append('operator_identity_class_not_allowed')
 return rs
def validate_handoff_chain(proposal,validation,safety,verification,closure,handoff)->list[str]:
 rs=[]
 if proposal.get('schema')!='zero.engineering.change_proposal.v1': rs.append('proposal_schema_invalid')
 if validation.get('status')!='valid': rs.append('validation_not_valid')
 if safety.get('status')!='approved_for_handoff': rs.append('safety_review_not_approved_for_handoff')
 if verification.get('status')!='verified': rs.append('verification_not_verified')
 if closure.get('status')!='closed': rs.append('proposal_closure_not_closed')
 if handoff.get('status')!='handed_off': rs.append('proposal_handoff_not_handed_off')
 vals=[x.get('proposal_id') for x in (proposal,validation,safety,verification,closure,handoff)]
 if len(set(vals))!=1: rs.append('proposal_linkage_mismatch')
 rs+=validate_false_invariants(proposal,handoff,closure)
 if handoff.get('operator_approval_obtained') is not False: rs.append('upstream_operator_approval_not_false')
 return reasons(rs)
def scope_ok(child:Sequence[str],parent:Sequence[str])->bool: return subset(child,parent)
def authority_ok(child:Sequence[str],parent:Sequence[str])->bool: return subset(child,parent)
def conflict_reasons(summaries:Sequence[Mapping[str,Any]])->list[str]:
 t=[x.get('target_path_fingerprint') for x in summaries if x.get('target_path_fingerprint')]
 rs=[]
 if len(t)!=len(set(t)): rs.append('duplicate_target_conflict')
 return rs
def prohibited_payload(v:Any,allow_content:bool=False)->list[str]:
 rs=[]
 def walk(x,path=''):
  if callable(x): rs.append('callable_payload'); return
  if isinstance(x,(bytes,bytearray,memoryview)): rs.append('binary_payload'); return
  if isinstance(x,dict):
   for k,val in x.items():
    key=str(k).lower().replace('-','_')
    if key in FALSE_FLAGS or key in ('executable','token_purpose','token_schema'):
     pass
    elif not (allow_content and key in ('content','proposed_content','review_content')) and any(t in key for t in PROHIBITED_TERMS): rs.append('prohibited_key_'+key)
    walk(val,path+'.'+key)
  elif isinstance(x,(list,tuple)):
   for y in x: walk(y,path)
  elif isinstance(x,str):
   low=x.lower()
   if any(t.replace('_',' ') in low for t in PROHIBITED_TERMS if t not in ('script','shell')): rs.append('prohibited_text')
 walk(v); return reasons(rs)
def counts(ops): return {'operation_count':len(ops),'file_count':len({x.get('target_path_fingerprint') for x in ops}),'content_byte_total':sum(int(x.get('content_byte_count') or 0) for x in ops),'diff_entry_total':sum(int(x.get('diff_entry_count') or 0) for x in ops)}
def ok_status(status,good,bad,rs): return good if not rs else bad
