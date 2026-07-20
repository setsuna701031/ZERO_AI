from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import freeze, norm_path, norm_paths, seal, short_text
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_repair_candidate import SCHEMA as CANDIDATE_SCHEMA

SCHEMA='zero.engineering.repair_plan.v1'
PLAN_STATUSES=('planned','blocked','invalid')
OPERATION_TYPES=('create_file','replace_file','delete_file')
EXPECTATION_TYPES=('file_exists','file_absent','fingerprint_changed','fingerprint_unchanged','focused_test_passed','compile_passed','invariant_preserved','transaction_committed','rollback_available')
AUTHORITY_BOUNDARY={'planning':'only','approval':'not_granted','authorization':'not_granted','token':'not_granted','mutation':'not_granted','test_execution':'not_granted','git':'not_granted'}

def _expectations(items: Any) -> list[dict[str, Any]]:
    out=[]
    if not isinstance(items,(list,tuple)) or not items: raise ValueError('empty_verification_expectations')
    for x in items:
        if not isinstance(x,Mapping): raise ValueError('expectation_not_mapping')
        d={'expectation_id':short_text(x.get('expectation_id'),96),'expectation_type':short_text(x.get('expectation_type'),64),'required':bool(x.get('required',True)),'expected_status':short_text(x.get('expected_status','satisfied'),64),'description':short_text(x.get('description'),512)}
        if x.get('target_path') is not None: d['target_path']=norm_path(x.get('target_path'))
        if x.get('component_identity') is not None: d['component_identity']=short_text(x.get('component_identity'),160)
        if x.get('expected_post_fingerprint') is not None: d['expected_post_fingerprint']=short_text(x.get('expected_post_fingerprint'),80)
        if x.get('expected_invariant') is not None: d['expected_invariant']=short_text(x.get('expected_invariant'),256)
        out.append(d)
    return sorted(out,key=lambda y:y['expectation_id'])

def build_engineering_repair_plan(*, candidate: Mapping[str,Any], requested_outcome: str|None=None, change_strategy:str='focused_canonical_repair', ordered_operations:Any=(), allowed_target_paths:Any=None, prohibited_target_paths:Any=None, expected_postconditions:Any=(), verification_expectations:Any=(), rollback_expectations:Any=(), assumptions:Any=(), constraints:Any=(), plan_status:str='planned') -> Mapping[str, Any]:
    allowed=norm_paths(allowed_target_paths if allowed_target_paths is not None else candidate.get('target_scope'))
    prohibited=sorted(dict.fromkeys(norm_path(p) for p in (prohibited_target_paths if prohibited_target_paths is not None else candidate.get('prohibited_scope',[]))))
    ver=_expectations(verification_expectations)
    ops=[]
    if not isinstance(ordered_operations,(list,tuple)) or not ordered_operations: raise ValueError('empty_operations')
    seed={'schema':SCHEMA,'candidate_identity':candidate.get('candidate_id'),'candidate_fingerprint':candidate.get('fingerprint'),'allowed_target_paths':allowed,'prohibited_target_paths':prohibited,'change_strategy':change_strategy}
    pid='engineering-repair-plan-'+fingerprint(seed)[:24]
    for i,o in enumerate(ordered_operations, start=1):
        if not isinstance(o,Mapping): raise ValueError('operation_not_mapping')
        target=norm_path(o.get('target_path'))
        typ=short_text(o.get('operation_type'),64)
        oid='engineering-repair-operation-'+fingerprint({'repair_plan_id':pid,'sequence':i,'operation_type':typ,'target_path':target,'candidate_identity':candidate.get('candidate_id')})[:24]
        ops.append({'operation_id':oid,'sequence':i,'operation_type':typ,'target_path':target,'source_candidate_identity':candidate.get('candidate_id'),'rationale':short_text(o.get('rationale'),512),'expected_precondition_type':short_text(o.get('expected_precondition_type','bounded_precondition'),96),'expected_change_kind':short_text(o.get('expected_change_kind',typ),96),'expected_postcondition':short_text(o.get('expected_postcondition'),256),'verification_expectation_ids':sorted(short_text(x,96) for x in o.get('verification_expectation_ids',[]))})
    body={'schema':SCHEMA,'repair_plan_id':pid,'task_id':candidate.get('task_id'),'repository_identity':candidate.get('repository_identity'),'analysis_identity':candidate.get('analysis_identity'),'candidate_identity':candidate.get('candidate_id'),'candidate_fingerprint':candidate.get('fingerprint'),'requested_outcome':short_text(requested_outcome or candidate.get('requested_outcome'),512),'plan_status':plan_status,'status':plan_status,'change_strategy':short_text(change_strategy,160),'ordered_operations':ops,'operation_count':len(ops),'ordered_operation_ids':[o['operation_id'] for o in ops],'ordered_operation_types':[o['operation_type'] for o in ops],'allowed_target_paths':allowed,'prohibited_target_paths':prohibited,'expected_postconditions':sorted(short_text(x,256) for x in expected_postconditions),'verification_expectations':ver,'rollback_expectations':sorted(short_text(x,256) for x in rollback_expectations) or ['rollback availability remains governed by mutation transaction layer'],'risk_level':candidate.get('risk_level','medium'),'assumptions':sorted(short_text(x,256) for x in assumptions),'constraints':sorted(short_text(x,256) for x in constraints),'deterministic':True,'immutable':True,'authority_boundary':AUTHORITY_BOUNDARY}
    body['fingerprint']=fingerprint({k:v for k,v in body.items() if k!='fingerprint'})
    return freeze(body)
