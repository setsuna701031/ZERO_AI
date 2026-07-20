from __future__ import annotations
from typing import Any, Mapping
from .engineering_task_orchestration_validation import *
from .engineering_task_orchestration_persistence import save_state, load_state
from .engineering_task_orchestration_closure import build_task_closure
from .engineering_task_artifact_adapter_registry import default_registry
from .engineering_task_artifact_reference import mutable_reference
from .engineering_repair_candidate_validation import validate_engineering_repair_candidate
from .engineering_repair_plan_validation import validate_engineering_repair_plan
from .engineering_completion_foundation import validate_proposal_linkage, validate_verification_result, validate_completion, SUCCESS_VERIFICATION_STATUSES

class OrchestrationError(ValueError): pass

def seal_state(s:Mapping[str,Any])->dict[str,Any]:
    d=dict(s); d['state_fingerprint']=state_fingerprint({k:v for k,v in d.items() if k!='state_fingerprint'}); return d

def _persist(repo_root, s): return save_state(repo_root, seal_state(s))
def _load(repo_root, task_id): return load_state(repo_root, task_id)
def _ensure(s, state):
    if s.get('terminal'): raise OrchestrationError('terminal_state_immutable')
    if s.get('lifecycle_state')!=state: raise OrchestrationError('out_of_order_artifact')
def _phase_adapter_name(key:str)->str:
    return {
        'analysis_identity':'analysis', 'candidate_identity':'candidate_selection', 'plan_identity':'repair_plan',
        'proposal_identity':'proposal', 'approval_identity':'approval', 'authorization_identity':'authorization',
        'authorized_scope_identity':'authorized_scope', 'preparation_identity':'preparation',
        'authorization_token_identity':'authorization_token', 'verification_identity':'verification',
    }.get(key, key.removesuffix('_identity'))

def _attach(repo_root,s,phase,key,artifact,next_state,pending=None,schema=None,statuses=None,id_keys=()):
    if s.get('terminal'):
        raise OrchestrationError('terminal_state_immutable')
    ref = mutable_reference(default_registry().validate_artifact(_phase_adapter_name(key), artifact))
    existing=s.get(key)
    if existing:
        if existing.get('artifact_identity')==ref.get('artifact_identity') and existing.get('artifact_fingerprint')==ref.get('artifact_fingerprint'):
            return s
        raise OrchestrationError('conflicting_artifact_replay')
    _ensure(s, phase)
    if artifact.get('task_id') not in (None,s.get('task_id')): raise OrchestrationError('task_id_mismatch')
    if artifact.get('repository_identity') not in (None,s.get('repository_identity')): raise OrchestrationError('repository_identity_mismatch')
    n=dict(s); n[key]=ref; n['completed_phases']=list(dict.fromkeys([*n.get('completed_phases',[]), next_state])); n['lifecycle_state']=next_state; n['lifecycle_revision']=n.get('lifecycle_revision',0)+1; n['pending_requirement']=pending
    return _persist(repo_root,n)

def create_task(repo_root, request):
    req=canonical_request(request); tid,tfp=task_identity(req)
    state={'schema':STATE_SCHEMA,'task_id':tid,'task_fingerprint':tfp,'repository_identity':req['repository_identity'],'request_identity':stable_ref(req,'request_id'),'request':req,'lifecycle_state':'requested','lifecycle_revision':0,'analysis_identity':None,'candidate_identity':None,'plan_identity':None,'proposal_identity':None,'approval_identity':None,'authorization_identity':None,'authorized_scope_identity':None,'preparation_identity':None,'authorization_token_identity':None,'preparation_token_identity':None,'executor_handoff_identity':None,'transaction_identity':None,'execution_result_identity':None,'verification_identity':None,'completion_identity':None,'closure_identity':None,'proposal_linkage_identity':None,'verification_linkage':None,'completion_linkage':None,'transaction_evidence_linkage':None,'completed_phases':['requested'],'pending_requirement':'task_admission','failure':None,'terminal':False,'execution_started':False,'execution_completed':False,'execution_replay_prohibited':False}
    return _persist(repo_root,state)

