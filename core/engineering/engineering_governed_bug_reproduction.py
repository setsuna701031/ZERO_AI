from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.engineering.engineering_multifile_coding_workflow import canon, run_bounded_test_set
from core.engineering.engineering_practical_task_runner import _ref, safe_path
from core.engineering.engineering_runtime_orchestrator_common import fingerprint

REQUEST_SCHEMA='zero.engineering.bug_reproduction_request_candidate.v1'
CONFIRMATION_SCHEMA='zero.engineering.bug_reproduction_confirmation.v1'
ADMISSION_SCHEMA='zero.engineering.bounded_test_admission.v1'
RESULT_SCHEMA='zero.engineering.bug_reproduction_result.v1'
AUTHORITY={'may_modify_repository':False,'may_approve':False,'may_authorize':False,'may_retry':False,'may_complete':False}
STORE_FILES={'request':'reproduction/request.json','confirmation':'reproduction/confirmation.json','admission':'reproduction/admission.json','result':'reproduction/result.json','test_set':'testing/test-set-result.json','failure_evidence':'testing/failure-evidence.json','repair_candidate':'feedback/repair-candidate.json','repair_review':'feedback/repair-review.json'}

class ReproductionError(ValueError):
    def __init__(self,code): super().__init__(code); self.code=code

def capture_workspace_snapshot(root:str|Path, targets:Sequence[str])->dict[str,Any]:
    base=Path(root).resolve(); files=[]
    for target in sorted(set(str(x).split('::')[0].replace('\\','/') for x in targets)):
        p=safe_path(base,target)
        if not p.is_file(): raise ReproductionError('test_target_not_found')
        files.append({'path':target,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size})
    body={'schema':'zero.engineering.bounded_workspace_snapshot.v1','repository_root':str(base),'files':files}
    return canon(body,'workspace_snapshot_fingerprint','workspace_snapshot_id','engineering-workspace-snapshot-')

def _target_ok(target:str)->bool:
    value=str(target).replace('\\','/')
    if not value or value.startswith('/') or '..' in value.split('/') or value.count('::')>2: return False
    path,*node=value.split('::')
    if not path.startswith('tests/') or not path.endswith('.py'): return False
    return not node or all(part and all(c.isalnum() or c in '_-[]' for c in part) for part in node)

def build_reproduction_request_candidate(*,work_request:Mapping[str,Any],confirmed_specification:Mapping[str,Any],human_plan_confirmation:Mapping[str,Any],repository_analysis:Mapping[str,Any],repository_identity:Mapping[str,Any],confirmed_scope:Sequence[str],target_test_files:Sequence[str],target_test_nodes:Sequence[str]=(),expected_behavior:str,observed_behavior:str,reproduction_steps:Sequence[str],workspace_snapshot:Mapping[str,Any],session_id:str,timeout_seconds:int=120,stop_policy:str='first_failure')->dict[str,Any]:
    if human_plan_confirmation.get('decision')!='confirmed': raise ReproductionError('human_plan_confirmation_required')
    targets=list(target_test_nodes or target_test_files)
    body={'schema':REQUEST_SCHEMA,'session_id':session_id,'work_request_reference':_ref(work_request),'confirmed_specification_reference':_ref(confirmed_specification),'human_plan_confirmation_reference':_ref(human_plan_confirmation),'repository_analysis_reference':_ref(repository_analysis),'repository_identity':dict(repository_identity),'workspace_snapshot_reference':_ref(workspace_snapshot),'confirmed_scope':list(confirmed_scope),'target_test_files':list(target_test_files),'target_test_nodes':list(target_test_nodes),'expected_behavior':expected_behavior,'observed_behavior':observed_behavior,'reproduction_steps':list(reproduction_steps),'environment_constraints':{'runner':'python -m pytest','network':False,'package_installation':False,'git':False},'timeout_policy':{'seconds':int(timeout_seconds),'maximum_seconds':120},'stop_policy':stop_policy,'evidence_requirements':['bounded stdout','bounded stderr','bounded repository-relative traceback'],'authority':AUTHORITY}
    candidate=canon(body,'reproduction_request_fingerprint','reproduction_request_id','engineering-reproduction-request-')
    errors=validate_reproduction_request(candidate,workspace_snapshot=workspace_snapshot,session_id=session_id)
    if errors: raise ReproductionError(errors[0])
    return candidate

