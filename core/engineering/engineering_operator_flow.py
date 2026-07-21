from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from core.engineering.engineering_runtime_orchestrator_common import canonical_json, fingerprint
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact, load_session_store
from core.engineering.engineering_work_entry import create_engineering_work_request, admit_engineering_work, create_work_coordination, persist_work_entry, inspect_work_coordination, resume_work_coordination, WorkEntryError
from core.engineering.engineering_read_only_pipeline import create_read_only_pipeline, run_read_only_pipeline, inspect_read_only_pipeline, resume_read_only_pipeline
from core.engineering.engineering_approval_execution_activation import *

OPERATOR_FLOW_SCHEMA='zero.engineering.operator_flow.v1'
ACTIVE_TERMINAL={'completed','closed','invalid'}
NEXT_COMMAND={'no_active_work':'start','requires_repository_admission':'prepare','requires_repository_analysis':'prepare','requires_objective_definition':'prepare','requires_planning':'prepare','requires_proposal_PREPARATION':'prepare','requires_proposal_preparation':'prepare','requires_proposal_review':'prepare','requires_human_approval':'approval-summary','requires_authorization':'authorization-summary','requires_human_authorization':'authorization-summary','requires_execution_preparation':'prepare-execution','requires_adapter_admission':'admit-adapter','requires_execution':'preview','requires_explicit_execution_activation':'preview','requires_verification':'verify','requires_progress_evaluation':'evaluate-progress','requires_completion_review':'completion-review-summary','requires_human_completion_review':'completion-review-summary','requires_next_iteration_proposal':'next-iteration-summary','requires_human_reassessment':'reassessment-summary','blocked':'reassessment-summary','failed':'reassessment-summary','invalid':'inspect'}
COMMANDS=['start','status','inspect','prepare','review','approval-summary','attach-approval','authorization-summary','attach-authorization','prepare-execution','admit-adapter','preview','execute','verify','evaluate-progress','result','completion-review-summary','resume','verify-flow']

def _ref(a:Mapping[str,Any], id_key:str, fp_key:str)->dict[str,Any]:
    return {'schema':a.get('schema'),'artifact_identity':a.get(id_key),'artifact_fingerprint':a.get(fp_key),'session_id':a.get('session_id')}

def _canon(body:Mapping[str,Any])->dict[str,Any]:
    base={k:v for k,v in dict(body).items() if k not in {'operator_flow_id','operator_flow_fingerprint'}}
    fp=fingerprint(base)
    return {**base,'operator_flow_fingerprint':fp,'operator_flow_id':'engineering-operator-flow-'+fp[:32]}

def _session_dirs(store_root:Path):
    if not store_root.exists(): return []
    return [p for p in sorted(store_root.iterdir(), key=lambda x:x.name) if p.is_dir()]

def _load_bundle(store_root:Path, session_id:str)->dict[str,Any]:
    try: return load_session_store(store_root, session_id)
    except Exception: return {}

def _load_optional(store_root:Path, session_id:str, name:str):
    try: return read_session_artifact(store_root, session_id, name)
    except Exception: return None

def resolve_active_engineering_work(store_root:str|Path, *, session_id:str|None=None, coordination_id:str|None=None, work_request_id:str|None=None, include_terminal:bool=False)->dict[str,Any]:
    root=Path(store_root)
    candidates=[]
    for d in _session_dirs(root):
        sid=d.name
        if session_id and sid!=session_id: continue
        b=_load_bundle(root,sid); c=b.get('work-entry/coordination.json'); r=b.get('work-entry/request.json')
        if not c or not r: continue
        if coordination_id and c.get('coordination_id')!=coordination_id: continue
        if work_request_id and r.get('work_request_id')!=work_request_id: continue
        st=str(c.get('coordination_status') or c.get('current_stage'))
        if not include_terminal and (st in ACTIVE_TERMINAL or c.get('current_stage') in ACTIVE_TERMINAL): continue
        candidates.append({'session_id':sid,'coordination_id':c.get('coordination_id'),'work_request_id':r.get('work_request_id')})
    if not candidates: return {'resolution_status':'no_active_work','candidates':[],'error':'no_active_work'}
    if len(candidates)>1 and not (session_id or coordination_id or work_request_id): return {'resolution_status':'ambiguous_active_work','candidates':candidates,'error':'ambiguous_active_work'}
    chosen=candidates[0]; b=_load_bundle(root,chosen['session_id'])
    return {'resolution_status':'resolved','session_id':chosen['session_id'],'bundle':b,'candidate':chosen}