def admit_task(repo_root, task_id):
    s=_load(repo_root,task_id); _ensure(s,'requested'); n=dict(s); n['lifecycle_state']='admitted'; n['lifecycle_revision']+=1; n['pending_requirement']='analysis'; n['completed_phases'].append('admitted'); return _persist(repo_root,n)
def attach_analysis(repo_root,task_id,a): return _attach(repo_root,_load(repo_root,task_id),'admitted','analysis_identity',a,'analysis_ready','candidate_selection')
def attach_candidate_selection(repo_root,task_id,a):
    s=_load(repo_root,task_id)
    analysis=s.get('analysis_identity') or {}
    r=validate_engineering_repair_candidate(a, task_id=s.get('task_id'), repository_identity=s.get('repository_identity'), analysis_identity=analysis.get('artifact_identity'), analysis_fingerprint=analysis.get('artifact_fingerprint'), request_scope=s.get('request',{}).get('bounded_target_scope'))
    if not r.valid: raise OrchestrationError('candidate_validation_failed:'+','.join(r.errors))
    return _attach(repo_root,s,'analysis_ready','candidate_identity',a,'candidate_selected','repair_plan')
def attach_plan(repo_root,task_id,a):
    s=_load(repo_root,task_id)
    if not s.get('candidate_identity'): raise OrchestrationError('candidate_required')
    cref=s.get('candidate_identity') or {}
    if a.get('candidate_identity')!=cref.get('artifact_identity') or a.get('candidate_fingerprint')!=cref.get('artifact_fingerprint'): raise OrchestrationError('candidate_linkage_mismatch')
    candidate_context={'selection_status':'selected','candidate_id':cref.get('artifact_identity'),'fingerprint':cref.get('artifact_fingerprint'),'target_scope':cref.get('bounded_summary',{}).get('target_scope',[]),'prohibited_scope':cref.get('bounded_summary',{}).get('prohibited_scope',[]),'analysis_identity':(s.get('analysis_identity') or {}).get('artifact_identity'),'repository_identity':s.get('repository_identity')}
    r=validate_engineering_repair_plan(a, candidate=candidate_context, task_id=s.get('task_id'), repository_identity=s.get('repository_identity'), analysis_identity=(s.get('analysis_identity') or {}).get('artifact_identity'), request_scope=s.get('request',{}).get('bounded_target_scope'))
    if not r.valid: raise OrchestrationError('plan_validation_failed:'+','.join(r.errors))
    return _attach(repo_root,s,'candidate_selected','plan_identity',a,'plan_ready','proposal')

def attach_proposal(repo_root,task_id,a):
    s=_load(repo_root,task_id)
    if s.get('terminal'): raise OrchestrationError('terminal_state_immutable')
    existing=s.get('proposal_identity')
    proposal=a.get('proposal') if isinstance(a,dict) and a.get('proposal_linkage') else a
    linkage=a.get('proposal_linkage') if isinstance(a,dict) else None
    if not linkage: raise OrchestrationError('proposal_linkage_required')
    if existing:
        pref=mutable_reference(default_registry().validate_artifact('proposal', proposal))
        lref=mutable_reference(default_registry().validate_artifact('proposal_linkage', linkage))
        if existing.get('artifact_identity')==pref.get('artifact_identity') and existing.get('artifact_fingerprint')==pref.get('artifact_fingerprint') and (s.get('proposal_linkage_identity') or {}).get('artifact_fingerprint')==lref.get('artifact_fingerprint'):
            return s
        raise OrchestrationError('conflicting_artifact_replay')
    _ensure(s,'plan_ready')
    analysis=s.get('analysis_identity') or {}; cand=s.get('candidate_identity') or {}; plan=s.get('plan_identity') or {}
    r=validate_proposal_linkage(linkage, task_id=s.get('task_id'), repository_identity=s.get('repository_identity'), analysis=analysis, candidate=cand, repair_plan={'repair_plan_id':plan.get('artifact_identity'),'fingerprint':plan.get('artifact_fingerprint'), **(plan.get('bounded_summary') or {})}, proposal=proposal)
    if not r.valid: raise OrchestrationError('proposal_linkage_validation_failed:'+','.join(r.errors))
    n=_attach(repo_root,s,'plan_ready','proposal_identity',proposal,'awaiting_human_approval','human_approval')
    n=dict(n); n['proposal_linkage_identity']=mutable_reference(default_registry().validate_artifact('proposal_linkage', linkage)); return _persist(repo_root,n)