def validate_reproduction_request(value:Mapping[str,Any],*,workspace_snapshot:Mapping[str,Any]|None=None,session_id:str|None=None)->list[str]:
    errors=[]; material={k:v for k,v in value.items() if k not in {'reproduction_request_id','reproduction_request_fingerprint'}}; expected=canon(material,'reproduction_request_fingerprint','reproduction_request_id','engineering-reproduction-request-')
    if value.get('schema')!=REQUEST_SCHEMA: errors.append('schema_invalid')
    if expected!=value: errors.append('wrong_reproduction_request_fingerprint')
    if session_id and value.get('session_id')!=session_id: errors.append('session_mismatch')
    if not value.get('human_plan_confirmation_reference'): errors.append('human_plan_confirmation_required')
    if not value.get('work_request_reference'): errors.append('missing_work_request')
    if not value.get('repository_identity'): errors.append('wrong_repository_identity')
    targets=value.get('target_test_nodes') or value.get('target_test_files') or []
    if not targets: errors.append('missing_test_target')
    if len(targets)>8: errors.append('maximum_targets_exceeded')
    if any(not _target_ok(t) for t in targets): errors.append('unsafe_test_target')
    scope=value.get('confirmed_scope') or []
    if any(not any(str(t).split('::')[0]==s or str(t).split('::')[0].startswith(str(s).rstrip('/')+'/') for s in scope) for t in targets): errors.append('scope_expansion')
    if value.get('stop_policy') not in {'first_failure','continue'}: errors.append('invalid_stop_policy')
    timeout=(value.get('timeout_policy') or {}).get('seconds')
    if not isinstance(timeout,int) or timeout<1 or timeout>120: errors.append('invalid_timeout')
    if any(value.get('authority',{}).get(k) for k in AUTHORITY): errors.append('candidate_with_authority')
    if workspace_snapshot and value.get('workspace_snapshot_reference')!=_ref(workspace_snapshot): errors.append('workspace_drift')
    return sorted(set(errors))

def confirm_reproduction_request(request:Mapping[str,Any],confirmation:Mapping[str,Any])->dict[str,Any]:
    if not confirmation.get('human_actor'): raise ReproductionError('human_actor_required')
    ref=confirmation.get('reproduction_request_reference') or {}
    if ref!=_ref(request): raise ReproductionError('stale_confirmation')
    decision=confirmation.get('decision')
    if decision not in {'confirmed','rejected','requires_revision'}: raise ReproductionError('invalid_confirmation_decision')
    body={'schema':CONFIRMATION_SCHEMA,'reproduction_request_reference':_ref(request),'confirmed_test_targets':list(confirmation.get('confirmed_test_targets') or request.get('target_test_nodes') or request.get('target_test_files') or []),'confirmed_scope':list(confirmation.get('confirmed_scope') or request.get('confirmed_scope') or []),'timeout_acknowledgement':bool(confirmation.get('timeout_acknowledgement')),'environment_acknowledgement':bool(confirmation.get('environment_acknowledgement')),'human_actor':confirmation['human_actor'],'decision':decision,'authority':AUTHORITY}
    if decision=='confirmed' and (not body['timeout_acknowledgement'] or not body['environment_acknowledgement']): raise ReproductionError('missing_human_acknowledgement')
    return canon(body,'reproduction_confirmation_fingerprint','reproduction_confirmation_id','engineering-reproduction-confirmation-')

def admit_bounded_reproduction(request:Mapping[str,Any],confirmation:Mapping[str,Any],*,workspace_snapshot:Mapping[str,Any],repository_identity:Mapping[str,Any],session_id:str)->dict[str,Any]:
    errors=validate_reproduction_request(request,workspace_snapshot=workspace_snapshot,session_id=session_id)
    if confirmation.get('decision')!='confirmed': errors.append('human_reproduction_confirmation_required')
    if confirmation.get('reproduction_request_reference')!=_ref(request): errors.append('stale_confirmation')
    if dict(request.get('repository_identity') or {})!=dict(repository_identity): errors.append('wrong_repository_identity')
    targets=confirmation.get('confirmed_test_targets') or []
    if sorted(targets)!=sorted(request.get('target_test_nodes') or request.get('target_test_files') or []): errors.append('scope_expansion')
    if any(not _target_ok(t) for t in targets): errors.append('unsafe_test_target')
    status='admitted' if not errors else 'rejected'
    body={'schema':ADMISSION_SCHEMA,'session_id':session_id,'reproduction_request_reference':_ref(request),'human_confirmation_reference':_ref(confirmation),'workspace_snapshot_reference':_ref(workspace_snapshot),'repository_identity':dict(repository_identity),'confirmed_test_targets':list(targets),'timeout_seconds':request.get('timeout_policy',{}).get('seconds'),'stop_policy':request.get('stop_policy'),'single_use':True,'consumption_state':'unconsumed','admission_status':status,'reason_codes':sorted(set(errors)),'authority':AUTHORITY}
    return canon(body,'test_admission_fingerprint','test_admission_id','engineering-test-admission-')