def _phase(coord, pipe, activation):
    if activation:
        m={'awaiting_approval':'awaiting_approval','awaiting_authorization':'awaiting_authorization','preparing_execution':'execution_preparation','ready_for_execution':'ready_for_execution','awaiting_verification':'verification','verification_completed':'progress_evaluation','awaiting_completion_review':'awaiting_completion_review','next_iteration_candidate':'next_iteration_candidate','blocked':'blocked','failed':'failed','completed':'completed','invalid':'invalid'}
        return m.get(str(activation.get('current_stage')),'invalid')
    if pipe:
        if pipe.get('pipeline_status')=='awaiting_human_approval': return 'awaiting_approval'
        return 'read_only_preparation' if pipe.get('pipeline_status')!='created' else 'intake'
    return 'intake' if coord else 'not_started'

def build_operator_flow(bundle:Mapping[str,Any])->dict[str,Any]:
    req=bundle.get('work-entry/request.json') or {}; coord=bundle.get('work-entry/coordination.json') or {}; pipe=bundle.get('work-entry/pipeline.json'); act=bundle.get('work-entry/execution-activation.json')
    phase=_phase(coord,pipe,act); action=(act or pipe or coord).get('next_governed_action','no_active_work')
    status='awaiting_human_action' if action in {'requires_human_approval','requires_human_authorization','requires_human_completion_review','requires_human_reassessment'} else 'ready' if phase=='ready_for_execution' else 'active'
    if phase in {'blocked'}: status='blocked'
    if phase in {'failed'}: status='failed'
    if phase in {'completed','closed'}: status='completed'
    if phase=='invalid': status='invalid'
    body={'schema':OPERATOR_FLOW_SCHEMA,'work_request_reference':_ref(req,'work_request_id','work_request_fingerprint') if req else None,'coordination_reference':_ref(coord,'coordination_id','coordination_fingerprint') if coord else None,'runtime_session_reference':coord.get('runtime_session_reference') or {},'read_only_pipeline_reference':_ref(pipe,'pipeline_id','pipeline_fingerprint') if pipe else None,'approval_execution_activation_reference':_ref(act,'activation_id','activation_fingerprint') if act else None,'current_phase':phase,'overall_status':status,'next_operator_action':NEXT_COMMAND.get(action,'inspect'),'human_action_required':status=='awaiting_human_action','available_commands':COMMANDS,'blocked_reasons':(act or pipe or coord).get('blocked_reasons',[]),'latest_summary_references':{}}
    return _canon(body)