def attach_human_approval(repo_root,task_id,a):
    s=_load(repo_root,task_id)
    if a.get('status') not in ('approved','verified') and a.get('decision')!='approved': raise OrchestrationError('approval_not_positive')
    return _attach(repo_root,s,'awaiting_human_approval','approval_identity',a,'approved','formal_authorization')
def attach_authorization(repo_root,task_id,a):
    s=_load(repo_root,task_id)
    r=_attach(repo_root,s,'approved','authorization_identity',a,'authorized','preparation',statuses={'verified','authorized'})
    if a.get('authorized_scope_id'): r=dict(r); r['authorized_scope_identity']={'id':a.get('authorized_scope_id'),'fingerprint':a.get('authorized_scope_fingerprint'),'schema':a.get('authorized_scope_schema')}; r=_persist(repo_root,r)
    return r
def attach_preparation(repo_root,task_id,a): return _attach(repo_root,_load(repo_root,task_id),'authorized','preparation_identity',a,'prepared','authorization_token',statuses={'closed','ready','prepared'})
def attach_authorization_token(repo_root,task_id,a):
    s=_load(repo_root,task_id)
    if a.get('token_consumed') is not False or a.get('use_limit') not in (None,1): raise OrchestrationError('token_not_single_use_available')
    r=_attach(repo_root,s,'prepared','authorization_token_identity',a,'execution_ready','execute',statuses={'issued'})
    tx=a.get('transaction_id') or a.get('mutation_transaction_id')
    if tx: r=dict(r); r['transaction_identity']={'id':tx,'fingerprint':a.get('transaction_fingerprint'),'schema':a.get('transaction_schema')}; r=_persist(repo_root,r)
    return r
def execute_task(repo_root,task_id,handoff,workspace_root):
    s=_load(repo_root,task_id); _ensure(s,'execution_ready')
    href=mutable_reference(default_registry().validate_artifact('executor_handoff', handoff))
    for req in ('proposal_identity','approval_identity','authorization_identity','preparation_identity','authorization_token_identity'):
        if not s.get(req): raise OrchestrationError('missing_canonical_'+req)
    if s.get('execution_started') or s.get('execution_completed'): raise OrchestrationError('execution_replay_prohibited')
    existing_h=s.get('executor_handoff_identity')
    if existing_h and (existing_h.get('artifact_identity')!=href.get('artifact_identity') or existing_h.get('artifact_fingerprint')!=href.get('artifact_fingerprint')): raise OrchestrationError('executor_handoff_mismatch')
    n=dict(s); n['executor_handoff_identity']=href; n['execution_started']=True; n['execution_replay_prohibited']=True; n['lifecycle_state']='executing'; n['lifecycle_revision']+=1; _persist(repo_root,n)
    from core.engineering.engineering_governed_workspace_mutation_executor import execute_pipeline
    result=execute_pipeline(handoff,workspace_root,execute_confirmed=True)
    m=dict(n); m['execution_completed']=True; m['lifecycle_state']='executed'; m['pending_requirement']='verification'; m['completed_phases']=list(dict.fromkeys([*m.get('completed_phases',[]),'executed']))
    res=result.get('result') or result.get('failure') or result
    m['execution_result_identity']=mutable_reference(default_registry().validate_artifact('execution_result', res))
    if result.get('execution_evidence'): m['transaction_evidence_linkage']=stable_ref(result['execution_evidence'],'evidence_id')
    if result.get('execution_closure'): m['transaction_closure_identity']=stable_ref(result['execution_closure'],'closure_id')
    if result.get('failure'): m['failure']={'code':'governed_execution_failed','detail':stable_ref(result['failure'])}
    return _persist(repo_root,m)