def run_reproduction(request:Mapping[str,Any],confirmation:Mapping[str,Any],admission:Mapping[str,Any],*,workspace_root:str|Path,workspace_snapshot:Mapping[str,Any]):
    if admission.get('admission_status')!='admitted': raise ReproductionError('test_admission_required')
    if admission.get('consumption_state')!='unconsumed': raise ReproductionError('replayed_admission')
    current=capture_workspace_snapshot(workspace_root,admission.get('confirmed_test_targets') or [])
    if current.get('workspace_snapshot_fingerprint')!=workspace_snapshot.get('workspace_snapshot_fingerprint'): raise ReproductionError('workspace_drift')
    test_set=run_bounded_test_set({},admission['confirmed_test_targets'],workspace_root=workspace_root,stop_policy=admission['stop_policy'],total_timeout_seconds=admission['timeout_seconds'],maximum_output_bytes=24000)
    consumed={**admission,'consumption_state':'consumed'}
    material={k:v for k,v in consumed.items() if k not in {'test_admission_id','test_admission_fingerprint'}}; consumed=canon(material,'test_admission_fingerprint','test_admission_id','engineering-test-admission-')
    overall=test_set.get('overall_status'); status='reproduced' if overall=='failed' else 'timed_out' if test_set.get('timed_out_targets') else 'not_reproduced' if overall=='passed' else 'blocked'
    body={'schema':RESULT_SCHEMA,'reproduction_request_reference':_ref(request),'human_confirmation_reference':_ref(confirmation),'test_admission_reference':_ref(consumed),'test_set_result_reference':_ref(test_set),'repository_identity':request.get('repository_identity'),'workspace_snapshot_reference':_ref(workspace_snapshot),'reproduction_status':status,'expected_behavior':request.get('expected_behavior'),'actual_behavior':'bounded tests '+str(overall),'reproduced':status=='reproduced','limitations':['bounded confirmed pytest targets only','test failure does not confirm root cause'],'authority':AUTHORITY}
    return canon(body,'reproduction_result_fingerprint','reproduction_result_id','engineering-reproduction-result-'),test_set,consumed

def inspect_reproduction_state(bundle:Mapping[str,Any])->dict[str,Any]:
    get=lambda key:bundle.get(STORE_FILES[key]) or {}
    return {'human_plan_confirmation_status':(bundle.get('planning/multifile-change-plan-confirmation.json') or {}).get('decision','missing'),'reproduction_request_status':'created' if get('request') else 'missing','reproduction_confirmation_status':get('confirmation').get('decision','missing'),'test_admission_status':get('admission').get('admission_status','missing'),'test_execution_status':get('test_set').get('overall_status','not_executed'),'reproduction_status':get('result').get('reproduction_status','not_started'),'failure_evidence_status':get('failure_evidence').get('evidence_status','not_started'),'repair_candidate_status':get('repair_candidate').get('candidate_status','not_started'),'scope_expansion_status':get('repair_candidate').get('scope_relationship','not_applicable'),'next_governed_action':resume_reproduction_state(bundle)['decision']}

def resume_reproduction_state(bundle:Mapping[str,Any])->dict[str,Any]:
    if not bundle.get('planning/multifile-change-plan-confirmation.json'): decision='requires_plan_confirmation'
    elif not bundle.get(STORE_FILES['request']): decision='requires_reproduction_request'
    elif not bundle.get(STORE_FILES['confirmation']): decision='requires_reproduction_confirmation'
    elif not bundle.get(STORE_FILES['admission']): decision='requires_test_admission'
    elif not bundle.get(STORE_FILES['result']): decision='requires_bounded_test_execution'
    elif (bundle.get(STORE_FILES['result']) or {}).get('reproduction_status')=='reproduced' and not bundle.get(STORE_FILES['failure_evidence']): decision='requires_failure_evidence'
    elif bundle.get(STORE_FILES['failure_evidence']) and not bundle.get(STORE_FILES['repair_candidate']): decision='requires_repair_candidate'
    elif bundle.get(STORE_FILES['repair_candidate']) and not bundle.get(STORE_FILES['repair_review']): decision='requires_human_repair_review'
    else: decision='human_repair_review_recorded'
    return {'schema':'zero.engineering.bug_reproduction_resume.v1','decision':decision,'will_confirm':False,'will_run_tests':False,'will_retry':False,'will_modify_repository':False,'will_approve':False,'will_authorize':False,'will_complete':False}