def build_operator_status(store_root:str|Path, **ids)->dict[str,Any]:
    res=resolve_active_engineering_work(store_root, **ids)
    if res['resolution_status']!='resolved': return {'schema':'zero.engineering.operator_status.v1','resolution':res,'operator_flow_status':'not_initialized','next_operator_action':NEXT_COMMAND.get(res['error'],'start'),'human_action_required':False}
    b=res['bundle']; req=b.get('work-entry/request.json',{}); coord=b.get('work-entry/coordination.json',{}); pipe=b.get('work-entry/pipeline.json'); act=b.get('work-entry/execution-activation.json'); appr=b.get('work-entry/approval.json'); auth=b.get('work-entry/authorization.json')
    flow=build_operator_flow(b); ins=inspect_work_coordination(coord); rins=inspect_read_only_pipeline(coord,pipe,_stage_artifacts(b)) if pipe else {'read_only_pipeline_status':'not_initialized'}; ains=inspect_activation(act,approval=appr,authorization=auth)
    return {'schema':'zero.engineering.operator_status.v1','resolution':{'resolution_status':'resolved','session_id':res['session_id']},'operator_flow':flow,'work_request_statement':req.get('request_statement'),'requested_mode':req.get('requested_mode'),'repository_identity':req.get('repository_identity'),'runtime_session_id':res['session_id'],'coordination_stage':ins.get('current_stage'),'read_only_pipeline_stage':rins.get('pipeline_current_stage'),'approval_status':ains.get('approval_status','pending' if flow['current_phase']=='awaiting_approval' else 'not_started'),'authorization_status':ains.get('authorization_status','not_started'),'authorization_consumption_state':ains.get('authorization_consumption_state','not_attached'),'execution_readiness':ains.get('execution_readiness',False),'execution_status':ains.get('execution_status') or 'not_started','verification_status':ains.get('verification_status') or 'not_started','objective_progress':ains.get('objective_progress_status','not_started'),'completion_readiness':ains.get('completion_readiness') or 'not_evaluated','iteration_health':ains.get('iteration_health','not_evaluated'),'human_action_required':flow['human_action_required'],'next_operator_action':flow['next_operator_action'],'recommended_command':'zero engineering '+flow['next_operator_action'],'timeline':_timeline(rins,ains),'blocked_reasons':flow['blocked_reasons']}

def _stage_artifacts(b):
    names={'repository-admission':'repository_admission','repository-analysis':'repository_analysis_closure','objective-definition':'objective','planning':'planning_closure','proposal-preparation':'engineering_proposal','proposal-review':'proposal_review_closure'}; out={}
    for f,k in names.items():
        v=b.get('work-entry/stages/'+f+'.json')
        if isinstance(v,dict): out.update(v.get('artifacts',{})); out[k]=out.get(k) or v.get(k)
    return out

def _timeline(rins,ains):
    base=['Work Request','Repository Analysis','Objective Definition','Engineering Planning','Proposal Preparation','Proposal Review','Human Approval','Human Authorization','Execution Preparation','Adapter Admission','Controlled Execution','Verification','Completion Review']
    done={x['stage'] for x in rins.get('timeline',[]) if x.get('status')=='Completed'}|{x['stage'] for x in ains.get('timeline',[]) if x.get('status')=='Completed'}
    pend={x['stage'] for x in ains.get('timeline',[]) if x.get('status')=='Pending'}
    return [{'stage':s,'status':'Completed' if s in done else 'Pending' if s in pend else 'Not Started'} for s in base]

def start_operator_flow(statement, *, store_root, repository, repo_id='default', scope=('docs/status.txt',), mode='governed_delivery', acceptance_intent='ZERO engineering flow verified.', prepare=False):
    req=create_engineering_work_request(request_statement=statement, repository_identity={'repository_id':repo_id}, repository_root_reference='.', requested_scope=list(scope), requested_mode=mode, acceptance_intent=acceptance_intent)
    intake=admit_engineering_work(req); coord=create_work_coordination(req,intake); sid=coord['runtime_session_reference']['artifact_identity']; pipe=create_read_only_pipeline(req,intake,coord); persist_work_entry(store_root,sid,request=req,intake=intake,coordination=coord); write_session_artifact(store_root,sid,'work-entry/pipeline.json',pipe)
    out={'work_request':req,'work_intake':intake,'coordination':coord,'read_only_pipeline':pipe,'operator_flow':build_operator_flow({'work-entry/request.json':req,'work-entry/coordination.json':coord,'work-entry/pipeline.json':pipe})}
    if prepare: out['prepare_result']=prepare_operator_flow(store_root,session_id=sid,repository=repository)
    return out