def attach_verification_result(repo_root,task_id,a):
    s=_load(repo_root,task_id)
    if s.get('verification_identity'):
        ref=mutable_reference(default_registry().validate_artifact('verification_result', a))
        if s['verification_identity'].get('artifact_identity')==ref.get('artifact_identity') and s['verification_identity'].get('artifact_fingerprint')==ref.get('artifact_fingerprint'): return s
        raise OrchestrationError('conflicting_artifact_replay')
    _ensure(s,'executed')
    if not s.get('proposal_identity') or not s.get('execution_result_identity'): raise OrchestrationError('proposal_and_execution_required')
    plan=s.get('plan_identity') or {}
    r=validate_verification_result(a, task_id=s.get('task_id'), repository_identity=s.get('repository_identity'), proposal=s.get('proposal_identity') or {}, repair_plan={'repair_plan_id':plan.get('artifact_identity'),'fingerprint':plan.get('artifact_fingerprint'), **(plan.get('bounded_summary') or {})}, execution_result=s.get('execution_result_identity') or {})
    if not r.valid: raise OrchestrationError('verification_validation_failed:'+','.join(r.errors))
    ref=mutable_reference(default_registry().validate_artifact('verification_result', a))
    n=dict(s); n['verification_identity']=ref; n['completed_phases']=list(dict.fromkeys([*n.get('completed_phases',[]),'verified'])); n['lifecycle_state']='verified'; n['lifecycle_revision']=n.get('lifecycle_revision',0)+1; n['pending_requirement']='completion'
    n['verification_linkage']={'proposal_identity':a.get('proposal_identity'),'repair_plan_identity':a.get('repair_plan_identity'),'execution_identity':a.get('execution_identity')}; return _persist(repo_root,n)

def attach_verification(repo_root,task_id,a):
    if isinstance(a,dict) and a.get('schema')=='zero.engineering.verification_result.v1': return attach_verification_result(repo_root,task_id,a)
    s=_load(repo_root,task_id); _ensure(s,'executed')
    if a.get('task_id')!=s.get('task_id'): raise OrchestrationError('task_id_mismatch')
    if a.get('transaction_identity')!=s.get('transaction_identity'): raise OrchestrationError('transaction_identity_mismatch')
    if a.get('status')!='passed' or a.get('failed_count',0)!=0: raise OrchestrationError('verification_not_successful')
    exp=set(s.get('request',{}).get('requested_verification_expectations') or [])
    if not exp.issubset(set(a.get('performed_verification_set') or [])): raise OrchestrationError('verification_incomplete')
    return _attach(repo_root,s,'executed','verification_identity',a,'verified','closure',schema=VERIFICATION_SCHEMA,statuses={'passed'},id_keys=('verification_id',))

def attach_completion(repo_root,task_id,a):
    s=_load(repo_root,task_id)
    if s.get('terminal'): raise OrchestrationError('terminal_state_immutable')
    if s.get('completion_identity'):
        ref=mutable_reference(default_registry().validate_artifact('completion', a))
        if s['completion_identity'].get('artifact_identity')==ref.get('artifact_identity') and s['completion_identity'].get('artifact_fingerprint')==ref.get('artifact_fingerprint'): return s
        raise OrchestrationError('conflicting_artifact_replay')
    _ensure(s,'verified')
    verification=s.get('verification_identity') or {}
    if verification.get('validation_status') not in SUCCESS_VERIFICATION_STATUSES: raise OrchestrationError('verification_not_successful')
    r=validate_completion(a, task_id=s.get('task_id'), repository_identity=s.get('repository_identity'), proposal=s.get('proposal_identity') or {}, verification_result=verification)
    if not r.valid: raise OrchestrationError('completion_validation_failed:'+','.join(r.errors))
    n=_attach(repo_root,s,'verified','completion_identity',a,'completed','closure')
    n=dict(n); n['completion_linkage']={'proposal_identity':a.get('proposal_identity'),'verification_result_identity':a.get('verification_result_identity'),'closure_eligibility':a.get('closure_eligibility')}; return _persist(repo_root,n)

def close_task(repo_root,task_id):
    s=_load(repo_root,task_id); _ensure(s,'completed')
    closure=build_task_closure(s); n=dict(s); n['closure_identity']={'schema':closure['schema'],'id':closure['closure_id'],'fingerprint':closure['closure_fingerprint']}; n['closure']=closure; n['lifecycle_state']='closed'; n['terminal']=True; n['pending_requirement']=None; n['completed_phases']=list(dict.fromkeys([*n.get('completed_phases',[]),'closed'])); n['lifecycle_revision']+=1
    return _persist(repo_root,n)
def inspect_task(repo_root,task_id): return _load(repo_root,task_id)