def prepare_operator_flow(store_root, *, repository='.', session_id=None, **ids):
    st=resolve_active_engineering_work(store_root, session_id=session_id, **ids); b=st['bundle']; out=run_read_only_pipeline(b['work-entry/request.json'],b['work-entry/intake.json'],b['work-entry/coordination.json'],b['work-entry/pipeline.json'],repository_root=repository,artifacts=_stage_artifacts(b)); sid=st['session_id']
    write_session_artifact(store_root,sid,'work-entry/coordination.json',out['coordination']); write_session_artifact(store_root,sid,'work-entry/pipeline.json',out['pipeline'])
    for sr in out.get('stage_results',[]): write_session_artifact(store_root,sid,'work-entry/stages/'+sr['stage'].replace('_','-')+'.json',{'stage_result':sr,'artifacts':out['artifacts']})
    if 'human_gate_handoff' in out['artifacts']: write_session_artifact(store_root,sid,'work-entry/human-gate-handoff.json',out['artifacts']['human_gate_handoff'])
    return out

def create_demo_activation(store_root, *, session_id=None, repository='.', path='docs/status.txt', content='ZERO engineering flow verified.\n'):
    res=resolve_active_engineering_work(store_root, session_id=session_id); b=res['bundle']; arts=_stage_artifacts(b); sess={'session_id':res['session_id'],'schema':'zero.engineering.runtime_session.v1','fingerprint':b['work-entry/coordination.json']['runtime_session_reference']['artifact_fingerprint']}
    act=create_activation(work_request=b['work-entry/request.json'],coordination=b['work-entry/coordination.json'],runtime_session=sess,read_only_pipeline=b['work-entry/pipeline.json'],proposal=arts['engineering_proposal'],proposal_review=arts['proposal_review_closure'],workspace_reference={'workspace_root':str(Path(repository).resolve()),'allowed_scope':[path]},ordered_operations=[{'operation':'create_text_file','path':path,'content':content}])
    persist_activation_artifacts(store_root,res['session_id'],activation=act); return act

def preview_execution(store_root, *, session_id=None, repository='.'):
    b=resolve_active_engineering_work(store_root, session_id=session_id)['bundle']; act=b.get('work-entry/execution-activation.json'); auth=b.get('work-entry/authorization.json'); prep=b.get('work-entry/execution-preparation.json')
    ops=act.get('ordered_operations',[]) if act else []
    before={op['path']:(Path(repository)/op['path']).read_text(encoding='utf-8') if (Path(repository)/op['path']).exists() else None for op in ops}
    return {'schema':'zero.engineering.execution_preview.v1','preview_status':'ready' if prep else 'preview_limited','workspace':str(Path(repository).resolve()),'adapter':'zero.text_file_create','ordered_operations':ops,'target_paths':[op['path'] for op in ops],'current_before_state_hashes':prep.get('before_state_evidence') if prep else {},'current_content_summary':before,'expected_changed_paths':[op['path'] for op in ops],'expected_unchanged_paths':[],'authorization_actor':(auth or {}).get('human_actor'),'authorization_consumption_state':(auth or {}).get('consumption_state','not_attached'),'execution_readiness':bool(prep and act and act.get('current_stage')=='ready_for_execution'),'blocking_conditions':[] if prep else ['preview_limited'],'mutation_occurred':False}

def human_text(payload, verbose=False):
    if 'work_request_statement' in payload:
        return '\n'.join(['工程任務：'+str(payload.get('work_request_statement')),'目前階段：'+str(payload.get('operator_flow',{}).get('current_phase')),'批准：'+str(payload.get('approval_status')),'授權：'+str(payload.get('authorization_status')),'執行：'+str(payload.get('execution_status')),'是否需要人類操作：'+('是' if payload.get('human_action_required') else '否'),'下一步：'+str(payload.get('recommended_command')),'治理警告：摘要不是批准、授權、執行或完成決策。'])
    return 'ZERO 工程操作者流程\n'+canonical_json(payload)
